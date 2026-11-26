"""Cada comprobación se prueba con el contraejemplo más pequeño que la falsa.

Un test que sólo dice «hay un hallazgo» no distingue una detección exacta de una
heurística; por eso se afirma el camino testigo, el delta neto y el alcance.
"""
from __future__ import annotations

import unittest

from contexto import cargar_texto, documento

from fsm_ledger_guard import checks
from fsm_ledger_guard.checks import (
    RC_HALLAZGO,
    RC_LIMPIO,
    RC_NO_MEDIDO,
    alcanzables,
    auditar,
    camino_mas_corto,
    componentes_fuertemente_conexas,
    conservacion_acotada,
)


def reglas(resultado):
    return sorted(h.regla for h in resultado.hallazgos)


def por_regla(resultado, regla):
    return [h for h in resultado.hallazgos if h.regla == regla]


class CicloConFugaTest(unittest.TestCase):
    def test_dos_aristas_con_delta_neto(self):
        g = cargar_texto(
            documento(
                [("P3", "a", "b", {"saldo": 350}), ("P9", "b", "a", {}), ("P7", "a", "c", {})],
                [("a", False), ("b", False), ("c", True)],
            )
        )
        h = por_regla(auditar(g), "FSM001")
        self.assertEqual(len(h), 1)
        self.assertEqual(set(h[0].camino), {"P3", "P9"})
        self.assertEqual(len(h[0].camino), 2)
        self.assertEqual(h[0].detalle["delta_neto"], 350)
        self.assertEqual(h[0].detalle["recurso"], "saldo")

    def test_lazo_con_delta_cero_no_dispara(self):
        g = cargar_texto(
            documento(
                [("N1", "a", "a", {"saldo": 0}), ("T1", "a", "b", {})],
                [("a", False), ("b", True)],
            )
        )
        self.assertEqual(por_regla(auditar(g), "FSM001"), [])

    def test_ciclo_equilibrado_no_dispara(self):
        g = cargar_texto(
            documento(
                [
                    ("T1", "a", "b", {"saldo": 100}),
                    ("T2", "b", "a", {"saldo": -100}),
                    ("T3", "b", "c", {}),
                    ("T4", "c", "d", {"saldo": -100}),
                ],
                [("a", False), ("b", False), ("c", False), ("d", True)],
            )
        )
        self.assertEqual(reglas(auditar(g)), [])

    def test_el_ciclo_se_mide_por_recurso(self):
        g = cargar_texto(
            documento(
                [
                    ("T1", "a", "b", {"saldo": 10}),
                    ("T2", "b", "a", {"saldo": -10, "otro": 3}),
                    ("T4", "a", "c", {}),
                ],
                [("a", False), ("b", False), ("c", True)],
                recursos={
                    "saldo": {"unidad": "u", "minimo": 0, "saldo_inicial": 0},
                    "otro": {"unidad": "v", "minimo": 0, "saldo_inicial": 0},
                },
            )
        )
        h = por_regla(auditar(g), "FSM001")
        self.assertEqual([x.detalle["recurso"] for x in h], ["otro"])
        self.assertEqual(h[0].detalle["delta_neto"], 3)

    def test_descomposicion_en_ciclos_simples(self):
        # el paseo cerrado puede repetir vértices; el testigo publicado no
        g = cargar_texto(
            documento(
                [
                    ("T1", "a", "b", {"saldo": 5}),
                    ("T2", "b", "c", {}),
                    ("T3", "c", "b", {}),
                    ("T4", "c", "a", {"saldo": -5}),
                    ("T5", "a", "d", {}),
                ],
                [("a", False), ("b", False), ("c", False), ("d", True)],
            )
        )
        # b<->c es un ciclo limpio y a->b->c->a tambien: no hay fuga
        self.assertEqual(por_regla(auditar(g), "FSM001"), [])


class AlcanzabilidadTest(unittest.TestCase):
    def test_estado_inalcanzable(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {}), ("T2", "z", "y", {})],
                [("a", False), ("b", True), ("y", True), ("z", False)],
            )
        )
        r = auditar(g)
        self.assertIn("FSM002", reglas(r))
        self.assertEqual(por_regla(r, "FSM002")[0].estados, ("y", "z"))
        self.assertEqual(por_regla(r, "FSM003")[0].transiciones, ("T2",))

    def test_alcance_no_cruza_por_aristas_inexistentes(self):
        g = cargar_texto(
            documento([("T1", "a", "b", {})], [("a", False), ("b", False), ("c", True)])
        )
        componentes = sorted(tuple(sorted(c)) for c in componentes_fuertemente_conexas(g))
        self.assertEqual(componentes, [("a",), ("b",), ("c",)])

    def test_camino_mas_corto_respeta_permitidos(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {}), ("T2", "b", "c", {}), ("T3", "c", "d", {})],
                [("a", False), ("b", False), ("c", False), ("d", True)],
            )
        )
        self.assertEqual([t.id for t in camino_mas_corto(g, "a", "d")], ["T1", "T2", "T3"])
        self.assertIsNone(camino_mas_corto(g, "a", "d", {"a", "b"}))
        self.assertEqual(alcanzables(g), {"a", "b", "c", "d"})


