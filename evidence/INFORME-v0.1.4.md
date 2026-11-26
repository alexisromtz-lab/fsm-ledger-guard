# INFORME — v0.1.4

**Qué cambia en esta versión.** El sexto informe dejó dos verticales privados
medidos y una deuda declarada en cada uno de sus seis fixtures:
`verificable_publicamente: false`. Un lector veía el delta de alertas y no podía
ver el código que lo producía. `v0.1.4` cierra esa deuda con un séptimo caso que
cualquiera audita entero dentro de este repositorio — y, a diferencia de los
otros seis, **el fixture no está escrito a mano**: lo emite un extractor que lee
las sentencias `UPDATE … SET estado = …` de dos árboles de código que también
viajan aquí.

## Las tres mediciones, en una tabla

| caso | qué es | RC | hallazgos | verificable |
|---|---|---|---|---|
| Studio City `95ea4a71 → e67b9d5a → 251aaff8` | flujo de reservas con anticipo, repo privado | 1 / 1 / 1 | 8 → 3 → 1 | no |
| Moon & Rain `93f5bcdd → d144256f` | pedidos y devoluciones, repo privado | 1 → 0 | 3 → 0 | no |
| **ejemplo público `pre_fix → post_fix`** | **cuatro escritores, cinco estados, repo público** | **1 → 0** | **13 → 0** | **sí** |

Las tres las juzga el mismo `checks.py`, con las mismas once reglas y sin una
línea de código por dominio. `tests/test_fixtures.py` lo prohíbe explícitamente:
si el motor nombra un dominio, el test enrojece.

## El caso público: el fixture sale del código

El directorio `examples/ecommerce_referencia/` tiene tres piezas:

- `maquina.json` — lo único escrito a mano: los cinco estados, los cuatro eventos
  con su delta de dinero en centavos y qué escritor de qué árbol corresponde a
  qué evento.
- `pre_fix/src/*.js` y `post_fix/src/*.js` — las sentencias reales, con su
  `WHERE`. Aquí no se ejecuta nada; se lee.
- `extraer.py` — lee cada `UPDATE`, le asocia la función que lo contiene y deriva
  el estado de origen de la guarda (`estado = 'x'` o `estado IN (…)`). Si no hay
  guarda, emite una arista por cada estado declarado y lo anota.

Ninguna arista está declarada en el DSL. Por eso el mismo `marcarPagado` produce
**cinco** aristas en `pre_fix` (una por cada estado, incluidos los terminales) y
**una** en `post_fix`.

### Lo que mide el `pre_fix`

Doce transiciones, **RC 1**, trece hallazgos:

| regla | n | qué nombra |
|---|---|---|
| `FSM001` | 1 | el ciclo `P2` tiene delta neto +69900 centavos por vuelta |
| `FSM005` | 4 | `devuelto` y `cancelado` se declaran terminales y cuatro aristas los abandonan |
| `FSM008` | 6 | las cinco aristas de `pagar` y la de `reembolsar` mueven dinero sin clave de idempotencia |
| `FSM010` | 1 | el saldo llega a −69900 en `devuelto`, camino `E1 → R3` |
| `FSM011` | 1 | el saldo llega a +139800 en `pagado`, máximo declarado +69900, camino `P1 → P2` |

Los trece salen de **un** `WHERE` ausente. El ciclo `P2` es el caso que importa:
`marcarPagado` no comprueba el origen, así que `pagado` tiene una arista hacia sí
mismo con `+69900`. El mismo webhook entregado dos veces cobra dos veces, y el
saldo de `pagado` no queda definido. `FSM008` dispara seis veces porque el motor
informa por arista y no por función: la no guarda contamina todas las que salen
del estado.

La conservación queda **ABIERTA**: 30 estados de saldo, 71 aplicaciones,
profundidad 8, frontera 4. La retención de dinero queda `NO_MEDIDO` con la causa
declarada —«el saldo no está definido (FSM001)»—, no como cero.

### Lo que mide el `post_fix`

Cinco transiciones, **RC 0**, sin hallazgos. La guarda **es** la clave de
idempotencia: `AND estado IN ('nuevo')` deja la segunda entrega del webhook en
cero filas. La conservación cierra: 5 estados de saldo, 5 aplicaciones, frontera
0, y la retención pasa a `MEDIDO: todo saldo positivo tiene salida`.

## El contrato del extractor: fail-closed o no hay fixture

`extraer.py` devuelve RC 2 —y ningún documento— cuando:

- hay un `UPDATE … SET estado` que no puede leer (SQL en varias líneas, otro
  delimitador, tabla compuesta);
- una escritura está fuera de una función nombrada;
- el `WHERE` menciona `estado` pero no como `= <literal>` ni `IN (…)` (el mensaje
  cita el fragmento que no supo leer, con `archivo:línea`);
- un escritor del árbol no está declarado en `maquina.json`, o una declaración no
  tiene código que la respalde.

Los cuatro están probados con copias temporales en `tests/test_extraer.py`. El
extractor **no importa el motor** —hay un test que lo comprueba—: si lo hiciera,
el fixture dependería del juez y no probaría nada.

El CI regenera los dos fixtures con `--check` en cada push, antes de auditar. Un
fixture que no es lo que el código produce no llega a auditarse.

## Cómo se rehace la medición

```console
pip install -e .
python examples/ecommerce_referencia/extraer.py --arbol pre_fix \
  --salida /tmp/ref_pre.json && diff /tmp/ref_pre.json tests/fixtures/referencia_publica_pre_fix.json
fsm-ledger-guard scan tests/fixtures/referencia_publica_pre_fix.json    # RC 1, 13 hallazgos
fsm-ledger-guard scan tests/fixtures/referencia_publica_post_fix.json   # RC 0
```

Estado de la corrida que publica este informe: sobre `92d8d8d` (el commit que
añade el ejemplo; `ad8c69b` solo inscribe la medición en el README), corrida
45752250121, 6/6 trabajos verdes, 138 pruebas en las cinco versiones de Python
soportadas (3.9 a 3.13), y 28 alertas vivas en la pestaña Security —las 13 del
caso público incluidas, subidas con categoría propia para que el delta se vea.

## Lo que este informe no afirma

- No afirma que el ejemplo sea un tercer sistema en producción: es una
  **reducción** de cuatro escritores y cinco estados, y existe para que la
  medición se pueda rehacer sin abrir un repositorio privado.
- No afirma que los dos verticales privados sean auditables por un tercero: su
  `verificable_publicamente` sigue siendo `false`, y el fixture sigue siendo el
  estado del grafo, no una paráfrasis de él.
- No afirma que las once reglas cubran todo defecto de flujo monetario. Cubren
  los que este motor sabe nombrar: ciclos con fuga, estados muertos, transiciones
  inalcanzables, asimetrías de liberación, movimiento sin idempotencia, unidades
  mixtas, saldo fuera de cota y conservación acotada a profundidad declarada.

---

Román Martínez, José Alexis · ORCID [0009-0001-9116-075X](https://orcid.org/0009-0001-9116-075X) · MIT
