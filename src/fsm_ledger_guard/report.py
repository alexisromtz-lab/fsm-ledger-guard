"""Salidas del auditor: SARIF 2.1.0, recibo ``conservation/1`` y resumen humano.

El recibo no declara su propio veredicto: publica los términos (``dominio`` y
``cubetas``) y deja que ``conservation-ledger`` recompute la resta. ``declarado``
viaja sólo para que el verificador pueda marcar ``DISCREPANCIA`` si el productor
se contradice a sí mismo.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .checks import REGLAS, Hallazgo, Resultado
from .dsl import Grafo

ESQUEMA_SARIF = "https://json.schemastore.org/sarif-2.1.0.json"
ESQUEMA_RECIBO = "conservation/1"
INSTRUMENTO = "fsm-ledger-guard"

CUBETAS = (
    "limpias",
    "en_ciclo_fuga",
    "inalcanzable",
    "sin_guarda",
    "unidad_inconsistente",
)


def clasificar(resultado: Resultado) -> Dict[str, int]:
    """Partición de transiciones por primera causa, en orden de prioridad.

    Prioridad: un ciclo con fuga define el saldo de toda su componente, así que
    se nombra antes que cualquier otro defecto de la misma arista. El recorrido
    es exhaustivo: una transición que no case con ningún defecto cae en
    ``limpias``, y esa es la única forma de que la suma cierre.
    """
    en_ciclo: set = set()
    inalcanzables: set = set()
    sin_guarda: set = set()
    mala_unidad: set = set()
    for h in resultado.hallazgos:
        if h.clase == "CICLO_CON_FUGA":
            en_ciclo.update(h.detalle.get("aristas_scc", ()))
        elif h.clase == "TRANSICION_INALCANZABLE":
            inalcanzables.update(h.transiciones)
        elif h.clase in ("MOVIMIENTO_NO_ATOMICO", "MOVIMIENTO_SIN_IDEM"):
            sin_guarda.update(h.transiciones)
        elif h.clase == "UNIDAD_INCONSISTENTE":
            mala_unidad.update(h.transiciones)

    cubetas = {nombre: 0 for nombre in CUBETAS}
    for t in resultado.grafo.transiciones:
        if t.id in en_ciclo:
            cubetas["en_ciclo_fuga"] += 1
        elif t.id in inalcanzables:
            cubetas["inalcanzable"] += 1
        elif t.id in sin_guarda:
            cubetas["sin_guarda"] += 1
        elif t.id in mala_unidad:
            cubetas["unidad_inconsistente"] += 1
        else:
            cubetas["limpias"] += 1
    return cubetas


def a_recibo(resultado: Resultado) -> Dict[str, Any]:
    grafo = resultado.grafo
    cubetas = clasificar(resultado)
    dominio = len(grafo.transiciones)
    cuerpo = {
        "hallazgos": [h.a_dict() for h in resultado.hallazgos],
        "medicion": {
            "profundidad": resultado.medicion.profundidad,
            "aplicaciones": resultado.medicion.aplicaciones,
            "estados_de_saldo": resultado.medicion.estados_de_saldo,
            "frontera": resultado.medicion.frontera,
            "cerrada": resultado.medicion.cerrada,
        },
        "cobertura": resultado.cobertura,
        "rc": resultado.rc,
    }
    salida = hashlib.sha256(
        json.dumps(cuerpo, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    conserva = sum(cubetas.values()) == dominio
    return {
        "schema": ESQUEMA_RECIBO,
        "area": f"fsm:{grafo.dominio}",
        "instrumento": INSTRUMENTO,
        "dominio": dominio,
        "unidad": "transiciones",
        "cubetas": cubetas,
        "version": __version__,
        "digests": {"entrada": grafo.huella(), "salida": salida},
        # ``declarado`` responde a la identidad de la particion, no a la salud de
        # la maquina: en la escala de conservation-ledger 2 y 4 significan VACIO y
        # RUPTURA, asi que publicar aqui el RC de la auditoria haria que el
        # verificador marque DISCREPANCIA sobre una particion que si cierra. El RC
        # de la auditoria viaja en ``auditoria``, que el verificador no lee.
        "declarado": {"conserva": conserva, "rc": 0 if conserva else 4},
        "auditoria": {
            "rc": resultado.rc,
            "hallazgos": len(resultado.hallazgos),
            "reglas": sorted({h.regla for h in resultado.hallazgos}),
            "medido": grafo.medido,
        },
        "procedencia": grafo.procedencia,
    }


def _fingerprint(h: Hallazgo) -> str:
    semilla = json.dumps(
        [h.regla, list(h.transiciones), list(h.estados), h.detalle.get("recurso", "")],
        sort_keys=True,
    )
    return hashlib.sha256(semilla.encode("utf-8")).hexdigest()[:16]


def _uri(fixture: str) -> str:
    ruta = os.path.abspath(fixture)
    relativa = os.path.relpath(ruta, os.getcwd())
    if relativa.startswith(".."):
        return "file://" + ruta
    return relativa.replace(os.sep, "/")


def a_sarif(resultado: Resultado, fixture: Optional[str] = None) -> Dict[str, Any]:
    grafo = resultado.grafo
    fixture = fixture or grafo.fuente
    usadas = sorted({h.regla for h in resultado.hallazgos})
    reglas = [
        {
            "id": regla,
            "name": REGLAS[regla]["clase"],
            "shortDescription": {"text": REGLAS[regla]["titulo"]},
            "fullDescription": {"text": REGLAS[regla]["ayuda"]},
            "help": {"text": REGLAS[regla]["ayuda"]},
            "defaultConfiguration": {"level": REGLAS[regla]["severidad"]},
            "properties": {
                "tags": ["fsm", "financial-conservation", "money"],
                "precision": "very-high",
            },
        }
        for regla in usadas
    ]
    resultados = [
        {
            "ruleId": h.regla,
            "ruleIndex": usadas.index(h.regla),
            "level": h.severidad,
            "message": {"text": h.mensaje},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": _uri(fixture)},
                        "region": {"startLine": max(1, h.linea)},
                    }
                }
            ],
            "partialFingerprints": {"fsmLedgerGuard/v1": _fingerprint(h)},
            "properties": {
                "clase": h.clase,
                "transiciones": list(h.transiciones),
                "estados": list(h.estados),
                "contraejemplo": list(h.camino),
                "detalle": h.detalle,
            },
        }
        for h in resultado.hallazgos
    ]
    return {
        "$schema": ESQUEMA_SARIF,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": INSTRUMENTO,
                        "version": __version__,
                        "informationUri": "https://github.com/alexisromtz-lab/fsm-ledger-guard",
                        "rules": reglas,
                    }
                },
                "invocations": [
                    {
                        "executionSuccessful": resultado.rc in (0, 1, 2),
                        "properties": {"rc": resultado.rc, "cobertura": resultado.cobertura},
                    }
                ],
                "results": resultados,
                "properties": {
                    "dominio": grafo.dominio,
                    "huella_del_grafo": grafo.huella(),
                },
            }
        ],
    }


def resumen(resultado: Resultado) -> str:
    grafo = resultado.grafo
    lineas: List[str] = []
    lineas.append(f"dominio   {grafo.dominio}")
    lineas.append(
        f"procedencia {grafo.procedencia.get('fuente', '?')} @ "
        f"{grafo.procedencia.get('commit', '?')}"
        + ("" if grafo.medido else "   [PROYECCIÓN · NO MEDIDO]")
    )
    lineas.append(f"grafo     {len(grafo.estados)} estados · "
                  f"{len(grafo.transiciones)} transiciones · huella {grafo.huella()[:16]}")
    if resultado.hallazgos:
        lineas.append("")
        for h in resultado.hallazgos:
            camino = " → ".join(h.camino) if h.camino else ""
            lineas.append(f"[{h.regla}] {h.severidad:7} {h.clase}")
            lineas.append(f"          {h.mensaje}")
            if camino:
                lineas.append(f"          contraejemplo: {camino}")
            lineas.append(f"          {grafo.fuente}:{h.linea}")
    else:
        lineas.append("")
        lineas.append("sin hallazgos")
    lineas.append("")
    m = resultado.medicion
    lineas.append(
        f"conservación {m.estados_de_saldo} estados de saldo · {m.aplicaciones} aplicaciones · "
        f"profundidad {m.profundidad} · frontera {m.frontera} · "
        f"{'cerrada' if m.cerrada else 'ABIERTA'}"
    )
    for nombre, estado in sorted(resultado.cobertura.items()):
        lineas.append(f"  cobertura {nombre}: {estado}")
    lineas.append(f"RC {resultado.rc}")
    return "\n".join(lineas)


def escribir(doc: Dict[str, Any], ruta: str | Path) -> Path:
    destino = Path(ruta)
    if destino.parent and not destino.parent.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8"
    )
    return destino
