"""Lectura, validación y serialización determinista de una máquina de estados
financiera declarada (``fsm-ledger/1``).

El DSL describe **qué** se afirma del flujo de recursos, no **cómo** se comprueba:
una transición es ``(de, evento, a, delta, atomico, idem_key)`` y el delta es un
entero por recurso. Los enteros son deliberados: con punto flotante la identidad
de conservación deja de ser exacta, y una identidad aproximada no certifica nada.

Los valores por omisión son **fail-closed**: una transición que no declara
``atomico`` ni ``idem_key`` se lee como si no los tuviera, para que la omisión se
convierta en hallazgo en vez de en crédito.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ESQUEMA = "fsm-ledger/1"

_ID_RE = re.compile(r'"id"\s*:\s*"([^"]+)"')


class ErrorDSL(ValueError):
    """El documento no se puede leer como una máquina de estados ``fsm-ledger/1``."""


def _entero(valor: Any, campo: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErrorDSL(
            f"{campo}: se esperaba un entero, llegó {type(valor).__name__} ({valor!r}); "
            "un delta fraccionario hace inexacta la conservación"
        )
    return valor


def _texto(valor: Any, campo: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErrorDSL(f"{campo}: se esperaba una cadena no vacía, llegó {valor!r}")
    return valor


@dataclass(frozen=True)
class Recurso:
    """Un recurso cuenta en unidades enteras de ``unidad``."""

    nombre: str
    unidad: str
    minimo: int = 0
    maximo: Optional[int] = None
    saldo_inicial: int = 0
    acumulativa: bool = False


@dataclass(frozen=True)
class Estado:
    nombre: str
    terminal: bool = False


@dataclass(frozen=True)
class Transicion:
    id: str
    de: str
    evento: str
    a: str
    delta: Dict[str, int]
    atomico: bool = False
    idem_key: Optional[str] = None
    unidad_declarada: Dict[str, str] = field(default_factory=dict)
    linea: int = 1
    nota: Optional[str] = None

    def mueve(self, recurso: str) -> bool:
        return self.delta.get(recurso, 0) != 0

    @property
    def mueve_algo(self) -> bool:
        return any(v != 0 for v in self.delta.values())

    def a_dict(self) -> Dict[str, Any]:
        doc: Dict[str, Any] = {
            "id": self.id,
            "de": self.de,
            "evento": self.evento,
            "a": self.a,
            "atomico": self.atomico,
            "idem_key": self.idem_key,
        }
        if self.unidad_declarada:
            doc["delta"] = {
                r: {"valor": v, "unidad": self.unidad_declarada.get(r, "")}
                for r, v in self.delta.items()
            }
        else:
            doc["delta"] = dict(self.delta)
        if self.nota:
            doc["nota"] = self.nota
        return doc


@dataclass(frozen=True)
class Grafo:
    dominio: str
    inicial: str
    estados: Dict[str, Estado]
    recursos: Dict[str, Recurso]
    transiciones: Tuple[Transicion, ...]
    procedencia: Dict[str, Any] = field(default_factory=dict)
    fuente: str = "<memoria>"
    texto_fuente: str = ""

    @property
    def por_id(self) -> Dict[str, Transicion]:
        return {t.id: t for t in self.transiciones}

    def salidas(self, estado: str) -> Tuple[Transicion, ...]:
        return tuple(t for t in self.transiciones if t.de == estado)

    def entradas(self, estado: str) -> Tuple[Transicion, ...]:
        return tuple(t for t in self.transiciones if t.a == estado)

    @property
    def medido(self) -> bool:
        return bool(self.procedencia.get("medido", True))

    def a_dict(self) -> Dict[str, Any]:
        return {
            "schema": ESQUEMA,
            "dominio": self.dominio,
            "inicial": self.inicial,
            "procedencia": self.procedencia,
            "estados": {e.nombre: {"terminal": e.terminal} for e in self.estados.values()},
            "recursos": {
                r.nombre: {
                    "unidad": r.unidad,
                    "minimo": r.minimo,
                    "maximo": r.maximo,
                    "saldo_inicial": r.saldo_inicial,
                    "acumulativa": r.acumulativa,
                }
                for r in self.recursos.values()
            },
            "transiciones": [t.a_dict() for t in self.transiciones],
        }

    def canonico(self) -> str:
        """Serialización determinista: misma máquina ⇒ mismos bytes ⇒ misma huella."""
        return json.dumps(
            self.a_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )

    def huella(self) -> str:
        return hashlib.sha256(self.canonico().encode("utf-8")).hexdigest()


def _lineas_por_id(texto: str) -> Dict[str, int]:
    lineas: Dict[str, int] = {}
    for numero, linea in enumerate(texto.splitlines(), start=1):
        m = _ID_RE.search(linea)
        if m and m.group(1) not in lineas:
            lineas[m.group(1)] = numero
    return lineas


def cargar(ruta: str | Path) -> Grafo:
    p = Path(ruta)
    try:
        texto = p.read_text(encoding="utf-8")
    except OSError as e:
        raise ErrorDSL(f"no se pudo leer {p}: {e}") from e
    return desde_texto(texto, fuente=str(p))


def desde_texto(texto: str, fuente: str = "<memoria>") -> Grafo:
    try:
        doc = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ErrorDSL(f"JSON inválido en {fuente}: {e}") from e
    if not isinstance(doc, dict):
        raise ErrorDSL(f"{fuente}: el documento debe ser un objeto JSON")

    esquema = doc.get("schema", ESQUEMA)
    if esquema != ESQUEMA:
        raise ErrorDSL(f"{fuente}: schema {esquema!r} no es {ESQUEMA!r}")

    dominio = _texto(doc.get("dominio"), f"{fuente}: dominio")

    estados_doc = doc.get("estados")
    if isinstance(estados_doc, list):
        estados_doc = {
            _texto((c or {}).get("nombre") if isinstance(c, dict) else None, f"{fuente}: estados[{i}].nombre"): (c or {})
            for i, c in enumerate(estados_doc)
        }
    if not isinstance(estados_doc, dict) or not estados_doc:
        raise ErrorDSL(f"{fuente}: estados debe ser un objeto o una lista no vacía")
    estados: Dict[str, Estado] = {}
    for nombre, cuerpo in estados_doc.items():
        if not isinstance(cuerpo, dict):
            raise ErrorDSL(f"{fuente}: estados.{nombre} debe ser un objeto")
        estados[nombre] = Estado(nombre=nombre, terminal=bool(cuerpo.get("terminal", False)))

    inicial = _texto(doc.get("inicial"), f"{fuente}: inicial")
    if inicial not in estados:
        raise ErrorDSL(f"{fuente}: inicial {inicial!r} no es un estado declarado")

    recursos_doc = doc.get("recursos")
    if not isinstance(recursos_doc, dict) or not recursos_doc:
        raise ErrorDSL(f"{fuente}: recursos debe ser un objeto no vacío")
    recursos: Dict[str, Recurso] = {}
    for nombre, cuerpo in recursos_doc.items():
        if not isinstance(cuerpo, dict):
            raise ErrorDSL(f"{fuente}: recursos.{nombre} debe ser un objeto")
        maximo = cuerpo.get("maximo")
        recursos[nombre] = Recurso(
            nombre=nombre,
            unidad=_texto(cuerpo.get("unidad"), f"{fuente}: recursos.{nombre}.unidad"),
            minimo=_entero(cuerpo.get("minimo", 0), f"{fuente}: recursos.{nombre}.minimo"),
            maximo=None if maximo is None else _entero(maximo, f"{fuente}: recursos.{nombre}.maximo"),
            saldo_inicial=_entero(
                cuerpo.get("saldo_inicial", 0), f"{fuente}: recursos.{nombre}.saldo_inicial"
            ),
            acumulativa=bool(cuerpo.get("acumulativa", False)),
        )

    trans_doc = doc.get("transiciones")
    if not isinstance(trans_doc, list) or not trans_doc:
        raise ErrorDSL(f"{fuente}: transiciones debe ser una lista no vacía")

    lineas = _lineas_por_id(texto)
    transiciones = []
    vistos = set()
    for i, cuerpo in enumerate(trans_doc):
        campo = f"{fuente}: transiciones[{i}]"
        if not isinstance(cuerpo, dict):
            raise ErrorDSL(f"{campo} debe ser un objeto")
        tid = _texto(cuerpo.get("id"), f"{campo}.id")
        if tid in vistos:
            raise ErrorDSL(f"{campo}.id: {tid!r} está repetido")
        vistos.add(tid)
        de = _texto(cuerpo.get("de"), f"{campo}.de")
        a = _texto(cuerpo.get("a"), f"{campo}.a")
        for extremo in (de, a):
            if extremo not in estados:
                raise ErrorDSL(f"{campo}: el estado {extremo!r} no está declarado")

        delta_doc = cuerpo.get("delta", {})
        if not isinstance(delta_doc, dict):
            raise ErrorDSL(f"{campo}.delta debe ser un objeto")
        delta: Dict[str, int] = {}
        unidad_declarada: Dict[str, str] = {}
        for recurso, valor in delta_doc.items():
            if recurso not in recursos:
                raise ErrorDSL(f"{campo}.delta: el recurso {recurso!r} no está declarado")
            if isinstance(valor, dict):
                delta[recurso] = _entero(valor.get("valor"), f"{campo}.delta.{recurso}.valor")
                unidad_declarada[recurso] = _texto(
                    valor.get("unidad"), f"{campo}.delta.{recurso}.unidad"
                )
            else:
                delta[recurso] = _entero(valor, f"{campo}.delta.{recurso}")

        idem = cuerpo.get("idem_key")
        transiciones.append(
            Transicion(
                id=tid,
                de=de,
                evento=_texto(cuerpo.get("evento"), f"{campo}.evento"),
                a=a,
                delta=delta,
                atomico=bool(cuerpo.get("atomico", False)),
                idem_key=idem if isinstance(idem, str) and idem.strip() else None,
                unidad_declarada=unidad_declarada,
                linea=lineas.get(tid, 1),
                nota=cuerpo.get("nota") if isinstance(cuerpo.get("nota"), str) else None,
            )
        )

    return Grafo(
        dominio=dominio,
        inicial=inicial,
        estados=estados,
        recursos=recursos,
        transiciones=tuple(transiciones),
        procedencia=doc.get("procedencia") or {},
        fuente=fuente,
        texto_fuente=texto,
    )
