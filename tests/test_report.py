"""SARIF y recibo: la forma es el contrato, así que se afirma la forma."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from contexto import cargar_texto, documento

from fsm_ledger_guard import __version__
from fsm_ledger_guard.checks import auditar
from fsm_ledger_guard.report import (
    CUBETAS,
    a_recibo,
    a_sarif,
    clasificar,
    escribir,
    resumen,
)

HEX64 = re.compile(r"^[0-9a-f]{64}$")

FUGA = [
    ("T1", "a", "b", {"saldo": 350}),
    ("T2", "b", "a", {}),
    ("T3", "a", "c", {}),
]
ESTADOS = [("a", False), ("b", False), ("c", True)]


def fuga():
    return cargar_texto(documento(FUGA, ESTADOS))


def limpio():
    return cargar_texto(
        documento(
            [
                ("T1", "a", "b", {"saldo": 10}, True, "evento-1"),
                ("T2", "b", "c", {"saldo": -10}, True, "evento-2"),
            ],
            ESTADOS,
        )
    )


class SarifTest(unittest.TestCase):
    def test_forma_21_0(self):
        sarif = a_sarif(auditar(fuga()), fixture="tests/fixtures/prueba.json")
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertIn("sarif-2.1.0", sarif["$schema"])
        self.assertEqual(len(sarif["runs"]), 1)
        run = sarif["runs"][0]
        self.assertEqual(run["tool"]["driver"]["name"], "fsm-ledger-guard")
        self.assertEqual(run["tool"]["driver"]["version"], __version__)
        self.assertTrue(run["tool"]["driver"]["informationUri"].startswith("https://"))
        self.assertEqual(run["properties"]["dominio"], "test/sintetico")

    def test_ruleindex_apunta_a_la_regla_declarada(self):
        run = a_sarif(auditar(fuga()))["runs"][0]
        reglas = [r["id"] for r in run["tool"]["driver"]["rules"]]
        self.assertEqual(reglas, sorted(reglas))
        for resultado in run["results"]:
            self.assertEqual(reglas[resultado["ruleIndex"]], resultado["ruleId"])
            self.assertIn(resultado["level"], ("error", "warning", "note"))

    def test_cada_resultado_tiene_ubicacion_y_huella(self):
        run = a_sarif(auditar(fuga()), fixture="tests/fixtures/prueba.json")["runs"][0]
        self.assertTrue(run["results"])
        huellas = set()
        for resultado in run["results"]:
            ubicacion = resultado["locations"][0]["physicalLocation"]
            self.assertEqual(ubicacion["artifactLocation"]["uri"], "tests/fixtures/prueba.json")
            self.assertGreaterEqual(ubicacion["region"]["startLine"], 1)
            huella = resultado["partialFingerprints"]["fsmLedgerGuard/v1"]
            self.assertRegex(huella, r"^[0-9a-f]{16}$")
            huellas.add(huella)
        self.assertEqual(len(huellas), len(run["results"]))

    def test_huella_estable_entre_corridas(self):
        uno = a_sarif(auditar(fuga()))["runs"][0]["results"]
        dos = a_sarif(auditar(fuga()))["runs"][0]["results"]
        self.assertEqual(uno, dos)

    def test_invocacion_declara_si_se_ejecuto(self):
        self.assertTrue(a_sarif(auditar(fuga()))["runs"][0]["invocations"][0]["executionSuccessful"])
        proyeccion = cargar_texto(
            documento(
                [
                    ("T1", "a", "b", {"saldo": 10}, True, "evento-1"),
                    ("T2", "b", "c", {"saldo": -10}, True, "evento-2"),
                ],
                ESTADOS,
                medido=False,
            )
        )
        invocacion = a_sarif(auditar(proyeccion, exigir_medido=True))["runs"][0]["invocations"][0]
        self.assertTrue(invocacion["executionSuccessful"])
        self.assertEqual(invocacion["properties"]["rc"], 2)

    def test_sin_hallazgos_el_sarif_esta_vacio_pero_completo(self):
        run = a_sarif(auditar(limpio()))["runs"][0]
        self.assertEqual(run["results"], [])
        self.assertEqual(run["tool"]["driver"]["rules"], [])


class ReciboTest(unittest.TestCase):
    def test_particion_cierra(self):
        resultado = auditar(fuga())
        recibo = a_recibo(resultado)
        self.assertEqual(recibo["schema"], "conservation/1")
        self.assertEqual(recibo["instrumento"], "fsm-ledger-guard")
        self.assertEqual(recibo["unidad"], "transiciones")
        self.assertEqual(recibo["dominio"], len(resultado.grafo.transiciones))
        self.assertEqual(tuple(recibo["cubetas"]), CUBETAS)
        self.assertEqual(sum(recibo["cubetas"].values()), recibo["dominio"])

    def test_digests_en_hexadecimal(self):
        recibo = a_recibo(auditar(fuga()))
        self.assertRegex(recibo["digests"]["entrada"], HEX64)
        self.assertRegex(recibo["digests"]["salida"], HEX64)
        self.assertNotEqual(recibo["digests"]["entrada"], recibo["digests"]["salida"])

    def test_declarado_habla_de_la_particion_no_de_la_auditoria(self):
        resultado = auditar(fuga())
        recibo = a_recibo(resultado)
        self.assertTrue(recibo["declarado"]["conserva"])
        self.assertEqual(recibo["declarado"]["rc"], 0)
        self.assertEqual(recibo["auditoria"]["rc"], resultado.rc)
        self.assertEqual(recibo["auditoria"]["hallazgos"], len(resultado.hallazgos))

    def test_el_recibo_no_declara_vacio_ni_ruptura(self):
        # en la escala de conservation-ledger 2 y 4 son VACIO y RUPTURA: declararlos
        # con la particion cerrada provoca DISCREPANCIA
        for grafo in (fuga(), limpio()):
            self.assertNotIn(a_recibo(auditar(grafo))["declarado"]["rc"], (2, 4))

    def test_recibo_es_json_serializable(self):
        recibo = a_recibo(auditar(fuga()))
        self.assertEqual(json.loads(json.dumps(recibo)), recibo)

    def test_cubetas_priorizan_el_ciclo(self):
        cubetas = clasificar(auditar(fuga()))
        self.assertEqual(sum(cubetas.values()), 3)
        self.assertEqual(cubetas["en_ciclo_fuga"], 2)
        self.assertEqual(cubetas["limpias"], 1)

    def test_arista_inalcanzable_cae_en_su_cubeta(self):
        grafo = cargar_texto(
            documento(
                [("T1", "a", "b", {}), ("T2", "y", "z", {})],
                [("a", False), ("b", True), ("y", False), ("z", True)],
            )
        )
        cubetas = clasificar(auditar(grafo))
        self.assertEqual(cubetas["inalcanzable"], 1)
        self.assertEqual(cubetas["limpias"], 1)


class ResumenTest(unittest.TestCase):
    def test_nombra_la_regla_el_contraejemplo_y_el_rc(self):
        texto = resumen(auditar(fuga()))
        self.assertIn("FSM001", texto)
        self.assertIn("contraejemplo", texto)
        self.assertTrue(texto.rstrip().endswith("RC 1"))

    def test_marca_la_proyeccion(self):
        proyeccion = cargar_texto(
            documento(
                [
                    ("T1", "a", "b", {"saldo": 10}, True, "evento-1"),
                    ("T2", "b", "c", {"saldo": -10}, True, "evento-2"),
                ],
                ESTADOS,
                medido=False,
            )
        )
        self.assertIn("PROYECCIÓN · NO MEDIDO", resumen(auditar(proyeccion)))

    def test_grafo_limpio_no_inventa_hallazgos(self):
        texto = resumen(auditar(limpio()))
        self.assertIn("sin hallazgos", texto)
        self.assertTrue(texto.rstrip().endswith("RC 0"))


class EscribirTest(unittest.TestCase):
    def test_crea_el_directorio_y_cierra_con_salto(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "salida" / "recibo.json"
            escribir({"a": 1}, destino)
            self.assertEqual(destino.read_text(encoding="utf-8"), '{\n  "a": 1\n}\n')


if __name__ == "__main__":
    unittest.main()
