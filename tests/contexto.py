"""Bootstrap de los tests: pone ``src/`` en el camino de importación.

Se importa antes que el paquete para que ``python -m unittest discover -s tests``
y ``pytest`` encuentren ``fsm_ledger_guard`` sin instalar nada.
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SRC = RAIZ / "src"
FIXTURES = RAIZ / "tests" / "fixtures"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def documento(
    transiciones: Iterable[Sequence[Any]],
    estados: Iterable[Tuple[str, bool]],
    recursos: Optional[Dict[str, Dict[str, Any]]] = None,
    inicial: str = "a",
    medido: bool = True,
) -> Dict[str, Any]:
    """Documento ``fsm-ledger/1`` mínimo para los tests unitarios."""
    return {
        "schema": "fsm-ledger/1",
        "dominio": "test/sintetico",
        "inicial": inicial,
        "procedencia": {"repo": "test", "commit": "test", "medido": medido},
        "recursos": recursos
        or {"saldo": {"unidad": "unidades", "minimo": 0, "maximo": None, "saldo_inicial": 0}},
        "estados": [{"nombre": n, "terminal": t} for n, t in estados],
        "transiciones": [
            {
                "id": t[0],
                "de": t[1],
                "evento": "evento",
                "a": t[2],
                "delta": dict(t[3]),
                "atomico": t[4] if len(t) > 4 else True,
                "idem_key": t[5] if len(t) > 5 else "k",
            }
            for t in transiciones
        ],
    }


def texto(doc: Dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False)


def cargar_texto(doc: Dict[str, Any]):
    from fsm_ledger_guard.dsl import desde_texto

    return desde_texto(texto(doc), fuente="test")