class EstadosMuertosTest(unittest.TestCase):
    def test_componente_sin_salida_ni_terminal(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {}), ("T2", "b", "a", {})],
                [("a", False), ("b", False)],
            )
        )
        r = auditar(g)
        self.assertEqual(por_regla(r, "FSM004")[0].estados, ("a", "b"))

    def test_terminal_con_salida(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {}), ("T2", "b", "c", {})],
                [("a", False), ("b", True), ("c", True)],
            )
        )
        self.assertEqual(por_regla(auditar(g), "FSM005")[0].transiciones, ("T2",))

    def test_lazo_en_terminal_no_es_salida(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {}), ("T2", "b", "b", {})],
                [("a", False), ("b", True)],
            )
        )
        self.assertEqual(por_regla(auditar(g), "FSM005"), [])


class RetencionTest(unittest.TestCase):
    def test_sin_arista_que_disminuya_es_global(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {"saldo": 100}), ("T2", "b", "c", {})],
                [("a", False), ("b", False), ("c", True)],
            )
        )
        h = por_regla(auditar(g), "FSM006")
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0].detalle["alcance"], "global")
        self.assertEqual(h[0].detalle["saldo_maximo"], 100)
        self.assertEqual(h[0].estados, ("b", "c"))

    def test_saldo_que_no_puede_bajar_es_por_estado(self):
        g = cargar_texto(
            documento(
                [
                    ("T1", "a", "b", {"saldo": 5}),
                    ("T2", "a", "x", {"saldo": 5}),
                    ("T3", "x", "y", {"saldo": -5}),
                    ("T4", "b", "c", {}),
                ],
                [("a", False), ("b", False), ("c", True), ("x", False), ("y", True)],
            )
        )
        h = por_regla(auditar(g), "FSM006")
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0].detalle["alcance"], "estado")
        # x tambien tiene saldo, pero puede soltarlo: solo b y c lo retienen
        self.assertEqual(h[0].estados, ("b", "c"))
        self.assertEqual(h[0].detalle["saldos"], {"b": 5, "c": 5})

    def test_recurso_acumulativo_no_se_vigila(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {"saldo": 100}), ("T2", "b", "c", {})],
                [("a", False), ("b", False), ("c", True)],
                recursos={"saldo": {"unidad": "u", "minimo": 0, "acumulativa": True}},
            )
        )
        r = auditar(g)
        self.assertEqual(por_regla(r, "FSM006"), [])
        self.assertIn("acumulativo", r.cobertura["retencion:saldo"])


class CoberturaDeRetencionTest(unittest.TestCase):
    """La cobertura dice qué mitad del par se midió, y hay que poder leerlo.

    Caso real (payouts de un creador, 2026-11-26): con la retención ya presente en
    el estado inicial y sólo aristas de salida, el veredicto fue RC 0 y la
    cobertura dijo «el recurso nunca entra». Ese verde no cubría la entrada, y
    nada en el RC lo delataba. Estos dos tests fijan que la diferencia se publique:
    si alguien la borra, el mismo grafo verde pasaría a decir que todo saldo
    positivo tiene salida sin haber visto entrar nada.
    """

    def test_frontera_que_oculta_la_entrada_lo_declara(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {"saldo": -100})],
                [("a", False), ("b", True)],
                recursos={
                    "saldo": {"unidad": "u", "minimo": 0, "maximo": 100, "saldo_inicial": 100}
                },
            )
        )
        r = auditar(g)
        self.assertEqual(por_regla(r, "FSM006"), [])
        self.assertEqual(r.rc, RC_LIMPIO)
        self.assertEqual(r.cobertura["retencion:saldo"], "MEDIDO: el recurso nunca entra")

    def test_con_arista_de_alta_la_cobertura_cubre_el_par(self):
        g = cargar_texto(
            documento(
                [("T0", "p", "a", {"saldo": 100}), ("T1", "a", "b", {"saldo": -100})],
                [("p", False), ("a", False), ("b", True)],
                recursos={
                    "saldo": {"unidad": "u", "minimo": 0, "maximo": 100, "saldo_inicial": 0}
                },
                inicial="p",
            )
        )
        r = auditar(g)
        self.assertEqual(por_regla(r, "FSM006"), [])
        self.assertEqual(r.rc, RC_LIMPIO)
        self.assertEqual(r.cobertura["retencion:saldo"], "MEDIDO: todo saldo positivo tiene salida")


