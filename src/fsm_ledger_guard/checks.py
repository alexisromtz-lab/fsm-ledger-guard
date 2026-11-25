"""Comprobaciones algebraicas sobre el grafo declarado.

Cuatro familias exactas y una acotada:

* **ciclos** — Tarjan sobre el grafo; para cada componente fuertemente conexa se
  busca una función potencial ``φ`` tal que ``φ(a) − φ(de) = δ``. Si no existe,
  hay un ciclo con delta neto distinto de cero: la máquina puede crear o perder
  unidades sin límite. El contraejemplo es el ciclo dirigido más corto.
* **alcanzabilidad** — estados y transiciones inalcanzables desde ``s0``.
* **estados muertos** — componente fuertemente conexa sin arista de salida que
  no contiene ningún estado terminal.
* **retención de recursos** — un recurso no acumulativo que entra y no tiene
  ninguna arista que lo saque queda retenido; con ``φ`` consistente se nombra
  además el estado donde queda.
* **conservación acotada a profundidad k** — exploración del espacio
  ``(estado, saldos)``. Si la frontera no se cierra en ``k`` pasos, la
  conservación es ``NO_MEDIDO`` (RC 2), no un cero.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .dsl import Grafo, Recurso, Transicion

RC_LIMPIO = 0
RC_HALLAZGO = 1
RC_NO_MEDIDO = 2
RC_USO = 4

#: El orden no es ``max``: ``max(1, 2) == 2`` diría que NO_MEDIDO pesa más que
#: un hallazgo, y un defecto medido no se degrada por una rama sin medir.
PRECEDENCIA = (RC_USO, RC_HALLAZGO, RC_NO_MEDIDO, RC_LIMPIO)

LIMITE_ESTADOS_DE_SALDO = 20000

REGLAS: Dict[str, Dict[str, str]] = {
    "FSM001": {
        "clase": "CICLO_CON_FUGA",
        "severidad": "error",
        "titulo": "Ciclo con delta neto distinto de cero",
        "ayuda": "No existe potencial de saldo para el recurso: el ciclo puede crear o "
        "destruir unidades sin límite (pago duplicado, devolución duplicada).",
    },
    "FSM002": {
        "clase": "ESTADO_INALCANZABLE",
        "severidad": "warning",
        "titulo": "Estado inalcanzable desde el estado inicial",
        "ayuda": "Un estado que ninguna transición alcanza es una rama muerta del diseño.",
    },
    "FSM003": {
        "clase": "TRANSICION_INALCANZABLE",
        "severidad": "warning",
        "titulo": "Transición con origen inalcanzable",
        "ayuda": "La arista existe en el código pero no hay camino que llegue a su origen.",
    },
    "FSM004": {
        "clase": "ESTADO_SIN_SALIDA",
        "severidad": "error",
        "titulo": "Componente sin salida y sin estado terminal",
        "ayuda": "Se puede entrar y no se puede salir: el trámite queda colgado.",
    },
    "FSM005": {
        "clase": "TERMINAL_CON_SALIDA",
        "severidad": "warning",
        "titulo": "Estado declarado terminal con aristas de salida",
        "ayuda": "La declaración y el grafo se contradicen; una de las dos miente.",
    },
    "FSM006": {
        "clase": "RECURSO_RETENIDO_SIN_SALIDA",
        "severidad": "error",
        "titulo": "Recurso que entra y no tiene arista que lo saque",
        "ayuda": "Dinero o cupo retenido sin reembolso ni liberación: hay una asimetría "
        "entre lo que se toma y lo que se devuelve.",
    },
    "FSM007": {
        "clase": "MOVIMIENTO_NO_ATOMICO",
        "severidad": "error",
        "titulo": "Transición que mueve un recurso sin atomicidad declarada",
        "ayuda": "Si el movimiento de recurso no es atómico con el cambio de estado, el "
        "reintento puede aplicarlo dos veces.",
    },
    "FSM008": {
        "clase": "MOVIMIENTO_SIN_IDEM",
        "severidad": "error",
        "titulo": "Transición que mueve un recurso sin clave de idempotencia",
        "ayuda": "Sin clave de idempotencia, el mismo evento aplicado dos veces mueve el "
        "recurso dos veces.",
    },
    "FSM009": {
        "clase": "UNIDAD_INCONSISTENTE",
        "severidad": "warning",
        "titulo": "Delta declarado en una unidad distinta a la del recurso",
        "ayuda": "Un mismo recurso no admite dos unidades: pesos y centavos en la misma "
        "columna desalinean todos los lectores por un factor de 100.",
    },
    "FSM010": {
        "clase": "SALDO_NEGATIVO",
        "severidad": "error",
        "titulo": "Saldo por debajo del mínimo en una ruta alcanzable",
        "ayuda": "El grafo permite extraer un recurso que no se tiene.",
    },
    "FSM011": {
        "clase": "COTA_EXCEDIDA",
        "severidad": "error",
        "titulo": "Saldo por encima del máximo declarado",
        "ayuda": "El recurso se acumula por encima de lo que el dominio admite: la misma "
        "reserva cobrada más de una vez.",
    },
}


@dataclass(frozen=True)
class Hallazgo:
    regla: str
    clase: str
    severidad: str
    mensaje: str
    transiciones: Tuple[str, ...] = ()
    estados: Tuple[str, ...] = ()
    camino: Tuple[str, ...] = ()
    detalle: Dict[str, Any] = field(default_factory=dict)
    linea: int = 1

    def a_dict(self) -> Dict[str, Any]:
        return {
            "regla": self.regla,
            "clase": self.clase,
            "severidad": self.severidad,
            "mensaje": self.mensaje,
            "transiciones": list(self.transiciones),
            "estados": list(self.estados),
            "camino": list(self.camino),
            "detalle": self.detalle,
            "linea": self.linea,
        }


@dataclass(frozen=True)
class Medicion:
    profundidad: int
    aplicaciones: int = 0
    estados_de_saldo: int = 0
    frontera: int = 0
    cerrada: bool = False
    motivo_no_medido: Optional[str] = None
    saldos_maximos: Dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Resultado:
    grafo: Grafo
    hallazgos: Tuple[Hallazgo, ...]
    medicion: Medicion
    cobertura: Dict[str, str]
    rc: int

    @property
    def limpio(self) -> bool:
        return self.rc == RC_LIMPIO

    def por_clase(self, clase: str) -> Tuple[Hallazgo, ...]:
        return tuple(h for h in self.hallazgos if h.clase == clase)


def _hallazgo(regla: str, mensaje: str, **kw: Any) -> Hallazgo:
    meta = REGLAS[regla]
    return Hallazgo(
        regla=regla, clase=meta["clase"], severidad=meta["severidad"], mensaje=mensaje, **kw
    )


# --------------------------------------------------------------------------- #
# Grafo
# --------------------------------------------------------------------------- #
def alcanzables(grafo: Grafo) -> Set[str]:
    vistos = {grafo.inicial}
    cola = deque([grafo.inicial])
    while cola:
        u = cola.popleft()
        for t in grafo.salidas(u):
            if t.a not in vistos:
                vistos.add(t.a)
                cola.append(t.a)
    return vistos


def componentes_fuertemente_conexas(grafo: Grafo) -> List[List[str]]:
    indice: Dict[str, int] = {}
    bajo: Dict[str, int] = {}
    pila: List[str] = []
    en_pila: Set[str] = set()
    componentes: List[List[str]] = []
    contador = [0]

    def visitar(u: str) -> None:
        indice[u] = bajo[u] = contador[0]
        contador[0] += 1
        pila.append(u)
        en_pila.add(u)
        for t in grafo.salidas(u):
            v = t.a
            if v not in indice:
                visitar(v)
                bajo[u] = min(bajo[u], bajo[v])
            elif v in en_pila:
                bajo[u] = min(bajo[u], indice[v])
        if bajo[u] == indice[u]:
            comp: List[str] = []
            while True:
                w = pila.pop()
                en_pila.discard(w)
                comp.append(w)
                if w == u:
                    break
            componentes.append(comp)

    for estado in grafo.estados:
        if estado not in indice:
            visitar(estado)
    return componentes


def camino_mas_corto(
    grafo: Grafo, origen: str, destino: str, permitidos: Optional[Set[str]] = None
) -> Optional[List[Transicion]]:
    """Camino dirigido de aristas mínimo de ``origen`` a ``destino``."""
    if origen == destino:
        return []
    padre: Dict[str, Tuple[str, Transicion]] = {}
    vistos = {origen}
    cola = deque([origen])
    while cola:
        u = cola.popleft()
        for t in grafo.salidas(u):
            v = t.a
            if permitidos is not None and (u not in permitidos or v not in permitidos):
                continue
            if v in vistos:
                continue
            vistos.add(v)
            padre[v] = (u, t)
            if v == destino:
                aristas: List[Transicion] = []
                cursor = destino
                while cursor != origen:
                    anterior, arista = padre[cursor]
                    aristas.append(arista)
                    cursor = anterior
                aristas.reverse()
                return aristas
            cola.append(v)
    return None


def potencial(grafo: Grafo, recurso: str) -> Tuple[Dict[str, int], List[Transicion]]:
    """Saldo por estado a lo largo de un árbol BFS, y las aristas que lo contradicen.

    Una contradicción aquí **no** implica un ciclo: dos caminos pueden llegar al
    mismo estado con saldos distintos (un estado que no determina el saldo). La
    detección de ciclos con fuga se hace dentro de cada componente fuertemente
    conexa, donde toda arista está sobre un ciclo.
    """
    phi: Dict[str, int] = {grafo.inicial: 0}
    cola = deque([grafo.inicial])
    while cola:
        u = cola.popleft()
        for t in grafo.salidas(u):
            if t.a not in phi:
                phi[t.a] = phi[u] + t.delta.get(recurso, 0)
                cola.append(t.a)
    conflictos = [
        t
        for t in grafo.transiciones
        if t.de in phi and t.a in phi and phi[t.a] != phi[t.de] + t.delta.get(recurso, 0)
    ]
    return phi, conflictos


def potencial_en_scc(
    grafo: Grafo, recurso: str, scc: Set[str]
) -> Tuple[Dict[str, int], Dict[str, Tuple[str, Transicion]], Dict[str, str]]:
    """Potencial restringido a las aristas internas de una componente conexa.

    Dentro de una SCC toda arista está sobre un ciclo, así que una arista que
    contradiga el potencial prueba que existe un ciclo con delta neto distinto
    de cero. Devuelve el saldo por estado, el árbol que lo sostiene y la raíz de
    cada estado, que es lo que permite reconstruir el contraejemplo.
    """
    internas = [t for t in grafo.transiciones if t.de in scc and t.a in scc]
    phi: Dict[str, int] = {}
    padre: Dict[str, Tuple[str, Transicion]] = {}
    raiz_de: Dict[str, str] = {}
    for raiz in sorted(scc):
        if raiz in phi:
            continue
        phi[raiz] = 0
        raiz_de[raiz] = raiz
        cola = deque([raiz])
        while cola:
            u = cola.popleft()
            for t in internas:
                if t.de != u or t.a in phi:
                    continue
                phi[t.a] = phi[u] + t.delta.get(recurso, 0)
                padre[t.a] = (u, t)
                raiz_de[t.a] = raiz
                cola.append(t.a)
    return phi, padre, raiz_de


def _ciclos_de_paseo(
    inicio: str, paseo: List[Tuple[str, str, Transicion]]
) -> List[List[Transicion]]:
    """Descompone un paseo cerrado en ciclos simples.

    Un paseo con delta neto distinto de cero no puede descomponerse en ciclos
    todos nulos: la suma de los trozos es el total. Se recorre con una pila de
    vértices y cada repetición cierra un ciclo.
    """
    pila_nodos = [inicio]
    pila_aristas: List[Transicion] = []
    ciclos: List[List[Transicion]] = []
    for _, hasta, arista in paseo:
        if hasta in pila_nodos:
            corte = pila_nodos.index(hasta)
            ciclos.append(pila_aristas[corte:] + [arista])
            pila_aristas = pila_aristas[:corte]
            pila_nodos = pila_nodos[: corte + 1]
        else:
            pila_nodos.append(hasta)
            pila_aristas.append(arista)
    return [c for c in ciclos if c]


def _ciclo_testigo(
    arista: Transicion,
    padre: Dict[str, Tuple[str, Transicion]],
    raiz_de: Dict[str, str],
    recurso: str,
) -> Optional[Tuple[List[Transicion], int]]:
    """Ciclo simple con delta neto distinto de cero que contiene ``arista``.

    El paseo cerrado es el camino del árbol hasta el origen, la arista, y el
    camino del árbol hasta el destino recorrido al revés. Su delta neto es
    ``phi[de] + delta - phi[a]``, distinto de cero porque ``arista`` contradice
    el potencial; al descomponerlo, algún ciclo simple conserva esa diferencia.
    """
    raiz = raiz_de.get(arista.de)
    if raiz is None or raiz_de.get(arista.a) != raiz:
        return None

    def camino(destino: str) -> List[Transicion]:
        aristas: List[Transicion] = []
        cursor = destino
        while cursor != raiz:
            anterior, paso = padre[cursor]
            aristas.append(paso)
            cursor = anterior
        aristas.reverse()
        return aristas

    paseo = [(a.de, a.a, a) for a in camino(arista.de)]
    paseo.append((arista.de, arista.a, arista))
    paseo += [(a.a, a.de, a) for a in reversed(camino(arista.a))]
    for ciclo in _ciclos_de_paseo(raiz, paseo):
        neto = sum(t.delta.get(recurso, 0) for t in ciclo)
        if neto != 0:
            return ciclo, neto
    return None


def combinar(*rcs: int) -> int:
    """RC de un acto sobre varios grafos, en el orden de precedencia."""
    for codigo in PRECEDENCIA:
        if codigo in rcs:
            return codigo
    return RC_USO


# --------------------------------------------------------------------------- #
# Comprobaciones
# --------------------------------------------------------------------------- #
def _chequeo_ciclos(grafo: Grafo, alcance: Set[str], cobertura: Dict[str, str]) -> List[Hallazgo]:
    hallazgos: List[Hallazgo] = []
    for comp in componentes_fuertemente_conexas(grafo):
        scc = set(comp)
        internas = [t for t in grafo.transiciones if t.de in scc and t.a in scc]
        if not internas:
            continue
        if not (scc & alcance):
            cobertura[f"ciclos:{'+'.join(sorted(scc))}"] = "NO_MEDIDO: componente inalcanzable"
            continue
        for recurso, rec in grafo.recursos.items():
            phi, padre, raiz_de = potencial_en_scc(grafo, recurso, scc)
            conflictos = [
                t for t in internas if phi[t.a] != phi[t.de] + t.delta.get(recurso, 0)
            ]
            if not conflictos:
                continue
            # Se publica el ciclo simple más corto entre los testigos de cada
            # arista que contradice el potencial.
            candidatos = []
            for indice, arista in enumerate(conflictos):
                testigo = _ciclo_testigo(arista, padre, raiz_de, recurso)
                if testigo is None:
                    continue
                ciclo, neto = testigo
                candidatos.append((len(ciclo), indice, arista, ciclo, neto))
            if not candidatos:
                cobertura[f"ciclos:{recurso}:{'+'.join(sorted(scc))}"] = (
                    "NO_MEDIDO: el potencial se contradice pero no se aisló un "
                    "ciclo simple que lo testifique"
                )
                continue
            candidatos.sort(key=lambda c: (c[0], c[1]))
            _, _, arista, ciclo, neto = candidatos[0]
            hallazgos.append(
                _hallazgo(
                    "FSM001",
                    f"{recurso}: el ciclo {' → '.join(t.id for t in ciclo)} tiene delta neto "
                    f"{neto:+d} {rec.unidad} por vuelta; el saldo de "
                    f"{', '.join(sorted(scc))} no está definido",
                    transiciones=tuple(t.id for t in ciclo),
                    estados=tuple(sorted(scc)),
                    camino=tuple(t.id for t in ciclo),
                    detalle={
                        "recurso": recurso,
                        "delta_neto": neto,
                        "unidad": rec.unidad,
                        "aristas_scc": [t.id for t in internas],
                        "estados_scc": sorted(scc),
                    },
                    linea=arista.linea,
                )
            )
    return hallazgos


def _chequeo_alcanzabilidad(grafo: Grafo, alcance: Set[str]) -> List[Hallazgo]:
    hallazgos: List[Hallazgo] = []
    inalcanzables = [e for e in grafo.estados if e not in alcance]
    if inalcanzables:
        hallazgos.append(
            _hallazgo(
                "FSM002",
                f"{len(inalcanzables)} estado(s) sin camino desde {grafo.inicial!r}: "
                f"{', '.join(inalcanzables)}",
                estados=tuple(inalcanzables),
                detalle={"inicial": grafo.inicial},
            )
        )
    huerfanas = [t for t in grafo.transiciones if t.de not in alcance]
    if huerfanas:
        hallazgos.append(
            _hallazgo(
                "FSM003",
                f"{len(huerfanas)} transición(es) con origen inalcanzable: "
                f"{', '.join(t.id for t in huerfanas)}",
                transiciones=tuple(t.id for t in huerfanas),
                linea=huerfanas[0].linea,
            )
        )
    return hallazgos


def _chequeo_estados_muertos(grafo: Grafo, alcance: Set[str]) -> List[Hallazgo]:
    hallazgos: List[Hallazgo] = []
    for comp in componentes_fuertemente_conexas(grafo):
        scc = set(comp)
        if not (scc & alcance):
            continue
        salidas = [t for t in grafo.transiciones if t.de in scc and t.a not in scc]
        terminales = [e for e in comp if grafo.estados[e].terminal]
        if not salidas and not terminales:
            hallazgos.append(
                _hallazgo(
                    "FSM004",
                    f"{', '.join(sorted(scc))} se alcanza y no se puede abandonar, y no hay "
                    "estado terminal declarado dentro",
                    estados=tuple(sorted(scc)),
                    detalle={"componente": sorted(scc)},
                )
            )
    for t in grafo.transiciones:
        if grafo.estados[t.de].terminal and t.a != t.de:
            hallazgos.append(
                _hallazgo(
                    "FSM005",
                    f"el estado {t.de!r} está declarado terminal y la transición {t.id} "
                    f"lo abandona hacia {t.a!r}",
                    transiciones=(t.id,),
                    estados=(t.de, t.a),
                    linea=t.linea,
                )
            )
    return hallazgos


def _chequeo_retencion(
    grafo: Grafo, alcance: Set[str], cobertura: Dict[str, str]
) -> List[Hallazgo]:
    hallazgos: List[Hallazgo] = []
    for recurso, rec in grafo.recursos.items():
        if rec.acumulativa:
            cobertura[f"retencion:{recurso}"] = "MEDIDO: recurso declarado acumulativo"
            continue
        entran = [t for t in grafo.transiciones if t.mueve(recurso) and t.delta[recurso] > 0]
        if not entran:
            cobertura[f"retencion:{recurso}"] = "MEDIDO: el recurso nunca entra"
            continue
        salen = [t for t in grafo.transiciones if t.delta.get(recurso, 0) < 0]
        phi, conflictos = potencial(grafo, recurso)
        if not salen:
            con_saldo = [e for e, v in phi.items() if v > rec.minimo]
            cola_saldo = (
                f"algún camino alcanza {max(phi.values()) - rec.minimo:+d} {rec.unidad}, y"
                " el saldo por estado no está definido porque hay estados alcanzables con"
                " dos saldos distintos"
                if conflictos
                else f"alcanza {max(phi.values()) - rec.minimo:+d} {rec.unidad}"
            )
            hallazgos.append(
                _hallazgo(
                    "FSM006",
                    f"{recurso}: ninguna transición lo disminuye, así que lo que entra por "
                    f"{', '.join(t.id for t in entran)} queda retenido en "
                    f"{', '.join(con_saldo) or 'ningún estado'}; {cola_saldo}",
                    transiciones=tuple(t.id for t in entran),
                    estados=tuple(con_saldo),
                    detalle={
                        "recurso": recurso,
                        "alcance": "global",
                        "sin_arista_de_salida": True,
                        "saldo_maximo": max(phi.values()),
                        "unidad": rec.unidad,
                    },
                    linea=entran[0].linea,
                )
            )
            continue
        if conflictos:
            cobertura[f"retencion:{recurso}"] = (
                "NO_MEDIDO: el saldo no está definido (FSM001); la retención se puede "
                "medir cuando el ciclo se cierre"
            )
            continue
        bajo = {t.de for t in salen}
        puede_bajar: Set[str] = set()
        cola = deque(sorted(bajo))
        while cola:
            u = cola.popleft()
            if u in puede_bajar:
                continue
            puede_bajar.add(u)
            for t in grafo.entradas(u):
                if t.de not in puede_bajar:
                    cola.append(t.de)
        retenidos = [e for e in grafo.estados if e in alcance and phi.get(e, 0) > rec.minimo and e not in puede_bajar]
        if retenidos:
            hallazgos.append(
                _hallazgo(
                    "FSM006",
                    f"{recurso}: {', '.join(retenidos)} retiene "
                    f"{max(phi[e] for e in retenidos):+d} {rec.unidad} sin camino que lo "
                    "libere",
                    estados=tuple(retenidos),
                    detalle={
                        "recurso": recurso,
                        "alcance": "estado",
                        "saldos": {e: phi[e] for e in retenidos},
                        "unidad": rec.unidad,
                    },
                )
            )
        else:
            cobertura[f"retencion:{recurso}"] = "MEDIDO: todo saldo positivo tiene salida"
    return hallazgos


def _chequeo_guardas(grafo: Grafo, cobertura: Dict[str, str]) -> List[Hallazgo]:
    hallazgos: List[Hallazgo] = []
    for t in grafo.transiciones:
        if not t.mueve_algo:
            continue
        recursos = ", ".join(
            f"{r}{t.delta[r]:+d}" for r in grafo.recursos if t.mueve(r)
        )
        if not t.atomico:
            hallazgos.append(
                _hallazgo(
                    "FSM007",
                    f"{t.id} mueve {recursos} sin declarar atomicidad con el cambio de estado",
                    transiciones=(t.id,),
                    estados=(t.de, t.a),
                    linea=t.linea,
                )
            )
        if not t.idem_key:
            hallazgos.append(
                _hallazgo(
                    "FSM008",
                    f"{t.id} mueve {recursos} sin clave de idempotencia: el mismo evento "
                    "aplicado dos veces mueve el recurso dos veces",
                    transiciones=(t.id,),
                    estados=(t.de, t.a),
                    linea=t.linea,
                )
            )
        for recurso, unidad in t.unidad_declarada.items():
            esperada = grafo.recursos[recurso].unidad
            if unidad != esperada:
                hallazgos.append(
                    _hallazgo(
                        "FSM009",
                        f"{t.id} declara {recurso} en {unidad!r} pero el recurso se cuenta "
                        f"en {esperada!r}",
                        transiciones=(t.id,),
                        estados=(t.de, t.a),
                        detalle={
                            "recurso": recurso,
                            "unidad_declarada": unidad,
                            "unidad_del_recurso": esperada,
                            "valor": t.delta[recurso],
                        },
                        linea=t.linea,
                    )
                )
    cobertura["guardas"] = "MEDIDO"
    return hallazgos


def conservacion_acotada(
    grafo: Grafo, profundidad: int, limite: int = LIMITE_ESTADOS_DE_SALDO
) -> Tuple[List[Hallazgo], Medicion]:
    """Explora el espacio ``(estado, saldos)`` hasta ``profundidad`` pasos."""
    recursos = list(grafo.recursos)
    inicial = tuple(grafo.recursos[r].saldo_inicial for r in recursos)
    clave_inicial = (grafo.inicial, inicial)

    padre: Dict[Tuple[str, Tuple[int, ...]], Optional[Tuple[Tuple[str, Tuple[int, ...]], str]]] = {
        clave_inicial: None
    }
    cola = deque([(grafo.inicial, inicial, 0)])
    en_frontera: Set[Tuple[str, Tuple[int, ...]]] = set()
    aplicaciones = 0
    motivo: Optional[str] = None
    saldos_maximos = dict(zip(recursos, inicial))
    excedidos: Dict[Tuple[str, str], Tuple[Tuple[str, Tuple[int, ...]], int]] = {}
    negativos: Dict[Tuple[str, str], Tuple[Tuple[str, Tuple[int, ...]], int]] = {}

    while cola:
        estado, saldos, d = cola.popleft()
        for t in grafo.salidas(estado):
            nuevos = tuple(
                s + t.delta.get(r, 0) for r, s in zip(recursos, saldos)
            )
            aplicaciones += 1
            for r, s in zip(recursos, nuevos):
                rec = grafo.recursos[r]
                saldos_maximos[r] = max(saldos_maximos[r], s)
                if s < rec.minimo and (r, t.a) not in negativos:
                    negativos[(r, t.a)] = ((estado, saldos), s, t)
                if rec.maximo is not None and s > rec.maximo and (r, t.a) not in excedidos:
                    excedidos[(r, t.a)] = ((estado, saldos), s, t)
            clave = (t.a, nuevos)
            if clave in padre or clave in en_frontera:
                continue
            if d + 1 >= profundidad:
                en_frontera.add(clave)
                continue
            if len(padre) >= limite:
                motivo = f"espacio de saldos > {limite} estados explorados"
                cola.clear()
                break
            padre[clave] = ((estado, saldos), t.id)
            cola.append((t.a, nuevos, d + 1))

    def camino(clave: Tuple[str, Tuple[int, ...]]) -> Tuple[str, ...]:
        aristas: List[str] = []
        cursor = clave
        while padre.get(cursor):
            anterior, tid = padre[cursor]  # type: ignore[misc]
            aristas.append(tid)
            cursor = anterior
        aristas.reverse()
        return tuple(aristas)

    def peor_caso(
        tabla: Dict[Tuple[str, str], Tuple[Tuple[str, Tuple[int, ...]], int, Transicion]]
    ) -> Dict[str, List[Tuple[int, str, Tuple[str, Tuple[int, ...]], int, Transicion]]]:
        """Un solo hallazgo por recurso, con el camino mas corto a la violacion."""
        agrupado: Dict[
            str, List[Tuple[int, str, Tuple[str, Tuple[int, ...]], int, Transicion]]
        ] = {}
        for (recurso, estado), (origen, saldo, arista) in sorted(tabla.items()):
            # la arista que viola la cota forma parte del contraejemplo: sin ella
            # el camino publicado acaba antes del defecto
            agrupado.setdefault(recurso, []).append(
                (len(camino(origen)) + 1, estado, origen, saldo, arista)
            )
        for casos in agrupado.values():
            casos.sort(key=lambda c: (c[0], c[1]))
        return agrupado

    hallazgos: List[Hallazgo] = []
    for recurso, casos in sorted(peor_caso(excedidos).items()):
        rec = grafo.recursos[recurso]
        _, estado, origen, saldo, arista = casos[0]
        camino_hasta = camino(origen) + (arista.id,)
        afectados = sorted({c[1] for c in casos})
        hallazgos.append(
            _hallazgo(
                "FSM011",
                f"{recurso} llega a {saldo:+d} {rec.unidad} en {estado!r} y el máximo "
                f"declarado es {rec.maximo:+d}"
                + (f" ({len(afectados)} estados afectados)" if len(afectados) > 1 else ""),
                estados=tuple(afectados),
                camino=camino_hasta,
                detalle={
                    "recurso": recurso,
                    "saldo": saldo,
                    "maximo": rec.maximo,
                    "unidad": rec.unidad,
                    "camino": list(camino_hasta),
                    "estados_afectados": afectados,
                },
                linea=arista.linea,
            )
        )
    for recurso, casos in sorted(peor_caso(negativos).items()):
        rec = grafo.recursos[recurso]
        _, estado, origen, saldo, arista = casos[0]
        camino_hasta = camino(origen) + (arista.id,)
        afectados = sorted({c[1] for c in casos})
        hallazgos.append(
            _hallazgo(
                "FSM010",
                f"{recurso} llega a {saldo:+d} {rec.unidad} en {estado!r}, por debajo del "
                f"mínimo {rec.minimo:+d}"
                + (f" ({len(afectados)} estados afectados)" if len(afectados) > 1 else ""),
                estados=tuple(afectados),
                camino=camino_hasta,
                detalle={"recurso": recurso, "saldo": saldo, "minimo": rec.minimo,
                         "unidad": rec.unidad, "camino": list(camino_hasta),
                         "estados_afectados": afectados},
                linea=arista.linea,
            )
        )

    medicion = Medicion(
        profundidad=profundidad,
        aplicaciones=aplicaciones,
        estados_de_saldo=len(padre),
        frontera=len(en_frontera),
        cerrada=not en_frontera and motivo is None,
        motivo_no_medido=motivo,
        saldos_maximos=saldos_maximos,
    )
    return hallazgos, medicion


def auditar(grafo: Grafo, profundidad: int = 8, exigir_medido: bool = False) -> Resultado:
    alcance = alcanzables(grafo)
    cobertura: Dict[str, str] = {"alcanzabilidad": "MEDIDO"}
    hallazgos: List[Hallazgo] = []
    hallazgos += _chequeo_ciclos(grafo, alcance, cobertura)
    hallazgos += _chequeo_alcanzabilidad(grafo, alcance)
    hallazgos += _chequeo_estados_muertos(grafo, alcance)
    hallazgos += _chequeo_retencion(grafo, alcance, cobertura)
    hallazgos += _chequeo_guardas(grafo, cobertura)
    de_cota, medicion = conservacion_acotada(grafo, profundidad)
    hallazgos += de_cota

    if medicion.cerrada:
        cobertura["conservacion"] = "MEDIDO: el espacio de saldos se cierra"
    else:
        cobertura["conservacion"] = (
            f"NO_MEDIDO: frontera abierta en profundidad {profundidad}"
            + (f" ({medicion.motivo_no_medido})" if medicion.motivo_no_medido else "")
        )

    hallazgos.sort(key=lambda h: (h.regla, h.linea, h.transiciones))
    rc = RC_LIMPIO
    if hallazgos:
        rc = RC_HALLAZGO
    elif not medicion.cerrada or any(not v.startswith("MEDIDO") for v in cobertura.values()):
        rc = RC_NO_MEDIDO
    elif exigir_medido and not grafo.medido:
        rc = RC_NO_MEDIDO

    return Resultado(
        grafo=grafo,
        hallazgos=tuple(hallazgos),
        medicion=medicion,
        cobertura=cobertura,
        rc=rc,
    )
