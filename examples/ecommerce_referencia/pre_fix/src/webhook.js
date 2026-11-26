// Reduccion publica del patron que aparecio en dos verticales distintos:
// manejadores de webhook que escriben `estado` sin comprobar el estado de
// origen. Este arbol es el "antes": dos de las tres escrituras no guardan su
// origen, y ninguna declara clave de idempotencia en maquina.json.
//
// El extractor (../extraer.py) lee estas sentencias; no hay ninguna arista
// declarada a mano.

export async function marcarPagado(db, evento) {
  const sql = "UPDATE pedidos SET estado = 'pagado' WHERE pedido_id = ?";
  await db.prepare(sql).bind(evento.pedido_id).run();
}

export async function marcarEnviado(db, evento) {
  const sql = "UPDATE pedidos SET estado = 'enviado' WHERE pedido_id = ?";
  await db.prepare(sql).bind(evento.pedido_id).run();
}

export async function marcarDevuelto(db, evento) {
  // La unica escritura del arbol que ya comprobaba su origen: un reembolso solo
  // tiene sentido sobre un pedido embarcado.
  const sql = "UPDATE pedidos SET estado = 'devuelto' WHERE pedido_id = ? AND estado = 'enviado'";
  await db.prepare(sql).bind(evento.pedido_id).run();
}
