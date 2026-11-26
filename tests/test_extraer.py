"""El ejemplo publico: el fixture se deriva del codigo y se puede rehacer.

Aqui no se afirma lo que alguien escribio en un JSON: se comprueba que el JSON
commiteado es exactamente lo que produce ``examples/ecommerce_referencia/extraer.py``
sobre el codigo de ``examples/ecommerce_referencia/<arbol>/``. Si alguien cambia
una guarda y no regenera el fixture, este test lo dice antes que el README.

Los dos arboles son una reduccion publica del patron, no un tercer sistema en
produccion: existen para que el lector rehaga la medicion sin acceso a los
repositorios privados.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from contexto import RAIZ, FIXTURES

from fsm_ledger_guard.checks import RC_HALLAZGO, RC_LIMPIO, auditar
from fsm_ledger_guard.dsl import cargar

EJEMPLO = RAIZ / "examples" / "ecommerce_referencia"
REF_PRE = FIXTURES / "referencia_publica_pre_fix.json"
REF_POST = FIXTURES / "referencia_publica_post_fix.json"


def _cargar_extractor():
    spec = importlib.util.spec_from_file_location("extraer_ejemplo", EJEMPLO / "extraer.py")
    modulo = importlib.util.module_from_spec(spec)
    # dataclasses resuelve los tipos mirando sys.modules[cls.__module__]
    sys.modules[spec.name] = modulo
    try:
        spec.loader.exec_module(modulo)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return modulo


extraer = _cargar_extractor()


class DerivacionTest(unittest.TestCase):
    """El fixture commiteado y el codigo no pueden divergir."""

    def test_los_fixtures_commiteados_son_los_que_el_codigo_produce(self):
        for arbol, ruta in (("pre_fix", REF_PRE), ("post_fix", REF_POST)):
            with self.subTest(arbol=arbol):
                derivado = extraer.derivar(EJEMPLO, arbol)
                self.assertEqual(
                    extraer.serializar(derivado), ruta.read_text(encoding="utf-8")
                )

    def test_el_extractor_no_carga_el_motor(self):
        """Si el extractor importara ``checks``, el fixture dependeria del juez."""
        texto = (EJEMPLO / "extraer.py").read_text(encoding="utf-8")
        self.assertNotIn("fsm_ledger_guard", texto)


class ReferenciaPreFixTest(unittest.TestCase):
    """Dos escritores sin guarda: el mismo webhook de pago cobra dos veces."""

    def setUp(self):
        self.resultado = auditar(cargar(str(REF_PRE)))
        self.reglas = sorted(h.regla for h in self.resultado.hallazgos)

    def test_rc_1(self):
        self.assertEqual(self.resultado.rc, RC_HALLAZGO)

    def test_hallazgos_exactos(self):
        self.assertEqual(
            self.reglas,
            ["FSM001"] + ["FSM005"] * 4 + ["FSM008"] * 6 + ["FSM010", "FSM011"],
        )

    def test_el_ciclo_es_el_webhook_repetido(self):
        ciclo = [h for h in self.resultado.hallazgos if h.regla == "FSM001"][0]
        self.assertEqual(ciclo.detalle["recurso"], "dinero")
        self.assertEqual(ciclo.detalle["delta_neto"], 69900)
        self.assertEqual(ciclo.camino, ("P2",), "P2 es 'pagar' desde 'pagado'")

    def test_el_dinero_sale_de_un_pedido_que_nunca_entro(self):
        """'enviar' sin guarda deja embarcar un pedido impago y reembolsarlo."""
        negativo = [h for h in self.resultado.hallazgos if h.regla == "FSM010"][0]
        self.assertEqual(negativo.detalle["saldo"], -69900)
        self.assertEqual(negativo.camino, ("E1", "R3"))

    def test_una_guarda_sola_no_salva_el_grafo(self):
        """'marcarDevuelto' guarda su origen y aun asi entra en el ciclo: la fuga
        la abre el escritor vecino."""
        self.assertTrue(any(h.regla == "FSM008" and "R3" in h.transiciones for h in self.resultado.hallazgos))


class ReferenciaPostFixTest(unittest.TestCase):
    """Cada escritor declara su origen; el mismo motor no cambia una linea."""

    def setUp(self):
        self.grafo = cargar(str(REF_POST))
        self.resultado = auditar(self.grafo)

    def test_rc_0(self):
        self.assertEqual(self.resultado.rc, RC_LIMPIO)

    def test_la_conservacion_se_cierra(self):
        self.assertTrue(self.resultado.medicion.cerrada)
        self.assertEqual(self.resultado.medicion.frontera, 0)

    def test_una_arista_por_origen_declarado(self):
        self.assertEqual(
            sorted((t.evento, t.de, t.a) for t in self.grafo.transiciones),
            [
                ("cancelar", "nuevo", "cancelado"),
                ("enviar", "pagado", "enviado"),
                ("pagar", "nuevo", "pagado"),
                ("reembolsar", "enviado", "devuelto"),
                ("reembolsar", "pagado", "devuelto"),
            ],
        )

    def test_ningun_terminal_retiene_importe(self):
        saldo, cambio = {self.grafo.inicial: 0}, True
        while cambio:
            cambio = False
            for t in self.grafo.transiciones:
                if t.de in saldo and t.a not in saldo:
                    saldo[t.a] = saldo[t.de] + t.delta.get("dinero", 0)
                    cambio = True
        for nombre, estado in self.grafo.estados.items():
            if estado.terminal:
                self.assertEqual(saldo.get(nombre), 0, nombre)


class VerificabilidadTest(unittest.TestCase):
    """La procedencia es una cita: cada linea publicada tiene que resolver."""

    def setUp(self):
        self.docs = {
            arbol: json.loads(ruta.read_text(encoding="utf-8"))
            for arbol, ruta in (("pre_fix", REF_PRE), ("post_fix", REF_POST))
        }

    def test_se_declara_verificable_publicamente(self):
        for arbol, doc in self.docs.items():
            procedencia = doc["procedencia"]
            self.assertTrue(procedencia["verificable_publicamente"], arbol)
            self.assertTrue(procedencia["medido"], arbol)
            self.assertEqual(procedencia["repo"], "alexisromtz-lab/fsm-ledger-guard", arbol)

    def test_cada_fuente_apunta_a_una_escritura_real(self):
        for arbol, doc in self.docs.items():
            procedencia = doc["procedencia"]
            for fuente in procedencia["fuentes"]:
                archivo = EJEMPLO / arbol / fuente["archivo"]
                self.assertTrue(archivo.is_file(), archivo)
                linea = archivo.read_text(encoding="utf-8").splitlines()[fuente["linea"] - 1]
                self.assertIn("SET estado", linea, f"{archivo}:{fuente['linea']}")
                self.assertIn(fuente["funcion"], " ".join(
                    archivo.read_text(encoding="utf-8").splitlines()[: fuente["linea"]]
                ))

    def test_la_huella_es_la_de_las_fuentes_no_la_del_reloj(self):
        for arbol, ruta in (("pre_fix", REF_PRE), ("post_fix", REF_POST)):
            with self.subTest(arbol=arbol):
                primera = extraer.derivar(EJEMPLO, arbol)
                segunda = extraer.derivar(EJEMPLO, arbol)
                self.assertEqual(primera, segunda)
                self.assertEqual(primera["procedencia"]["commit"],
                                 extraer.derivar(EJEMPLO, arbol)["procedencia"]["commit"])


class FailClosedTest(unittest.TestCase):
    """Lo que el extractor no puede leer no se omite: se declara NO_MEDIDO."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.raiz = Path(self._tmp.name) / "ecommerce_referencia"
        shutil.copytree(EJEMPLO, self.raiz)

    def _falla(self, arbol="pre_fix"):
        with self.assertRaises(extraer.ErrorExtraccion) as ctx:
            extraer.derivar(self.raiz, arbol)
        self.assertEqual(ctx.exception.rc, extraer.RC_NO_MEDIDO)
        return ctx.exception.motivo

    def test_un_escritor_sin_declarar_no_produce_fixture(self):
        Webhook = self.raiz / "pre_fix" / "src" / "webhook.js"
        Webhook.write_text(
            Webhook.read_text(encoding="utf-8")
            + "\nexport async function borrarPedido(db, id) {\n"
            '  const sql = "UPDATE pedidos SET estado = \'cancelado\' WHERE pedido_id = ?";\n'
            "  await db.prepare(sql).bind(id).run();\n}\n",
            encoding="utf-8",
        )
        motivo = self._falla()
        self.assertIn("src/webhook.js::borrarPedido", motivo)

    def test_una_guarda_ilegible_no_produce_fixture(self):
        Webhook = self.raiz / "post_fix" / "src" / "webhook.js"
        Webhook.write_text(
            Webhook.read_text(encoding="utf-8").replace(
                "AND estado IN ('pagado')", "AND estado <> 'nuevo'"
            ),
            encoding="utf-8",
        )
        motivo = self._falla("post_fix")
        self.assertIn("src/webhook.js:12", motivo)
        self.assertIn("estado <> 'nuevo'", motivo)

    def test_una_declaracion_sin_codigo_no_produce_fixture(self):
        panel = self.raiz / "pre_fix" / "src" / "panel.js"
        panel.write_text("// el boton se retiro\n", encoding="utf-8")
        motivo = self._falla()
        self.assertIn("src/panel.js::cancelarPedido", motivo)

    def test_el_origen_lo_lee_del_codigo(self):
        Webhook = self.raiz / "post_fix" / "src" / "webhook.js"
        Webhook.write_text(
            Webhook.read_text(encoding="utf-8").replace(
                "AND estado IN ('pagado')", "AND estado IN ('nuevo')"
            ),
            encoding="utf-8",
        )
        doc = extraer.derivar(self.raiz, "post_fix")
        enviar = [t for t in doc["transiciones"] if t["evento"] == "enviar"]
        self.assertEqual([(t["de"], t["a"]) for t in enviar], [("nuevo", "enviado")])


if __name__ == "__main__":
    unittest.main()
