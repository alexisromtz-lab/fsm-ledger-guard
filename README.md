# fsm-ledger-guard

[![verify](https://github.com/alexisromtz-lab/fsm-ledger-guard/actions/workflows/verify.yml/badge.svg)](https://github.com/alexisromtz-lab/fsm-ledger-guard/actions/workflows/verify.yml)
[![Code Scanning](https://img.shields.io/badge/Code%20Scanning-12%20alertas%20en%20vivo-blue)](https://github.com/alexisromtz-lab/fsm-ledger-guard/security/code-scanning)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24546807.svg)](https://doi.org/10.5281/zenodo.24546807)

Auditoría **algebraica** de máquinas de estados financieras. Certifica, antes de
desplegar, que un grafo de pagos, reservas o pedidos **no puede crear ni perder
unidades**: ni ciclos que devuelven dinero, ni recursos que entran y nunca salen,
ni movimientos de dinero sin clave de idempotencia.

Sin dependencias. Python ≥ 3.9. Emite **SARIF 2.1.0** (GitHub Code Scanning) y un
**recibo `conservation/1`** que [`conservation-ledger`](https://github.com/alexisromtz-lab/conservation-ledger)
recomputa por su cuenta.

```console
$ fsm-ledger-guard scan mi-flujo.json
dominio   studio-city/reservas
procedencia alexisromtz-lab/letras-delespiritu @ 95ea4a71
grafo     5 estados · 13 transiciones · huella a0e28f6069fa6657

[FSM001] error   CICLO_CON_FUGA
          escrow: el ciclo P9 → P3 tiene delta neto +350 centavos por vuelta; el saldo de confirmada, pagada, pendiente no está definido
          contraejemplo: P9 → P3
          tests/fixtures/studio_city_pre_fix.json:62
…
RC 1
```

**Nota de procedencia.** El código auditado vive en un repositorio **privado**
(`alexisromtz-lab/letras-delespiritu`, directorio `estudios-worker`), así que el
commit no es verificable por un lector externo: por eso cada fixture declara
`verificable_publicamente: false` en vez de omitirlo. Lo que sí es reproducible
es el documento —el fixture es el estado del grafo, no una paráfrasis de él— y
el comando que lo audita. `v0.1.2` corrigió esa cita: la versión anterior
declaraba un repositorio que no resuelve, y como la huella del grafo cubre el
documento completo, corregir la cita cambió las huellas publicadas. La cita se
mide antes de escribirse; si no resuelve, no se publica.

## 1. Qué se demuestra, no qué se opina

Una máquina de estados es $(S, \Sigma, \delta, s_0, F)$ y cada transición mueve
un vector de recursos con signo. Decir «este flujo conserva el dinero» es pedir
que para todo camino desde $s_0$:

$$\text{saldo}_{\text{inicial}} + \sum \text{entradas} - \sum \text{salidas} - \sum \text{reembolsos} = \text{saldo}_{\text{final}}$$

El instrumento no compara saldos finales: **decide si esa igualdad está bien
definida**. Dos resultados exactos, no heurísticas:

- **Potencial por recurso.** Si existe $\varphi$ con $\varphi(u) - \varphi(v) = \delta_{uv}$
  para cada arista $u \to v$, el saldo de cada estado es único. Y esa $\varphi$
  existe **si y sólo si** todo ciclo tiene delta neto $0$: un ciclo con
  $\delta \neq 0$ permite cobrar (o perder) esa cantidad **ilimitadas veces**, y
  no hay función que lo represente. Basta construir $\varphi$ por anchura y
  detenerse en la primera arista que lo contradiga — que es, por construcción,
  el contraejemplo mínimo.
- **Conservación acotada.** La igualdad se comprueba además sobre el espacio de
  saldos `(estado, saldos)` hasta profundidad $k$. Si la exploración no cierra
  dentro de $k$, el resultado es **NO_MEDIDO (RC 2)**, nunca «limpio».

Lo que **no** promete: no lee tu código fuente. El grafo es una declaración
`fsm-ledger/1` que tú escribes (o generas) y el auditor verifica. Un grafo que
miente produce un veredicto sobre una mentira.

## 2. El caso real: Studio City, tres commits y un objetivo

Los fixtures de [`tests/fixtures/`](tests/fixtures) son un flujo de reservas
con anticipo medido en un SaaS en producción. Tres de ellos son el **mismo
repositorio en tres commits** —con el delta medido entre uno y otro— y el cuarto
es una proyección que se declara como tal. Están en el repositorio porque el
instrumento se juzga por lo que encontró, no por su README.

| acto | commit | RC | qué dice |
|---|---|---|---|
| [`studio_city_pre_fix.json`](tests/fixtures/studio_city_pre_fix.json) | `95ea4a71` | **1** · 8 hallazgos | el dinero se puede cobrar dos veces y nadie lo suelta |
| [`studio_city_post_fix.json`](tests/fixtures/studio_city_post_fix.json) | `e67b9d5a` | **1** · 3 hallazgos | ciclo cerrado y unidades normalizadas; falta la idempotencia |
| [`studio_city_f7.json`](tests/fixtures/studio_city_f7.json) | `251aaff8` | **1** · **1** hallazgo | la deuda ya tiene clave de idempotencia; sólo falta la salida del dinero |
| [`studio_city_objetivo.json`](tests/fixtures/studio_city_objetivo.json) | *proyección* | **0** | lo que haría falta; **no está medido** |

**Antes.** El ciclo de dos aristas `pagada → pendiente → pagada` tiene delta neto
`+350` centavos y `+1` cupo por vuelta: la reserva se puede pagar, «despagar» y
volver a pagar sin que nada lo impida. Dos transiciones declaran el importe en
`pesos` sobre un recurso contado en `centavos` — el defecto que desalinea a todos
los lectores por un factor de 100. Ninguna transición disminuye `escrow`: el
dinero entra y se queda.

**Después del parche.** El ciclo desaparece (una guarda de origen impide
`pagada → pendiente`) y las unidades quedan uniformes. **Sigue en RC 1**, y no es
un fallo del auditor: en `e67b9d5a` los dos bordes que mueven dinero tampoco
declaran clave de idempotencia (`FSM008`), y ninguna arista saca `escrow` del
estado `pagada` (`FSM006`). Publicar aquí un RC 0 sería mentir sobre un commit.

**Después de F7.** El segundo parche no toca el grafo: toca el dinero. Dos
llamadas a `crearPreferencia` para la misma reserva acuñaban dos preferencias de
cobro y dejaban dos filas `pendiente` —un doble clic es un cobro duplicable—.
La clave de idempotencia no puede ser el `preference_id` de Mercado Pago, porque
cada POST acuña uno nuevo: es **la deuda** `(reserva_id, estudio_id, concepto)`,
con un solo `pendiente` vivo. La arista declara esa clave y `FSM008` desaparece
porque el defecto desapareció, no porque el auditor lo ignore: **3 → 1** con la
regla que ya existía. El único hallazgo que queda es `FSM006`, y es una política:
`pagada → cancelada` responde `409` a propósito mientras no exista un estado
`reembolsado` acoplado al asiento negativo en `platino-finance`.

**Objetivo.** `studio_city_objetivo.json` añade el estado terminal `reembolsado`
con su salida de `escrow`, la captura en `atendida` y las claves de idempotencia.
Da RC 0 — y su `procedencia.medido` es `false`, así que con `--exigir-medido`
responde **RC 2**. Una proyección se publica como proyección.

```console
$ fsm-ledger-guard scan tests/fixtures/studio_city_objetivo.json --exigir-medido
…
RC 2
```

## 2 bis. El segundo vertical: Moon & Rain (e-commerce, otro dominio)

Dos fixtures más, y ninguno de los dos hizo falta una línea nueva del motor:
[`moon_and_rain_pre_fix.json`](tests/fixtures/moon_and_rain_pre_fix.json) y
[`moon_and_rain_post_fix.json`](tests/fixtures/moon_and_rain_post_fix.json) son
el **mismo worker de tienda** (`moon-rain-worker`) en el HEAD `93f5bcdd` y en el
parche que le siguió. Los dos viven en el mismo repositorio privado que Studio
City, así que su `procedencia.verificable_publicamente` es `false`, igual que en
los otros cuatro.

| acto | commit | RC | qué dice |
|---|---|---|---|
| [`moon_and_rain_pre_fix.json`](tests/fixtures/moon_and_rain_pre_fix.json) | `93f5bcdd` | **1** · 3 hallazgos | el importe entra por `orders/create` y no hay ninguna arista que lo saque |
| [`moon_and_rain_post_fix.json`](tests/fixtures/moon_and_rain_post_fix.json) | `d144256f` | **0** | guarda de origen, reembolso y cancelación: todo terminal cierra en saldo cero |

**Antes.** Tres escritores de `cuenta_pedidos.estado` sin guarda de origen
(`pedidos.js:18-19` reescribía `procesando` desde cualquier evento, `webhook.js:215`
y `banca.js:31` escribían `en camino` con `WHERE order_id=?`), cero ocurrencias de
`refunds` y de `orders/cancelled` en `src/`, y un estado `entregado` que sólo
existía en el comentario de la migración. El auditor lo nombra sin saber que es
una tienda: `FSM004` (`en camino` y `procesando` se alcanzan y no se abandonan, y
no hay terminal dentro), `FSM006` (ninguna transición disminuye `dinero`) y
`FSM002` (`entregado`, inalcanzable).

**Después.** `src/shopify/estados.js` declara la máquina como dato y los tres
escritores arman su guarda con `guardaDeOrigen()`. `refunds/create` cierra el
pedido sólo si el reembolso cubre el total, comparando en centavos enteros: un
reembolso parcial no mueve la máquina, se registra. **RC 0**, y la corrida usa
las mismas reglas que Studio City: `test_fixtures.py` comprueba que `checks.py`
no nombra ningún dominio.

**Lo que este vertical añade al argumento.** El primer caso podía leerse como
«un auditor de pagos». El segundo es un flujo de pedidos, devoluciones y
cancelaciones —otro vocabulario, otra base de datos, otro equipo— y el veredicto
lo produce el mismo conjunto de reglas. Eso es lo que se compra: no un chequeo de
Mercado Pago, sino un invariante sobre el grafo.

## 2 ter. El séptimo caso: público, y el fixture sale del código

Los seis fixtures anteriores declaran `verificable_publicamente: false`: el
delta de alertas se ve, el código detrás no. `v0.1.4` cierra esa brecha con
[`examples/ecommerce_referencia/`](examples/ecommerce_referencia), donde el
fixture **no está transcrito a mano**: lo emite un extractor que lee las
sentencias `UPDATE … SET estado = …` de dos árboles de código versionados en
este mismo repositorio y deriva de cada `WHERE` el estado de origen de la arista.

| árbol | transiciones | RC | hallazgos |
|---|---|---|---|
| [`referencia_publica_pre_fix.json`](tests/fixtures/referencia_publica_pre_fix.json) | 12 | **1** | **13**: `FSM001`×1, `FSM005`×4, `FSM008`×6, `FSM010`×1, `FSM011`×1 |
| [`referencia_publica_post_fix.json`](tests/fixtures/referencia_publica_post_fix.json) | 5 | **0** | ninguno; conservación cerrada (frontera 0) |

Los trece salen de **un** `WHERE` ausente. Sin guarda de origen, `marcarPagado`
tiene una arista hacia sí mismo con `+69900` y el ciclo es `P2` —el mismo webhook
entregado dos veces cobra dos veces—; las cinco aristas de `pagar` más la de
`reembolsar` mueven dinero sin clave de idempotencia (`FSM008`×6, uno por arista
y no por función); con el ciclo abierto el saldo llega a `-69900` (`E1 → R3`) y a
`+139800` (`P1 → P2`). En `post_fix` la guarda **es** la clave: la segunda
entrega afecta cero filas y la conservación cierra con cinco estados de saldo.

**Lo que se puede comprobar sin confiar en este README.** El extractor no importa
el motor (`tests/test_extraer.py` lo prohíbe), el CI regenera con `--check` y
falla si el fixture commiteado no es lo que el código produce, y si un escritor
no está declarado o su guarda no se puede leer el resultado es `RC 2` con
`archivo:línea` —nunca una arista inventada—. `procedencia.verificable_publicamente`
es `true` porque las dos entradas de la medición —código y declaración— viajan
en el repositorio. Detalle y límites: [`examples/ecommerce_referencia/README.md`](examples/ecommerce_referencia/README.md).

## 3. Uso

```console
pip install -e .
fsm-ledger-guard scan flujo.json                      # resumen humano
fsm-ledger-guard scan flujo.json --json               # hallazgos en JSON
fsm-ledger-guard scan flujo.json --sarif out.sarif    # SARIF 2.1.0
fsm-ledger-guard scan flujo.json --recibo recibo.json # recibo conservation/1
fsm-ledger-guard scan a.json b.json c.json            # varios grafos, un RC
fsm-ledger-guard scan flujo.json --depth 12           # profundidad de conservación
fsm-ledger-guard scan flujo.json --exigir-medido      # procedencia no medida ⇒ RC 2
```

### El documento `fsm-ledger/1`

```json
{
  "schema": "fsm-ledger/1",
  "dominio": "studio-city/reservas",
  "inicial": "pendiente",
  "procedencia": { "repo": "org/repo", "commit": "95ea4a71", "medido": true },
  "recursos": {
    "escrow": { "unidad": "centavos", "minimo": 0, "maximo": 35000, "saldo_inicial": 0 }
  },
  "estados": [
    { "nombre": "pendiente", "terminal": false },
    { "nombre": "pagada", "terminal": false },
    { "nombre": "cancelada", "terminal": true }
  ],
  "transiciones": [
    {
      "id": "P3",
      "de": "pendiente",
      "evento": "pagar",
      "a": "pagada",
      "delta": { "escrow": 35000 },
      "atomico": true,
      "idem_key": "preferencia_id"
    }
  ]
}
```

`delta` acepta enteros (en la unidad del recurso) o `{"valor": 350, "unidad": "pesos"}`
cuando la arista declara su propia unidad y hay que notar el desajuste.
`atomico: false` e `idem_key: null` son los valores por omisión **declarados**:
el instrumento no los supone seguros.

## 4. Las reglas

| regla | clase | qué caza | tipo |
|---|---|---|---|
| `FSM001` | `CICLO_CON_FUGA` | ciclo con delta neto ≠ 0: recurso ilimitado por vuelta | exacto |
| `FSM002` | `ESTADO_INALCANZABLE` | estado sin camino desde el inicial | exacto |
| `FSM003` | `TRANSICION_INALCANZABLE` | transición sobre un estado inalcanzable | exacto |
| `FSM004` | `COMPONENTE_SIN_SALIDA` | componente fuertemente conexa sin estado terminal | exacto |
| `FSM005` | `TERMINAL_CON_SALIDA` | estado declarado terminal que todavía transiciona | exacto |
| `FSM006` | `RECURSO_RETENIDO_SIN_SALIDA` | recurso que entra y ninguna arista disminuye | exacto |
| `FSM007` | `MOVIMIENTO_NO_ATOMICO` | dinero que se mueve fuera del cambio de estado | declarativo |
| `FSM008` | `MOVIMIENTO_SIN_IDEM` | dinero movido sin clave de idempotencia | declarativo |
| `FSM009` | `UNIDAD_INCONSISTENTE` | una arista declara pesos sobre un recurso en centavos | exacto |
| `FSM010` | `SALDO_NEGATIVO` | ruta alcanzable que extrae lo que no hay | acotado |
| `FSM011` | `COTA_EXCEDIDA` | el saldo supera el máximo: la misma reserva cobrada dos veces | acotado |

«Acotado» significa: dentro de la profundidad pedida; agotarla es `RC 2`, no un
verde. `FSM006` responde en dos alcances: **global** (ninguna arista disminuye el
recurso: exacto, no necesita $\varphi$) y **por estado** (hay aristas que
disminuyen, pero algunos estados no alcanzan ninguna). Si un ciclo deja el saldo
indefinido, el alcance por estado se publica como `NO_MEDIDO` en la cobertura en
vez de inventar un número.

## 5. La escalera

| RC | significado |
|---|---|
| `0` | sin hallazgos **y** conservación medida |
| `1` | hay al menos un hallazgo |
| `2` | `NO_MEDIDO`: la exploración no cerró, o se exigió procedencia medida y no lo es |
| `4` | uso: el documento no es `fsm-ledger/1` legible, o los argumentos no cuadran |

El orden no es `max()`: `4 > 1 > 2 > 0`. Un hallazgo medido pesa más que una
rama sin medir; un `NO_MEDIDO` nunca se lee como cero.

## 6. Integración con `conservation-ledger`

El recibo publica los términos (`dominio` y `cubetas`) y deja que el verificador
rehaga la resta:

```console
$ fsm-ledger-guard scan tests/fixtures/studio_city_pre_fix.json --recibo r.json -q
recibo r.json
$ python -m conservation_ledger verify r.json
```

**Límite que conviene leer dos veces:** que `conservation-ledger` devuelva
`CONSERVADO` significa que **la partición del auditor está completa** (ninguna
transición se perdió por el camino), **no** que el dinero conserve. El veredicto
sobre el dinero es el RC del auditor, que viaja en `auditoria.rc`. Por eso el
recibo declara `declarado.rc` como `0` o `4` (¿cierra la partición?) y no como el
RC de la auditoría: en la escala de `conservation-ledger` un `2` o un `4` en
`declarado` provocan `DISCREPANCIA`, y una partición que sí cierra quedaría
marcada como rota. `tests/test_interop.py` fija ese comportamiento con el
verificador real, no con una copia.

## 7. GitHub Code Scanning

```yaml
permissions:
  contents: read
  security-events: write
steps:
  - run: pip install -e . && fsm-ledger-guard scan flujo.json --sarif out.sarif || true
  - uses: github/codeql-action/upload-sarif@v4
    with:
      sarif_file: out.sarif
```

Una **categoría por análisis**: el Action rechaza varios `run` bajo la misma
categoría (`does not support uploading multiple SARIF runs with the same
category`, medido en la corrida 45724438171). Sin `security-events: write` el
SARIF se valida y se sube como artefacto, pero no llega a la pestaña Security.

Cada resultado lleva `ruleId` (`FSM001`…), `level`, la línea del fixture,
`partialFingerprints` estable entre corridas y, en `properties`, el
`contraejemplo` completo. Los archivos de `evidence/` se validaron contra el
esquema oficial `sarif-schema-2.1.0.json` con `jsonschema` (Draft-07): cero
errores. `.github/workflows/verify.yml` audita los ocho fixtures en cada push y
exige `1 / 1 / 1 / 0` para Studio City, `1 / 0` para Moon & Rain y `1 / 0` para
el caso público, que antes regenera con `--check`: un fixture que no es lo que el
código produce no llega a auditarse.

Medición viva, 26-Nov-2026 @ `92d8d8d`, corrida 45752250121: la pestaña
Security de este repositorio publica **28 alertas** — `FSM008`×10 (idempotencia),
`FSM006`×4 (el escrow de cada acto posterior al parche, más el importe retenido
de la tienda), `FSM005`×4, `FSM001`×3 (los ciclos de dos aristas), `FSM011`×2
(cupo por encima de su máximo), `FSM009`×2 (unidades), `FSM010`×1, `FSM004`×1 y
`FSM002`×1 (el estado sin escritor y el componente sin salida de Moon & Rain).
Son las 8 de `pre_fix`, las 3 de `post_fix`, la de `f7`, las 3 de
`tienda-pre_fix` y las **13 del caso público**: cada acto se sube con categoría
distinta a propósito, porque lo que se demuestra es el delta entre ellos
—**8 → 3 → 1** sobre Studio City, **3 → 0** sobre Moon & Rain y **13 → 0** sobre
el ejemplo público—, no un conteo. Las categorías `post_fix`,
`tienda-post_fix` y `referencia-post_fix` no aportan ninguna: los parches
cerraron los hallazgos y el motor no cambió.

Como hook de pre-commit, el instrumento audita los documentos que terminen en
`.fsm.json`:

```yaml
repos:
  - repo: https://github.com/alexisromtz-lab/fsm-ledger-guard
    rev: v0.1.4
    hooks: [{ id: fsm-ledger-guard }]
```

## 8. Reproducir

```console
python -m unittest discover -s tests -t tests -v
python -m fsm_ledger_guard scan tests/fixtures/studio_city_pre_fix.json
python -m fsm_ledger_guard scan tests/fixtures/moon_and_rain_pre_fix.json

# el caso público: el fixture se vuelve a extraer del código antes de auditarlo
python examples/ecommerce_referencia/extraer.py --arbol pre_fix \
  --salida /tmp/ref_pre.json && diff /tmp/ref_pre.json tests/fixtures/referencia_publica_pre_fix.json
python -m fsm_ledger_guard scan tests/fixtures/referencia_publica_pre_fix.json
```

Los artefactos ya generados de los actos están en [`evidence/`](evidence).

## 9. Cómo citar

El paquete depositado es **v0.1.4** con su evidencia. Se cita por DOI, no por el repositorio: el
repositorio cambia y el depósito no. Hay dos DOI y sirven a cosas distintas:

- **Concepto** — `10.5281/zenodo.24546807` — resuelve **siempre a la última versión**. Úsalo para
  decir «este software existe» (es el del escudo de arriba).
- **Versión** — `10.5281/zenodo.24548850` — fija **v0.1.4**, lo que efectivamente se leyó. Úsalo
  en una cita.

> Román Martínez, José Alexis (2026). *alexisromtz-lab/fsm-ledger-guard: v0.1.4 — el caso público
> cuyo fixture se extrae del código, no se transcribe* [Software]. Zenodo.
> <https://doi.org/10.5281/zenodo.24548850>

```bibtex
@software{fsm_ledger_guard_014,
  author    = {Román Martínez, José Alexis},
  title     = {alexisromtz-lab/fsm-ledger-guard: v0.1.4 --- el caso público cuyo
               fixture se extrae del código, no se transcribe},
  year      = 2026,
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.24548850},
  url       = {https://doi.org/10.5281/zenodo.24548850}
}
```

La primera versión depositada (**v0.1.2**, la pieza «de ocho hallazgos a uno») sigue disponible y no
se retira: `10.5281/zenodo.24546808`.

## Licencia

MIT.
