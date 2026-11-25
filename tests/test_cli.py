"""La escalera de salida es el contrato con CI: se prueba por subproceso."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from contexto import FIXTURES, RAIZ, SRC, cargar_texto, documento

PRE = str(FIXTURES / "studio_city_pre_fix.json")
POST = str(FIXTURES / "studio_city_post_fix.json")
OBJETIVO = str(FIXTURES / "studio_city_objetivo.json")


def ejecutar(*argumentos, fixture=None):
    entorno = dict(os.environ)
    entorno["PYTHONPATH"] = str(SRC) + (
        os.pathsep + entorno["PYTHONPATH"] if entorno.get("PYTHONPATH") else ""
    )
    return subprocess.run(
        [sys.executable, "-m", "fsm_ledger_guard", *argumentos],
        capture_output=True,
        text=True,
        cwd=str(RAIZ),
        env=entorno,
    )


class EscaleraTest(unittest.TestCase):
    def test_rc1_con_hallazgos(self):
        proceso = ejecutar("scan", PRE)
        self.assertEqual(proceso.returncode, 1, proceso.stderr)
        self.assertIn("FSM001", proceso.stdout)
        self.assertIn("contraejemplo", proceso.stdout)

    def test_rc0_limpio(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "limpio.json"
            ruta.write_text(
                json.dumps(
                    documento(
                        [
                            ("T1", "a", "b", {"saldo": 10}, True, "k1"),
                            ("T2", "b", "c", {"saldo": -10}, True, "k2"),
                        ],
                        [("a", False), ("b", False), ("c", True)],
                    ),
                    indent=2,
                ),
                encoding="utf-8",
            )
            proceso = ejecutar("scan", str(ruta))
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        self.assertIn("sin hallazgos", proceso.stdout)

    def test_rc2_si_la_exploracion_no_cierra(self):
        proceso = ejecutar("scan", OBJETIVO, "--exigir-medido")
        self.assertEqual(proceso.returncode, 2, proceso.stdout)

    def test_rc4_si_el_fixture_no_es_el_esquema(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "roto.json"
            ruta.write_text('{"schema": "otro/9"}', encoding="utf-8")
            proceso = ejecutar("scan", str(ruta))
        self.assertEqual(proceso.returncode, 4)
        self.assertIn("schema", proceso.stderr)

    def test_rc4_sin_subcomando(self):
        self.assertEqual(ejecutar().returncode, 4)

    def test_rc4_con_argumentos_invalidos(self):
        self.assertEqual(ejecutar("scan", PRE, "--depth", "0").returncode, 4)
        self.assertEqual(ejecutar("scan", PRE, "--inventado").returncode, 4)


class ArtefactosTest(unittest.TestCase):
    def test_escribe_sarif_y_recibo(self):
        with tempfile.TemporaryDirectory() as tmp:
            sarif = Path(tmp) / "out" / "salida.sarif"
            recibo = Path(tmp) / "out" / "recibo.json"
            proceso = ejecutar(
                "scan", PRE, "--sarif", str(sarif), "--recibo", str(recibo), "-q"
            )
            self.assertEqual(proceso.returncode, 1, proceso.stderr)
            self.assertEqual(proceso.stdout.strip().splitlines()[-1], f"recibo {recibo}")
            log = json.loads(sarif.read_text(encoding="utf-8"))
            doc = json.loads(recibo.read_text(encoding="utf-8"))
        self.assertEqual(log["version"], "2.1.0")
        self.assertTrue(log["runs"][0]["results"])
        self.assertEqual(doc["schema"], "conservation/1")
        self.assertEqual(sum(doc["cubetas"].values()), doc["dominio"])

    def test_json_es_la_misma_medicion(self):
        proceso = ejecutar("scan", POST, "--json")
        self.assertEqual(proceso.returncode, 1, proceso.stderr)
        datos = json.loads(proceso.stdout)
        self.assertEqual(datos["rc"], 1)
        self.assertEqual(sorted(h["regla"] for h in datos["hallazgos"]), ["FSM006", "FSM008", "FSM008"])
        self.assertEqual(datos["medicion"]["profundidad"], 8)


class VariosFixturesTest(unittest.TestCase):
    def test_el_rc_del_acto_combina_la_escalera(self):
        self.assertEqual(ejecutar("scan", POST, "-q").returncode, 1)
        self.assertEqual(
            ejecutar("scan", POST, str(FIXTURES / "studio_city_objetivo.json"), "-q").returncode, 1
        )

    def test_una_proyeccion_sola_no_contamina_un_grafo_limpio(self):
        proceso = ejecutar("scan", OBJETIVO, POST, "-q")
        self.assertEqual(proceso.returncode, 1)
        self.assertEqual(ejecutar("scan", OBJETIVO, "--exigir-medido", "-q").returncode, 2)

    def test_artefactos_exigen_un_solo_fixture(self):
        proceso = ejecutar("scan", PRE, POST, "--sarif", "/dev/null")
        self.assertEqual(proceso.returncode, 4)
        self.assertIn("uno en uno", proceso.stderr)


class VersionTest(unittest.TestCase):
    def test_version(self):
        proceso = ejecutar("--version")
        self.assertEqual(proceso.returncode, 0)
        self.assertIn("fsm-ledger-guard", proceso.stdout)


if __name__ == "__main__":
    unittest.main()
