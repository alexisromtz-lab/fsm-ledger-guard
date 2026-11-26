"""Los seis fixtures son la evidencia pública: se afirma su contenido exacto.

Los cuatro primeros son Studio City en cuatro cortes (el delta medido
8 -> 3 -> 1 -> proyección); los otros dos son Moon & Rain, el segundo vertical:
un e-commerce en el mismo HEAD, antes y después de la guarda de origen.

Si un fixture cambia porque el motor cambió de criterio, este test lo dice antes
de que el cambio llegue al README.
"""
from __future__ import annotations

import unittest

from contexto import FIXTURES

from fsm_ledger_guard.checks import RC_HALLAZGO, RC_LIMPIO, RC_NO_MEDIDO, auditar
from fsm_ledger_guard.dsl import cargar

PRE = FIXTURES / "studio_city_pre_fix.json"
POST = FIXTURES / "studio_city_post_fix.json"
F7 = FIXTURES / "studio_city_f7.json"
OBJETIVO = FIXTURES / "studio_city_objetivo.json"
TIENDA_PRE = FIXTURES / "moon_and_rain_pre_fix.json"
TIENDA_POST = FIXTURES / "moon_and_rain_post_fix.json"


def auditar_archivo(ruta, **kwargs):
    return auditar(cargar(str(ruta)), **kwargs)


class StudioCityPreFixTest(unittest.TestCase):
    """HEAD 95ea4a71: el dinero se puede cobrar dos veces y nadie lo suelta."""

    def setUp(self):
        self.resultado = auditar_archivo(PRE)
        self.reglas = sorted(h.regla for h in self.resultado.hallazgos)

    def test_rc_1(self):
        self.assertEqual(self.resultado.rc, RC_HALLAZGO)

    def test_hallazgos_exactos(self):
        self.assertEqual(
            self.reglas,
            ["FSM001", "FSM001", "FSM006", "FSM008", "FSM008", "FSM009", "FSM009", "FSM011"],
        )

    def test_el_ciclo_es_el_de_dos_aristas(self):
        ciclos = [h for h in self.resultado.hallazgos if h.regla == "FSM001"]
        self.assertEqual(len(ciclos), 2)
        for ciclo in ciclos:
            self.assertEqual(set(ciclo.camino), {"P3", "P9"})
        self.assertEqual(
            sorted(c.detalle["recurso"] for c in ciclos), ["cupo", "escrow"]
        )
        escrow = [c for c in ciclos if c.detalle["recurso"] == "escrow"][0]
        self.assertEqual(escrow.detalle["delta_neto"], 350)

    def test_el_dinero_no_tiene_salida(self):
        retenido = [h for h in self.resultado.hallazgos if h.regla == "FSM006"]
        self.assertEqual(len(retenido), 1)
        self.assertEqual(retenido[0].detalle["recurso"], "escrow")
        self.assertEqual(retenido[0].detalle["alcance"], "global")

    def test_mezcla_de_unidades_en_la_misma_columna(self):
        unidades = [h for h in self.resultado.hallazgos if h.regla == "FSM009"]
        self.assertEqual({h.detalle["unidad_declarada"] for h in unidades}, {"pesos"})
        self.assertEqual({h.detalle["unidad_del_recurso"] for h in unidades}, {"centavos"})

    def test_la_retencion_por_estado_queda_no_medida(self):
        self.assertIn("NO_MEDIDO", self.resultado.cobertura["retencion:cupo"])

    def test_procedencia(self):
        grafo = cargar(str(PRE))
        self.assertEqual(grafo.procedencia["commit"], "95ea4a71")
        self.assertTrue(grafo.medido)


