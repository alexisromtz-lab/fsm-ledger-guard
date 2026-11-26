"""El DSL es el contrato: si acepta basura, toda medición aguas abajo es prosa."""
from __future__ import annotations

import json
import unittest

from contexto import cargar_texto, documento, texto

from fsm_ledger_guard.dsl import ErrorDSL, desde_texto


class CargaTest(unittest.TestCase):
    def test_minimo_valido(self):
        g = cargar_texto(documento([("T1", "a", "b", {"saldo": 5})], [("a", False), ("b", True)]))
        self.assertEqual(g.dominio, "test/sintetico")
        self.assertEqual(g.inicial, "a")
        self.assertEqual(list(g.estados), ["a", "b"])
        self.assertTrue(g.estados["b"].terminal)
        self.assertFalse(g.estados["a"].terminal)
        self.assertEqual(g.transiciones[0].delta, {"saldo": 5})
        self.assertEqual(g.transiciones[0].atomico, True)
        self.assertEqual(g.transiciones[0].idem_key, "k")

    def test_estados_admite_objeto(self):
        doc = documento([("T1", "a", "b", {})], [("a", False), ("b", True)])
        doc["estados"] = {"a": {"terminal": False}, "b": {"terminal": True}}
        g = desde_texto(texto(doc))
        self.assertEqual(list(g.estados), ["a", "b"])
        self.assertTrue(g.estados["b"].terminal)

    def test_orden_de_estados_es_el_declarado(self):
        g = cargar_texto(
            documento([("T1", "a", "b", {})], [("b", True), ("a", False)], inicial="a")
        )
        self.assertEqual(list(g.estados), ["b", "a"])

    def test_schema_distinto(self):
        doc = documento([("T1", "a", "b", {})], [("a", False), ("b", True)])
        doc["schema"] = "fsm-ledger/2"
        with self.assertRaises(ErrorDSL) as ctx:
            desde_texto(texto(doc))
        self.assertIn("schema", str(ctx.exception))

    def test_json_invalido(self):
        with self.assertRaises(ErrorDSL):
            desde_texto("{no es json")

    def test_inicial_no_declarado(self):
        doc = documento([("T1", "a", "b", {})], [("a", False), ("b", True)])
        doc["inicial"] = "z"
        with self.assertRaises(ErrorDSL) as ctx:
            desde_texto(texto(doc))
        self.assertIn("inicial", str(ctx.exception))

    def test_id_repetido(self):
        doc = documento(
            [("T1", "a", "b", {}), ("T1", "a", "b", {})], [("a", False), ("b", True)]
        )
        with self.assertRaises(ErrorDSL) as ctx:
            desde_texto(texto(doc))
        self.assertIn("repetido", str(ctx.exception))

    def test_estado_no_declarado_en_transicion(self):
        doc = documento([("T1", "a", "z", {})], [("a", False), ("b", True)])
        with self.assertRaises(ErrorDSL) as ctx:
            desde_texto(texto(doc))
        self.assertIn("'z'", str(ctx.exception))

    def test_recurso_no_declarado(self):
        doc = documento([("T1", "a", "b", {"otro": 1})], [("a", False), ("b", True)])
        with self.assertRaises(ErrorDSL) as ctx:
            desde_texto(texto(doc))
        self.assertIn("otro", str(ctx.exception))

    def test_delta_booleano_se_rechaza(self):
        doc = documento([("T1", "a", "b", {"saldo": True})], [("a", False), ("b", True)])
        with self.assertRaises(ErrorDSL):
            desde_texto(texto(doc))

    def test_delta_no_entero_se_rechaza(self):
        doc = documento([("T1", "a", "b", {"saldo": 1.5})], [("a", False), ("b", True)])
        with self.assertRaises(ErrorDSL):
            desde_texto(texto(doc))

    def test_forma_con_unidad_declarada(self):
        doc = documento(
            [("T1", "a", "b", {"saldo": {"valor": 350, "unidad": "pesos"}})],
            [("a", False), ("b", True)],
        )
        t = desde_texto(texto(doc)).transiciones[0]
        self.assertEqual(t.delta, {"saldo": 350})
        self.assertEqual(t.unidad_declarada, {"saldo": "pesos"})
        self.assertTrue(t.mueve("saldo"))
        self.assertTrue(t.mueve_algo)

    def test_delta_cero_no_mueve(self):
        g = cargar_texto(documento([("T1", "a", "b", {"saldo": 0})], [("a", False), ("b", True)]))
        t = g.transiciones[0]
        self.assertFalse(t.mueve("saldo"))
        self.assertFalse(t.mueve_algo)

    def test_idem_vacio_es_ausencia(self):
        doc = documento(
            [("T1", "a", "b", {"saldo": 1}, True, "   ")], [("a", False), ("b", True)]
        )
        self.assertIsNone(desde_texto(texto(doc)).transiciones[0].idem_key)

    def test_omision_es_fail_closed(self):
        doc = documento([("T1", "a", "b", {"saldo": 1})], [("a", False), ("b", True)])
        del doc["transiciones"][0]["atomico"]
        del doc["transiciones"][0]["idem_key"]
        t = desde_texto(texto(doc)).transiciones[0]
        self.assertFalse(t.atomico)
        self.assertIsNone(t.idem_key)

    def test_linea_apunta_al_id(self):
        g = cargar_texto(
            documento(
                [("T1", "a", "b", {}), ("T2", "b", "c", {})],
                [("a", False), ("b", False), ("c", True)],
            )
        )
        texto_fuente = texto(
            documento(
                [("T1", "a", "b", {}), ("T2", "b", "c", {})],
                [("a", False), ("b", False), ("c", True)],
            )
        ).splitlines()
        for t in g.transiciones:
            self.assertIn(f'"id": "{t.id}"', texto_fuente[t.linea - 1])

    def test_huella_es_estable_y_sensible(self):
        uno = cargar_texto(documento([("T1", "a", "b", {"saldo": 5})], [("a", False), ("b", True)]))
        otro = cargar_texto(documento([("T1", "a", "b", {"saldo": 5})], [("a", False), ("b", True)]))
        distinto = cargar_texto(
            documento([("T1", "a", "b", {"saldo": 6})], [("a", False), ("b", True)])
        )
        self.assertEqual(uno.huella(), otro.huella())
        self.assertNotEqual(uno.huella(), distinto.huella())
        self.assertEqual(len(uno.huella()), 64)
        self.assertEqual(uno.huella(), uno.huella())

    def test_canonico_no_depende_del_orden_de_claves(self):
        doc = documento([("T1", "a", "b", {"saldo": 5})], [("a", False), ("b", True)])
        reordenado = json.loads(json.dumps(doc))
        reordenado = {k: reordenado[k] for k in reversed(list(reordenado))}
        self.assertEqual(
            desde_texto(texto(doc)).huella(), desde_texto(texto(reordenado)).huella()
        )

    def test_vacio_se_rechaza(self):
        for campo in ("recursos", "estados", "transiciones"):
            doc = documento([("T1", "a", "b", {})], [("a", False), ("b", True)])
            doc[campo] = {} if campo != "transiciones" else []
            with self.assertRaises(ErrorDSL, msg=campo):
                desde_texto(texto(doc))


