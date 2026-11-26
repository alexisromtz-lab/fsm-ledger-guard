# El caso público verificable

Los otros seis fixtures de este repositorio salen de dos workers privados: un
lector ve el delta de alertas, pero no el código detrás. Este directorio cierra
esa brecha con lo que se puede auditar entero sin abrir un solo repositorio
privado: **el fixture no se escribe a mano, se extrae del código** y cualquiera
puede volver a extraerlo.

Es una **reducción**, no un tercer sistema en producción. Cuatro escritores, cinco
estados, una columna. Existe para que el lector rehaga la medición en diez
segundos y compruebe que el motor no lleva reglas de ningún dominio.

## Las dos piezas

| archivo | qué es | quién manda |
|---|---|---|
| `maquina.json` | estados, eventos con su delta de `dinero` y qué escritor de qué árbol corresponde a qué evento | el dominio: es lo único escrito a mano |
| `<arbol>/src/*.js` | las sentencias `UPDATE … SET estado = …` reales, con su `WHERE` | el código: de aquí salen origen e idempotencia de cada arista |
| `extraer.py` | lee el código, lo cruza con `maquina.json` y emite `fsm-ledger/1` | nadie: es el instrumento, y es fail-closed |

La arista **no** está declarada en ningún sitio. `extraer.py` lee la guarda
(`estado = 'x'` o `estado IN (…)`) y de ahí saca el estado de origen; si no hay
guarda, emite una arista por cada estado declarado y lo anota. Por eso el mismo
`marcarPagado` produce cinco aristas en `pre_fix` y una en `post_fix`.

## Cómo se rehace

```console
python examples/ecommerce_referencia/extraer.py --arbol pre_fix \
  --salida tests/fixtures/referencia_publica_pre_fix.json
python examples/ecommerce_referencia/extraer.py --arbol post_fix \
  --salida tests/fixtures/referencia_publica_post_fix.json
python -m fsm_ledger_guard scan tests/fixtures/referencia_publica_pre_fix.json   # RC 1
python -m fsm_ledger_guard scan tests/fixtures/referencia_publica_post_fix.json  # RC 0
```

Con `--check` en vez de escribir: compara el fixture commiteado con lo que el
código produce y devuelve RC 1 si divergen. Eso es lo que corre el CI en cada
push, antes de auditar: un fixture que envejece deja de ser evidencia.

## Lo que mide

| árbol | transiciones | RC | hallazgos |
|---|---|---|---|
| `pre_fix` | 12 | **1** | 13: `FSM001`×1, `FSM005`×4, `FSM008`×6, `FSM010`×1, `FSM011`×1 |
| `post_fix` | 5 | **0** | ninguno; conservación cerrada (frontera 0) |

Los trece del `pre_fix` son tres defectos de una línea de código:

- **`FSM001` · el ciclo es `P2`.** `marcarPagado` no comprueba el origen, así
  que el estado `pagado` tiene una arista hacia sí mismo con `+69900`: el mismo
  webhook entregado dos veces cobra dos veces, y el saldo de `pagado` no queda
  definido.
- **`FSM008` ×6.** Las cinco aristas sin guarda de `pagar` más la de
  `reembolsar` mueven dinero sin clave de idempotencia. Seis, porque el motor
  informa por arista y no por función: la no guarda contamina todas.
- **`FSM010` y `FSM011`.** Con el ciclo abierto, el saldo llega a `-69900`
  (`E1 → R3`, reembolsar un pedido que nunca se cobró) y a `+139800`
  (`P1 → P2`, el máximo declarado es un pedido).

En `post_fix` la guarda hace de clave: `AND estado IN ('nuevo')` deja el segundo
webhook en cero filas, y la conservación cierra con cinco estados de saldo.

## Lo que no es

- No es un framework ni una plantilla de worker: los `.js` no se ejecutan, se leen.
- No sustituye a la auditoría de un flujo real: mide lo que el DSL declara sobre
  el código que cita. Un flujo cuyo dinero no se mueve por `UPDATE` no entra.
- No es el motor. `extraer.py` no importa `fsm_ledger_guard` y hay un test que lo
  comprueba: si el extractor dependiera del juez, el fixture no probaría nada.
