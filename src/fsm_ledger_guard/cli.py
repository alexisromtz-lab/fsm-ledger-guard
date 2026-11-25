"""Interfaz de línea de comandos.

Escalera de salida, la misma que el resto de la suite:

===  =================================================================
0    limpio: sin hallazgos y conservación medida
1    hallazgos
2    NO_MEDIDO: la exploración no cerró dentro de la profundidad pedida
4    uso: el fixture no es ``fsm-ledger/1`` legible, o los argumentos no
     cuadran
===  =================================================================
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional, Sequence

from . import __version__
from .checks import RC_USO, auditar, combinar
from .dsl import ErrorDSL, cargar
from .report import a_recibo, a_sarif, escribir, resumen


class _Parser(argparse.ArgumentParser):
    """``argparse`` sale con 2 en un error de uso; aquí 2 es NO_MEDIDO."""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(RC_USO)


def construir_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="fsm-ledger-guard",
        description="Audita la conservación de una máquina de estados financiera declarada.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="comando", metavar="comando")

    scan = sub.add_parser(
        "scan",
        aliases=["auditar"],
        help="audita un fixture fsm-ledger/1",
        description="Audita un fixture y emite hallazgos, SARIF y recibo.",
    )
    scan.add_argument(
        "fixtures",
        nargs="+",
        metavar="fixture",
        help="uno o más documentos fsm-ledger/1",
    )
    scan.add_argument(
        "--depth",
        type=int,
        default=8,
        metavar="K",
        help="profundidad de la conservación acotada (por omisión 8)",
    )
    scan.add_argument("--sarif", metavar="RUTA", help="escribe el log SARIF 2.1.0")
    scan.add_argument("--recibo", metavar="RUTA", help="escribe el recibo conservation/1")
    scan.add_argument(
        "--exigir-medido",
        action="store_true",
        help="trata una procedencia no medida como NO_MEDIDO (RC 2)",
    )
    scan.add_argument("--json", action="store_true", dest="como_json", help="salida JSON")
    scan.add_argument("--quiet", "-q", action="store_true", help="no imprime el resumen")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "comando", None):
        parser.print_help()
        return RC_USO
    if args.depth < 1:
        print("fsm-ledger-guard: error: --depth debe ser >= 1", file=sys.stderr)
        return RC_USO

    if len(args.fixtures) > 1 and (args.sarif or args.recibo):
        print(
            "fsm-ledger-guard: error: --sarif y --recibo emiten un artefacto por "
            "corrida; audita los fixtures de uno en uno",
            file=sys.stderr,
        )
        return RC_USO

    codigos: List[int] = []
    for fixture in args.fixtures:
        codigos.append(_auditar_uno(fixture, args))
    return combinar(*codigos)


def _auditar_uno(fixture: str, args: argparse.Namespace) -> int:
    try:
        grafo = cargar(fixture)
    except ErrorDSL as e:
        print(f"fsm-ledger-guard: {e}", file=sys.stderr)
        return RC_USO

    resultado = auditar(grafo, profundidad=args.depth, exigir_medido=args.exigir_medido)

    if args.como_json:
        print(
            json.dumps(
                {
                    "dominio": grafo.dominio,
                    "rc": resultado.rc,
                    "huella": grafo.huella(),
                    "hallazgos": [h.a_dict() for h in resultado.hallazgos],
                    "medicion": {
                        "profundidad": resultado.medicion.profundidad,
                        "estados_de_saldo": resultado.medicion.estados_de_saldo,
                        "aplicaciones": resultado.medicion.aplicaciones,
                        "frontera": resultado.medicion.frontera,
                        "cerrada": resultado.medicion.cerrada,
                    },
                    "cobertura": resultado.cobertura,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    elif not args.quiet:
        print(resumen(resultado))

    # ``--quiet`` calla el resumen, no el acto: los artefactos se anuncian
    # siempre, porque son lo que el usuario pidio
    if args.sarif:
        ruta = escribir(a_sarif(resultado, fixture), args.sarif)
        print(f"sarif  {ruta} ({len(resultado.hallazgos)} resultados)")
    if args.recibo:
        ruta = escribir(a_recibo(resultado), args.recibo)
        print(f"recibo {ruta}")

    return resultado.rc