class StudioCityPostFixTest(unittest.TestCase):
    """HEAD e67b9d5a: ciclo cerrado y unidades normalizadas; falta la idempotencia."""

    def setUp(self):
        self.resultado = auditar_archivo(POST)
        self.reglas = sorted(h.regla for h in self.resultado.hallazgos)

    def test_rc_1_porque_falta_idem_en_el_cobro(self):
        self.assertEqual(self.resultado.rc, RC_HALLAZGO)
        self.assertEqual(self.reglas, ["FSM006", "FSM008", "FSM008"])

    def test_el_ciclo_desaparecio(self):
        self.assertEqual([h for h in self.resultado.hallazgos if h.regla == "FSM001"], [])

    def test_la_unidad_quedo_uniforme(self):
        self.assertEqual([h for h in self.resultado.hallazgos if h.regla == "FSM009"], [])

    def test_el_dinero_sigue_sin_salida(self):
        retenido = [h for h in self.resultado.hallazgos if h.regla == "FSM006"][0]
        self.assertEqual(retenido.detalle["recurso"], "escrow")

    def test_procedencia(self):
        self.assertEqual(cargar(str(POST)).procedencia["commit"], "e67b9d5a")


class StudioCityF7Test(unittest.TestCase):
    """HEAD 251aaff8: la deuda ya tiene clave de idempotencia; falta la salida."""

    def setUp(self):
        self.grafo = cargar(str(F7))
        self.resultado = auditar(self.grafo)
        self.reglas = sorted(h.regla for h in self.resultado.hallazgos)

    def test_rc_1_con_un_solo_hallazgo(self):
        self.assertEqual(self.resultado.rc, RC_HALLAZGO)
        self.assertEqual(self.reglas, ["FSM006"])

    def test_el_cobro_declara_su_clave_de_idempotencia(self):
        aristas = [t for t in self.grafo.transiciones if t.id in ("P3", "P4")]
        self.assertEqual(len(aristas), 2)
        for arista in aristas:
            self.assertEqual(arista.idem_key, "reserva_id+estudio_id+concepto")

    def test_el_residual_es_el_escrow(self):
        self.assertEqual(self.resultado.hallazgos[0].detalle["recurso"], "escrow")

    def test_es_medido_en_el_commit_del_parche(self):
        self.assertEqual(self.grafo.procedencia["commit"], "251aaff8")
        self.assertTrue(self.grafo.medido)


class StudioCityObjetivoTest(unittest.TestCase):
    """Proyección: lo que haría falta para RC 0. No está medido, y lo dice."""

    def test_rc_0(self):
        self.assertEqual(auditar_archivo(OBJETIVO).rc, RC_LIMPIO)

    def test_bajo_exigir_medido_es_no_medido(self):
        self.assertEqual(auditar_archivo(OBJETIVO, exigir_medido=True).rc, RC_NO_MEDIDO)

    def test_no_se_presenta_como_medido(self):
        self.assertFalse(cargar(str(OBJETIVO)).medido)

    def test_la_diferencia_con_post_fix_es_la_salida_del_dinero(self):
        post = cargar(str(POST))
        objetivo = cargar(str(OBJETIVO))
        self.assertIn("reembolsado", objetivo.estados)
        self.assertNotIn("reembolsado", post.estados)
        # en post-fix ninguna arista saca escrow de pagada: por eso el dinero
        # queda retenido; la proyeccion abre dos salidas, reembolso y servicio
        self.assertEqual([t for t in post.transiciones if t.delta.get("escrow", 0) < 0], [])
        salidas = {
            t.a for t in objetivo.transiciones if t.de == "pagada" and t.delta.get("escrow", 0) < 0
        }
        self.assertEqual(salidas, {"reembolsado", "atendida"})


