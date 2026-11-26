// El "despues": cada escritura declara desde que estados es legal, y esa
// declaracion es la unica fuente del origen de cada arista. La guarda hace
// ademas de clave de idempotencia: un webhook repetido encuentra el pedido ya
// fuera del origen y el UPDATE afecta cero filas.

export async function marcarPagado(db, evento) {
  const sql = "UPDATE pedidos SET estado = 'pagado' WHERE pedido_id = ? AND estado IN ('nuevo')";
  await db.prepare(sql).bind(evento.pedido_id).run();
}

export async function marcarEnviado(db, evento) {
  const sql = "UPDATE pedidos SET estado = 'enviado' WHERE pedido_id = ? AND estado IN ('pagado')";
  await db.prepare(sql).bind(evento.pedido_id).run();
}

export async function marcarDevuelto(db, evento) {
  // El reembolso cubre tambien el pedido pagado que nunca se embarcó: dejarlo
  // fuera era una asimetria de liberacion, no una regla de negocio.
  const sql = "UPDATE pedidos SET estado = 'devuelto' WHERE pedido_id = ? AND estado IN ('pagado','enviado')";
  await db.prepare(sql).bind(evento.pedido_id).run();
}