class GuardasTest(unittest.TestCase):
    def test_movimiento_sin_atomicidad_y_sin_idem(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {"saldo": 5}, False, None)],
                [("a", False), ("b", True)],
            )
        )
        r = auditar(g)
        self.assertEqual(por_regla(r, "FSM007")[0].transiciones, ("T1",))
        self.assertEqual(por_regla(r, "FSM008")[0].transiciones, ("T1",))

    def test_arista_sin_movimiento_no_exige_guardas(self):
        g = cargar_texto(
            documento([("T1", "a", "b", {}, False, None)], [("a", False), ("b", True)])
        )
        r = auditar(g)
        self.assertEqual(por_regla(r, "FSM007"), [])
        self.assertEqual(por_regla(r, "FSM008"), [])

    def test_unidad_inconsistente(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {"saldo": {"valor": 350, "unidad": "pesos"}})],
                [("a", False), ("b", True)],
            )
        )
        h = por_regla(auditar(g), "FSM009")
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0].detalle["unidad_declarada"], "pesos")
        self.assertEqual(h[0].detalle["unidad_del_recurso"], "unidades")
        self.assertEqual(h[0].severidad, "warning")


class ConservacionAcotadaTest(unittest.TestCase):
    def test_saldo_negativo(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {"saldo": -5})], [("a", False), ("b", True)]
            )
        )
        r = auditar(g)
        self.assertEqual(por_regla(r, "FSM010")[0].detalle["saldo"], -5)
        self.assertEqual(por_regla(r, "FSM010")[0].detalle["minimo"], 0)

    def test_cota_excedida_una_vez_por_recurso(self):
        g = cargar_texto(
            documento(
                [
                    ("T1", "a", "b", {"saldo": 2000}),
                    ("T2", "b", "a", {"saldo": 0}),
                    ("T3", "b", "c", {}),
                ],
                [("a", False), ("b", False), ("c", True)],
                recursos={"saldo": {"unidad": "u", "minimo": 0, "maximo": 1000}},
            )
        )
        h = por_regla(auditar(g), "FSM011")
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0].detalle["maximo"], 1000)
        self.assertEqual(h[0].detalle["camino"], ["T1"])

    def test_cota_no_saluda_cuando_el_maximo_se_respeta(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {"saldo": 1000}), ("T2", "b", "c", {"saldo": -1000})],
                [("a", False), ("b", False), ("c", True)],
                recursos={"saldo": {"unidad": "u", "minimo": 0, "maximo": 1000}},
            )
        )
        self.assertEqual(por_regla(auditar(g), "FSM011"), [])

    def test_frontera_abierta_es_no_medido(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {}), ("T2", "b", "c", {}), ("T3", "c", "d", {})],
                [("a", False), ("b", False), ("c", False), ("d", True)],
            )
        )
        hallazgos, medicion = conservacion_acotada(g, profundidad=2)
        self.assertFalse(medicion.cerrada)
        self.assertGreater(medicion.frontera, 0)
        self.assertEqual(hallazgos, [])
        self.assertEqual(auditar(g, profundidad=2).rc, RC_NO_MEDIDO)

    def test_espacio_que_se_cierra(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {}), ("T2", "b", "c", {})],
                [("a", False), ("b", False), ("c", True)],
            )
        )
        _, medicion = conservacion_acotada(g, profundidad=8)
        self.assertTrue(medicion.cerrada)
        self.assertEqual(medicion.frontera, 0)