class MoonAndRainPreFixTest(unittest.TestCase):
    """El mismo HEAD de Moon & Rain: el dinero entra y ninguna arista lo saca.

    El caso no es de pagos: es de pedidos. Sirve porque el defecto es el mismo
    objeto algebraico --un estado alcanzable sin salida que retiene un recurso--
    y el motor no tuvo que cambiar una linea para verlo.
    """

    def setUp(self):
        self.grafo = cargar(str(TIENDA_PRE))
        self.resultado = auditar(self.grafo)
        self.reglas = sorted(h.regla for h in self.resultado.hallazgos)

    def test_rc_1(self):
        self.assertEqual(self.resultado.rc, RC_HALLAZGO)

    def test_los_tres_hallazgos_estructurales(self):
        self.assertEqual(self.reglas, ["FSM002", "FSM004", "FSM006"])

    def test_el_dinero_no_tiene_arista_de_salida(self):
        retenido = [h for h in self.resultado.hallazgos if h.regla == "FSM006"][0]
        self.assertEqual(retenido.detalle["recurso"], "dinero")
        self.assertEqual(retenido.detalle["alcance"], "global")
        self.assertEqual(
            [t.id for t in self.grafo.transiciones if t.delta.get("dinero", 0) < 0], []
        )

    def test_ningun_estado_es_terminal(self):
        self.assertEqual([h.regla for h in self.resultado.hallazgos].count("FSM004"), 1)
        self.assertEqual([n for n, e in self.grafo.estados.items() if e.terminal], [])

    def test_entregado_se_declara_sin_escritor_y_por_eso_es_inalcanzable(self):
        inalcanzable = [h for h in self.resultado.hallazgos if h.regla == "FSM002"][0]
        self.assertIn("entregado", inalcanzable.mensaje)
        self.assertIn("entregado", self.grafo.estados)
        self.assertNotIn("entregado", {t.a for t in self.grafo.transiciones})

    def test_la_regresion_de_estado_es_una_arista_sin_guarda(self):
        """U1 es el reintento de `orders/create` deshaciendo un envio."""
        saltos = [t for t in self.grafo.transiciones if t.id == "U1"][0]
        self.assertEqual((saltos.de, saltos.a), ("en camino", "procesando"))
        self.assertIsNone(saltos.idem_key)

    def test_procedencia(self):
        self.assertEqual(self.grafo.procedencia["commit"], "93f5bcdd")
        self.assertEqual(self.grafo.procedencia["ruta"], "moon-rain-worker")
        self.assertTrue(self.grafo.medido)
        self.assertFalse(self.grafo.procedencia["verificable_publicamente"])


class MoonAndRainPostFixTest(unittest.TestCase):
    """El mismo worker despues de `src/shopify/estados.js`: RC 0 sin tocar el motor."""

    def setUp(self):
        self.grafo = cargar(str(TIENDA_POST))
        self.resultado = auditar(self.grafo)

    def test_rc_0(self):
        self.assertEqual(self.resultado.rc, RC_LIMPIO)

    def test_cero_hallazgos(self):
        self.assertEqual([h.regla for h in self.resultado.hallazgos], [])

    def test_la_regresion_de_estado_desaparece_en_vez_de_quedar_guardada(self):
        self.assertEqual([t for t in self.grafo.transiciones if t.id == "U1"], [])
        guardadas = {(t.de, t.evento) for t in self.grafo.transiciones if t.evento == "orders/create"}
        self.assertEqual(guardadas, {("pendiente_de_registro", "orders/create")})

    def test_el_reembolso_es_la_salida_del_dinero(self):
        salidas = [t for t in self.grafo.transiciones if t.delta.get("dinero", 0) < 0]
        self.assertEqual(sorted(t.id for t in salidas), ["C1", "C2", "R1", "R2"])
        self.assertEqual({t.a for t in self.grafo.transiciones if t.id.startswith("R")}, {"reembolsado"})

    def test_procedencia(self):
        self.assertEqual(self.grafo.procedencia["commit"], "d144256f")
        self.assertEqual(self.grafo.procedencia["ruta"], "moon-rain-worker")
        self.assertTrue(self.grafo.medido)

    def test_todo_terminal_tiene_saldo_cero(self):
        """El invariante que el pre-fix no cumplia: cerrar no retiene importe."""
        saldo = {self.grafo.inicial: 0}
        cambio = True
        while cambio:
            cambio = False
            for t in self.grafo.transiciones:
                if t.de in saldo and t.a not in saldo:
                    saldo[t.a] = saldo[t.de] + t.delta.get("dinero", 0)
                    cambio = True
        for nombre, estado in self.grafo.estados.items():
            if estado.terminal:
                self.assertEqual(saldo.get(nombre), 0, nombre)


