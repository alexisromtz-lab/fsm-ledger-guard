"""Interoperabilidad real: ``conservation-ledger`` rehace la resta del recibo.

No se simula el verificador: se importa el publicado. Si no está en la máquina,
el test se salta en vez de fingir que pasó.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from contexto import FIXTURES

from fsm_ledger_guard.checks import auditar
from fsm_ledger_guard.dsl import cargar
from fsm_ledger_guard.report import a_recibo

CONSERVATION_LEDGER = Path.home() / "conservation-ledger" / "src"

try:  # pragma: no cover - depende de la máquina
    sys.path.insert(0, str(CONSERVATION_LEDGER))
    from conservation_ledger import esquema, verificador
except ImportError:  # pragma: no cover
    esquema = verificador = None


FIXTURES_PUBLICOS = ("studio_city_pre_fix", "studio_city_post_fix", "studio_city_objetivo")


def recibo_de(nombre):
    resultado = auditar(cargar(str(FIXTURES / f"{nombre}.json")))
    return resultado, a_recibo(resultado)


@unittest.skipIf(esquema is None, "conservation-ledger no está en esta máquina")
class InteropTest(unittest.TestCase):
    def test_el_verificador_acepta_el_recibo(self):
        for nombre in FIXTURES_PUBLICOS:
            with self.subTest(nombre):
                _, recibo = recibo_de(nombre)
                esquema.desde_documento(recibo)

    def test_la_particion_se_rehace_en_cero(self):
        for nombre in FIXTURES_PUBLICOS:
            with self.subTest(nombre):
                _, recibo = recibo_de(nombre)
                veredicto = verificador.verificar(esquema.desde_documento(recibo))
                self.assertEqual(veredicto.clase, "CONSERVADO")
                self.assertEqual(veredicto.rc, 0)
                self.assertEqual(veredicto.residuo, 0)
                self.assertTrue(veredicto.conserva)
                self.assertFalse(veredicto.defectuoso)

    def test_el_rc_de_la_auditoria_viaja_fuera_del_veredicto(self):
        for nombre in FIXTURES_PUBLICOS:
            with self.subTest(nombre):
                resultado, recibo = recibo_de(nombre)
                veredicto = verificador.verificar(esquema.desde_documento(recibo))
                self.assertEqual(recibo["auditoria"]["rc"], resultado.rc)
                self.assertEqual(veredicto.declarado_rc, 0)

    def test_declarar_el_rc_de_auditoria_romperia_el_recibo(self):
        # esto es lo que se evita: 2 y 4 significan VACIO y RUPTURA en la otra escala
        _, recibo = recibo_de("studio_city_pre_fix")
        saboteado = dict(recibo, declarado={"conserva": True, "rc": 4})
        veredicto = verificador.verificar(esquema.desde_documento(saboteado))
        self.assertEqual(veredicto.clase, "DISCREPANCIA")
        self.assertEqual(veredicto.rc, 4)

    def test_una_transicion_sin_cubeta_es_ruptura(self):
        _, recibo = recibo_de("studio_city_post_fix")
        roto = dict(recibo, cubetas=dict(recibo["cubetas"], limpias=recibo["cubetas"]["limpias"] - 1))
        veredicto = verificador.verificar(esquema.desde_documento(roto))
        self.assertEqual(veredicto.clase, "RUPTURA")
        self.assertEqual(veredicto.residuo, 1)


if __name__ == "__main__":
    unittest.main()
