# fsm-ledger-guard

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
procedencia alexisromtz-lab/estudios-worker @ 95ea4a71
grafo     5 estados · 13 transiciones · huella 2cf20a52cd9a9fd7

[FSM001] error   CICLO_CON_FUGA
          escrow: el ciclo P9 → P3 tiene delta neto +350 centavos por vuelta; el saldo de confirmada, pagada, pendiente no está definido
          contraejemplo: P9 → P3
          tests/fixtures/studio_city_pre_fix.json:60
…
RC 1
```

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

## 2. El caso real: Studio City, tres actos

Los tres fixtures de [`tests/fixtures/`](tests/fixtures) son un flujo de reservas
con anticipo medido en un SaaS en producción. Están en el repositorio porque el
instrumento se juzga por lo que encontró, no por su README.

| acto | commit | RC | qué dice |
|---|---|---|---|
| [`studio_city_pre_fix.json`](tests/fixtures/studio_city_pre_fix.json) | `95ea4a71` | **1** · 8 hallazgos | el dinero se puede cobrar dos veces y nadie lo suelta |
| [`studio_city_post_fix.json`](tests/fixtures/studio_city_post_fix.json) | `e67b9d5a` | **1** · 3 hallazgos | ciclo cerrado y unidades normalizadas; falta la idempotencia |
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

**Objetivo.** `studio_city_objetivo.json` añade el estado terminal `reembolsado`
con su salida de `escrow`, la captura en `atendida` y las claves de idempotencia.
Da RC 0 — y su `procedencia.medido` es `false`, así que con `--exigir-medido`
responde **RC 2**. Una proyección se publica como proyección.

```console
$ fsm-ledger-guard scan tests/fixtures/studio_city_objetivo.json --exigir-medido
…
RC 2
```

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
- run: pip install -e . && fsm-ledger-guard scan flujo.json --sarif out.sarif || true
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: out.sarif
```

Cada resultado lleva `ruleId` (`FSM001`…), `level`, la línea del fixture,
`partialFingerprints` estable entre corridas y, en `properties`, el
`contraejemplo` completo. Los tres archivos de `evidence/` se validaron contra el
esquema oficial `sarif-schema-2.1.0.json` con `jsonschema` (Draft-07): cero
errores. `.github/workflows/verify.yml` audita los tres fixtures en cada push y
exige `1 / 1 / 0`.

Como hook de pre-commit, el instrumento audita los documentos que terminen en
`.fsm.json`:

```yaml
repos:
  - repo: https://github.com/alexisromtz-lab/fsm-ledger-guard
    rev: v0.1.0
    hooks: [{ id: fsm-ledger-guard }]
```

## 8. Reproducir

```console
python -m unittest discover -s tests -t tests -v
python -m fsm_ledger_guard scan tests/fixtures/studio_city_pre_fix.json
```

Los artefactos ya generados de los tres actos están en [`evidence/`](evidence).

## Licencia

MIT.