class MoonAndRainMismoMotorTest(unittest.TestCase):
    """Dos verticales, un solo conjunto de reglas: no hay rama por dominio."""

    def test_los_dos_dominios_usan_las_mismas_reglas(self):
        ciudad = {h.regla for h in auditar_archivo(PRE).hallazgos}
        tienda = {h.regla for h in auditar_archivo(TIENDA_PRE).hallazgos}
        self.assertIn("FSM006", ciudad & tienda)
        self.assertTrue(tienda)

    def test_el_dominio_no_aparece_en_las_reglas(self):
        """Si una regla nombra un dominio, no es una regla: es un parche."""
        import pathlib

        reglas = (pathlib.Path(__file__).resolve().parents[1] / "src" / "fsm_ledger_guard" / "checks.py")
        texto = reglas.read_text(encoding="utf-8").lower()
        for nombre in ("moon", "rain", "studio", "mascotas", "dental"):
            self.assertNotIn(nombre, texto)


if __name__ == "__main__":
    unittest.main()


class ProcedenciaTest(unittest.TestCase):
    """La procedencia es una cita: tiene que resolver y tiene que poder leerse.

    Medido 2026-11-26: los cuatro fixtures declaraban `alexisromtz-lab/estudios-worker`,
    un repositorio que GitHub no resuelve, y `report.resumen` buscaba `fuente`
    mientras los fixtures declaran `repo`: el resumen imprimia `? @ <commit>`.
    Una procedencia que no se puede verificar publicamente se declara, no se omite.
    """

    def test_el_resumen_imprime_el_repositorio_declarado(self):
        from fsm_ledger_guard.report import resumen

        grafo = cargar(str(PRE))
        linea = [l for l in resumen(auditar_archivo(PRE)).splitlines()
                 if l.startswith("procedencia")]
        self.assertEqual(len(linea), 1)
        self.assertIn(grafo.procedencia["repo"], linea[0])
        self.assertNotIn("procedencia ? ", linea[0])

    def test_el_repositorio_es_el_que_aloja_el_codigo(self):
        for ruta in (PRE, POST, F7, OBJETIVO):
            procedencia = cargar(str(ruta)).procedencia
            self.assertEqual(
                procedencia["repo"], "alexisromtz-lab/letras-delespiritu", ruta.name
            )
            self.assertEqual(procedencia["ruta"], "estudios-worker", ruta.name)

    def test_declara_que_el_repositorio_es_privado(self):
        for ruta in (PRE, POST, F7, OBJETIVO):
            self.assertFalse(
                cargar(str(ruta)).procedencia["verificable_publicamente"], ruta.name
            )

    def test_el_readme_no_publica_salida_que_el_codigo_no_produce(self):
        """El bloque `console` del README es una cita: se compara con la corrida real.

        Medido 2026-11-26: el README mostraba `procedencia alexisromtz-lab/estudios-worker`
        mientras el binario imprimia `procedencia ? @ 95ea4a71`. Documentar una
        salida que no ocurre es la misma falta que citar un blob ajeno.
        """
        from pathlib import Path

        from fsm_ledger_guard.report import resumen

        readme = (FIXTURES.parent.parent / "README.md").read_text(encoding="utf-8")
        for linea in resumen(auditar_archivo(PRE)).splitlines():
            if linea.startswith(("procedencia", "grafo ")):
                self.assertIn(linea, readme)