class EscaleraTest(unittest.TestCase):
    def test_grafo_limpio_rc0(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {"saldo": 10}), ("T2", "b", "c", {"saldo": -10})],
                [("a", False), ("b", False), ("c", True)],
            )
        )
        r = auditar(g)
        self.assertEqual(r.rc, RC_LIMPIO)
        self.assertEqual(r.hallazgos, ())

    def test_proyeccion_bajo_exigir_medido_es_rc2(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {"saldo": 10}), ("T2", "b", "c", {"saldo": -10})],
                [("a", False), ("b", False), ("c", True)],
                medido=False,
            )
        )
        self.assertEqual(auditar(g).rc, RC_LIMPIO)
        self.assertEqual(auditar(g, exigir_medido=True).rc, RC_NO_MEDIDO)

    def test_hallazgo_gana_a_no_medido(self):
        g = cargar_texto(
            documento(
                [
                    ("T1", "a", "b", {"saldo": 100}),
                    ("T2", "b", "c", {}),
                    ("T3", "a", "d", {}),
                ],
                [("a", False), ("b", False), ("c", True), ("d", True)],
            )
        )
        r = auditar(g, profundidad=1)
        self.assertIn("FSM006", reglas(r))
        # la exploracion quedo abierta, pero un hallazgo pesa mas que NO_MEDIDO
        self.assertFalse(r.medicion.cerrada)
        self.assertEqual(r.rc, RC_HALLAZGO)

    def test_un_hallazgo_basta_para_rc1(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {"saldo": 5}, False, None)], [("a", False), ("b", True)]
            )
        )
        self.assertEqual(auditar(g).rc, RC_HALLAZGO)

    def test_orden_de_hallazgos_es_estable(self):
        g = cargar_texto(
            documento(
                [
                    ("T1", "a", "b", {"saldo": 350}, False, None),
                    ("T2", "b", "a", {}),
                    ("T3", "a", "c", {}),
                ],
                [("a", False), ("b", False), ("c", True)],
            )
        )
        uno = [h.a_dict() for h in auditar(g).hallazgos]
        dos = [h.a_dict() for h in auditar(g).hallazgos]
        self.assertEqual(uno, dos)
        self.assertEqual(uno, sorted(uno, key=lambda h: (h["regla"], h["linea"], h["transiciones"])))


class EnlaceDeclaradoTest(unittest.TestCase):
    """FSM012 sólo existe donde el sujeto declara que dos recursos son el mismo dinero.

    Sin la declaración, que ``saldo`` y ``libro`` diverjan es un juicio del analista;
    con ella es un cómputo que el motor puede enumerar sobre todas las aristas.
    """

    RECURSOS = {
        "saldo": {
            "unidad": "centavos",
            "minimo": 0,
            "maximo": None,
            "saldo_inicial": 0,
            "acumulativa": True,
        },
        "libro": {
            "unidad": "centavos",
            "minimo": 0,
            "maximo": None,
            "saldo_inicial": 0,
            "acumulativa": True,
        },
    }

    def test_mueve_uno_y_no_el_otro(self):
        g = cargar_texto(
            documento(
                [("K1", "a", "b", {"saldo": 100}), ("K2", "b", "c", {})],
                [("a", False), ("b", False), ("c", True)],
                recursos=self.RECURSOS,
                enlaces=[{"nombre": "saldo↔libro", "recursos": ["saldo", "libro"], "ratio": [1, 1]}],
            )
        )
        r = auditar(g)
        hallazgos = por_regla(r, "FSM012")
        self.assertEqual([h.transiciones for h in hallazgos], [("K1",)])
        self.assertEqual(hallazgos[0].detalle["deltas"], {"saldo": 100, "libro": 0})
        self.assertIn("saldo↔libro", hallazgos[0].mensaje)
        self.assertEqual(r.rc, RC_HALLAZGO)

    def test_proporcion_respetada_no_emite(self):
        g = cargar_texto(
            documento(
                [("K1", "a", "b", {"saldo": 100, "libro": 200}), ("K2", "b", "c", {})],
                [("a", False), ("b", False), ("c", True)],
                recursos=self.RECURSOS,
                enlaces=[{"nombre": "uno a dos", "recursos": ["saldo", "libro"], "ratio": [1, 2]}],
            )
        )
        self.assertEqual(por_regla(auditar(g), "FSM012"), [])

    def test_sin_enlaces_es_cero_medido_y_no_silencio(self):
        g = cargar_texto(
            documento(
                [("K1", "a", "b", {"saldo": 100}), ("K2", "b", "c", {})],
                [("a", False), ("b", False), ("c", True)],
                recursos=self.RECURSOS,
            )
        )
        r = auditar(g)
        self.assertEqual(por_regla(r, "FSM012"), [])
        self.assertTrue(r.cobertura["enlaces"].startswith("MEDIDO"), msg=r.cobertura["enlaces"])


class ReglasTest(unittest.TestCase):
    def test_toda_regla_declarada_tiene_titulo_y_ayuda(self):
        for regla, cuerpo in checks.REGLAS.items():
            self.assertRegex(regla, r"^FSM\d{3}$")
            for campo in ("clase", "titulo", "ayuda", "severidad"):
                self.assertTrue(cuerpo.get(campo), msg=f"{regla}.{campo}")
            self.assertIn(cuerpo["severidad"], ("error", "warning", "note"))


if __name__ == "__main__":
    unittest.main()
