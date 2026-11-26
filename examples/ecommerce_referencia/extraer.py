#!/usr/bin/env python3
"""Codigo -> ``fsm-ledger/1``: el fixture del ejemplo publico se deriva, no se transcribe.

Lee las sentencias ``UPDATE <tabla> SET estado = '<destino>' [WHERE ...]`` de los
manejadores JS de un arbol y deriva el origen de cada arista de la guarda que el
**codigo** escribe. Un escritor sin guarda se expande a una arista desde cada
estado declarado --terminales incluidos--: eso es lo que el codigo permite, no lo
que su autor queria.

Alcance declarado (lo que el extractor **no** mide):

* sentencias SQL de una sola linea dentro de una funcion nombrada del archivo;
* guardas con la forma ``estado = '<literal>'`` o ``estado IN ('<literal>', ...)``.

Cualquier otra forma se declara ``NO_MEDIDO`` (RC 2) nombrando archivo y linea,
en vez de omitirse: una escritura que no se ve no es una escritura que no existe.

Escalera de salida, propia y distinta de la del motor:

===  =================================================================
0    el fixture derivado se escribio (o coincide con el commiteado)
1    ``--check``: el archivo commiteado no es lo que el codigo produce
2    NO_MEDIDO: hay una escritura o una declaracion que no se puede leer
4    uso: argumentos, o ``maquina.json`` que no cuadra con el codigo
===  =================================================================
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

RAIZ = Path(__file__).resolve().parent
ESQUEMA_MAQUINA = "ejemplo-declarado/1"

RC_OK = 0
RC_DESFASE = 1
RC_NO_MEDIDO = 2
RC_USO = 4

_FUNCION = re.compile(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(")
_ESCRITURA = re.compile(r"UPDATE\s+(\w+)\s+SET\s+estado\s*=\s*'([^']*)'([^\"\n]*)")
_GUARDA_IN = re.compile(r"\bestado\s+IN\s*\(([^)]*)\)")
_GUARDA_IGUAL = re.compile(r"\bestado\s*=\s*'([^']*)'")
_MENCION_ESTADO = re.compile(r"\bestado\b")
_LITERAL = re.compile(r"'([^']*)'")

_NOTAS = {
    "sin guarda": (
        "escritor sin guarda de origen: la arista existe desde cualquier estado "
        "declarado, incluidos los terminales"
    ),
}


class ErrorExtraccion(Exception):
    """No se puede derivar el grafo: se declara, no se rellena."""

    def __init__(self, motivo: str, rc: int = RC_NO_MEDIDO) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.rc = rc


@dataclass(frozen=True)
class Escritor:
    archivo: str
    linea: int
    funcion: str
    destino: str
    origenes: Optional[Tuple[str, ...]]
    guarda: str

    @property
    def clave(self) -> str:
        return f"{self.archivo}::{self.funcion}"


def leer_escritores(arbol: Path) -> List[Escritor]:
    if not arbol.is_dir():
        raise ErrorExtraccion(f"{arbol}: el arbol no existe", RC_USO)
    escritores: List[Escritor] = []
    for ruta in sorted(arbol.rglob("*.js")):
        rel = ruta.relative_to(arbol).as_posix()
        funcion: Optional[str] = None
        for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
            encontrada = _FUNCION.search(linea)
            if encontrada:
                funcion = encontrada.group(1)
            if "SET estado" not in linea:
                continue
            m = _ESCRITURA.search(linea)
            if m is None:
                raise ErrorExtraccion(
                    f"{rel}:{numero}: hay 'SET estado' y el extractor no sabe leer la "
                    "sentencia (fuera de alcance: SQL en varias lineas, delimitador que "
                    "no es '\"' o tabla/columna compuesta)"
                )
            if funcion is None:
                raise ErrorExtraccion(
                    f"{rel}:{numero}: escritura fuera de una funcion nombrada; el "
                    "declarante no puede nombrarla en maquina.json"
                )
            cola = m.group(3)
            dentro = _GUARDA_IN.search(cola)
            igual = _GUARDA_IGUAL.search(cola)
            if dentro and igual:
                raise ErrorExtraccion(
                    f"{rel}:{numero}: la misma sentencia usa 'estado IN (...)' y "
                    "'estado = ...': no hay una sola guarda que declarar"
                )
            if dentro:
                origenes = tuple(
                    sorted({literal for literal in _LITERAL.findall(dentro.group(1))})
                )
                guarda = f"estado IN ({dentro.group(1).strip()})"
            elif igual:
                origenes = (igual.group(1),)
                guarda = f"estado = '{igual.group(1)}'"
            elif _MENCION_ESTADO.search(cola):
                fragmento = " ".join(cola.split())[:90]
                raise ErrorExtraccion(
                    f"{rel}:{numero}: el WHERE menciona 'estado' pero no como "
                    "'= <literal>' ni 'IN (...)': el origen no se mide "
                    f"(lei: {fragmento!r})"
                )
            else:
                origenes = None
                guarda = "sin guarda"
            escritores.append(
                Escritor(
                    archivo=rel,
                    linea=numero,
                    funcion=funcion,
                    destino=m.group(2),
                    origenes=origenes,
                    guarda=guarda,
                )
            )
    if not escritores:
        raise ErrorExtraccion(f"{arbol}: no hay ninguna escritura de estado que leer")
    return escritores


def _huella_fuentes(raiz: Path, arbol: str, maquina: Dict[str, Any]) -> str:
    materiales: Dict[str, Any] = {
        "fuentes": {
            ruta.relative_to(raiz / arbol).as_posix(): hashlib.sha256(
                ruta.read_bytes()
            ).hexdigest()
            for ruta in sorted((raiz / arbol).rglob("*.js"))
        },
        "inicial": maquina["inicial"],
        "estados": maquina["estados"],
        "recursos": maquina["recursos"],
        "eventos": maquina["eventos"],
        "escritores": maquina["escritores"][arbol],
    }
    canonico = json.dumps(materiales, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def derivar(raiz: Path, arbol: str) -> Dict[str, Any]:
    """Devuelve el documento ``fsm-ledger/1`` que el codigo de ``arbol`` afirma."""
    ruta_maquina = raiz / "maquina.json"
    try:
        maquina = json.loads(ruta_maquina.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ErrorExtraccion(f"{ruta_maquina}: no se pudo leer ({e})", RC_USO) from e
    if maquina.get("schema") != ESQUEMA_MAQUINA:
        raise ErrorExtraccion(
            f"{ruta_maquina}: schema {maquina.get('schema')!r} no es {ESQUEMA_MAQUINA!r}", RC_USO
        )

    estados = [estado["nombre"] for estado in maquina["estados"]]
    declarados = maquina["escritores"].get(arbol)
    if not isinstance(declarados, dict) or not declarados:
        raise ErrorExtraccion(f"{ruta_maquina}: no declara escritores para {arbol!r}", RC_USO)

    escritores = leer_escritores(raiz / arbol)
    claves = [e.clave for e in escritores]
    repetidas = sorted({clave for clave in claves if claves.count(clave) > 1})
    if repetidas:
        raise ErrorExtraccion(
            "dos escrituras de estado en la misma funcion: " + ", ".join(repetidas)
        )
    sin_declarar = sorted(set(claves) - set(declarados))
    if sin_declarar:
        raise ErrorExtraccion(
            "escritor en el codigo que maquina.json no declara: " + ", ".join(sin_declarar)
        )
    sin_codigo = sorted(set(declarados) - set(claves))
    if sin_codigo:
        raise ErrorExtraccion(
            "declaracion en maquina.json sin escritor en el codigo: " + ", ".join(sin_codigo)
        )

    transiciones: List[Dict[str, Any]] = []
    fuentes: List[Dict[str, Any]] = []
    vistos: Dict[str, str] = {}
    for escritor in escritores:
        declaracion = declarados[escritor.clave]
        evento = declaracion["evento"]
        if evento not in maquina["eventos"]:
            raise ErrorExtraccion(
                f"{escritor.clave}: el evento {evento!r} no esta declarado en 'eventos'", RC_USO
            )
        if escritor.destino not in estados:
            raise ErrorExtraccion(
                f"{escritor.archivo}:{escritor.linea}: destino {escritor.destino!r} no es un "
                "estado declarado"
            )
        origenes = (
            list(escritor.origenes) if escritor.origenes is not None else list(estados)
        )
        ajenos = [origen for origen in origenes if origen not in estados]
        if ajenos:
            raise ErrorExtraccion(
                f"{escritor.archivo}:{escritor.linea}: la guarda nombra estados no "
                f"declarados: {', '.join(sorted(ajenos))}"
            )
        letra = maquina["eventos"][evento]["letra"]
        delta = maquina["eventos"][evento]["delta"]
        for origen in sorted(origenes, key=estados.index):
            tid = f"{letra}{estados.index(origen) + 1}"
            if tid in vistos:
                raise ErrorExtraccion(
                    f"{tid}: dos aristas con el mismo id ({vistos[tid]} y {escritor.clave})"
                )
            vistos[tid] = escritor.clave
            transicion: Dict[str, Any] = {
                "id": tid,
                "de": origen,
                "evento": evento,
                "a": escritor.destino,
                "delta": dict(delta),
                "atomico": bool(declaracion.get("atomico", False)),
                "idem_key": declaracion.get("idem_key"),
            }
            if escritor.guarda in _NOTAS:
                transicion["nota"] = _NOTAS[escritor.guarda]
            transiciones.append(transicion)
        fuentes.append(
            {
                "archivo": escritor.archivo,
                "linea": escritor.linea,
                "funcion": escritor.funcion,
                "evento": evento,
                "guarda": escritor.guarda,
                "origenes": origenes,
            }
        )

    huella = _huella_fuentes(raiz, arbol, maquina)
    return {
        "schema": "fsm-ledger/1",
        "dominio": maquina["dominio"],
        "inicial": maquina["inicial"],
        "procedencia": {
            "repo": maquina["repo"],
            "ruta": f"examples/ecommerce_referencia/{arbol}",
            "verificable_publicamente": True,
            "medido": True,
            "commit": f"huella:{huella[:12]}",
            "huella_fuentes": f"sha256:{huella}",
            "generado_por": "examples/ecommerce_referencia/extraer.py",
            "fuentes": fuentes,
            "nota": (
                "Reduccion publica del patron, no un tercer sistema en produccion: este "
                "arbol es codigo de referencia y existe para que el lector rehaga la "
                "medicion sin pedir acceso a los dos repositorios privados. Ninguna arista "
                "esta declarada a mano: el origen de cada una lo lee "
                "`examples/ecommerce_referencia/extraer.py` de la guarda escrita en el "
                "codigo, y el destino, el delta y la clave de idempotencia, de "
                "`maquina.json`. Un escritor sin guarda se expande a una arista desde cada "
                "estado declarado, terminales incluidos. El fixture se regenera con "
                "`python3 examples/ecommerce_referencia/extraer.py --arbol <arbol> "
                "--salida <ruta> --check`."
            ),
        },
        "recursos": maquina["recursos"],
        "estados": maquina["estados"],
        "transiciones": transiciones,
    }


def serializar(doc: Dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="extraer.py",
        description="Deriva un fixture fsm-ledger/1 del codigo de un arbol del ejemplo.",
    )
    parser.add_argument("--arbol", required=True, help="pre_fix | post_fix")
    parser.add_argument("--salida", required=True, help="ruta del fixture a escribir o comparar")
    parser.add_argument(
        "--check",
        action="store_true",
        help="no escribe: compara el archivo con lo que el codigo produce (RC 1 si difiere)",
    )
    parser.add_argument("--raiz", default=str(RAIZ), help="directorio del ejemplo")
    args = parser.parse_args(argv)

    raiz = Path(args.raiz).resolve()
    try:
        doc = derivar(raiz, args.arbol)
    except ErrorExtraccion as e:
        print(f"NO_MEDIDO: {e.motivo}", file=sys.stderr)
        return e.rc

    texto = serializar(doc)
    destino = Path(args.salida)
    if args.check:
        try:
            actual = destino.read_text(encoding="utf-8")
        except OSError as e:
            print(f"NO_MEDIDO: no se pudo leer {destino}: {e}", file=sys.stderr)
            return RC_NO_MEDIDO
        if actual != texto:
            print(
                f"DESFASE: {destino} no es lo que produce el codigo de {args.arbol}; "
                f"regenera con --salida {destino}",
                file=sys.stderr,
            )
            return RC_DESFASE
        print(f"OK: {destino} coincide con el codigo de {args.arbol}")
        return RC_OK

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    print(
        f"OK: {destino} escrito desde {args.arbol} · "
        f"{len(doc['transiciones'])} transiciones · "
        f"{len(doc['procedencia']['fuentes'])} escritores"
    )
    return RC_OK


if __name__ == "__main__":
    raise SystemExit(main())