class EnlacesTest(unittest.TestCase):
    """Un enlace mal declarado es un enlace que miente: se rechaza, no se adivina."""

    def _doc(self, enlaces):
        return documento(
            [("T1", "a", "b", {"saldo": 1})],
            [("a", False), ("b", True)],
            recursos={
                "saldo": {"unidad": "centavos", "minimo": 0, "saldo_inicial": 0},
                "libro": {"unidad": "centavos", "minimo": 0, "saldo_inicial": 0},
            },
            enlaces=enlaces,
        )

    def test_enlace_valido_se_lee_con_nombre_derivado(self):
        g = cargar_texto(self._doc([{"recursos": ["saldo", "libro"]}]))
        self.assertEqual(len(g.enlaces), 1)
        self.assertEqual(g.enlaces[0].nombre, "saldo↔libro")
        self.assertEqual(g.enlaces[0].ratio, (1, 1))

    def test_recurso_no_declarado_se_rechaza(self):
        with self.assertRaises(ErrorDSL):
            desde_texto(texto(self._doc([{"recursos": ["saldo", "fantasma"]}])))

    def test_recurso_repetido_se_rechaza(self):
        with self.assertRaises(ErrorDSL):
            desde_texto(texto(self._doc([{"recursos": ["saldo", "saldo"]}])))

    def test_ratio_de_longitud_distinta_se_rechaza(self):
        with self.assertRaises(ErrorDSL):
            desde_texto(texto(self._doc([{"recursos": ["saldo", "libro"], "ratio": [1]}])))

    def test_un_solo_recurso_no_es_un_enlace(self):
        with self.assertRaises(ErrorDSL):
            desde_texto(texto(self._doc([{"recursos": ["saldo"]}])))

    def test_sin_enlaces_la_huella_no_cambia(self):
        con = cargar_texto(self._doc([{"recursos": ["saldo", "libro"]}]))
        sin = cargar_texto(self._doc(None))
        self.assertEqual(len(sin.enlaces), 0)
        self.assertNotEqual(con.huella(), sin.huella())
        self.assertEqual(sin.huella(), cargar_texto(self._doc(None)).huella())


if __name__ == "__main__":
    unittest.main()
