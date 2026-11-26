// Panel de administracion: cancelar un pedido. La guarda existe porque el boton
// solo se dibuja para pedidos impagos; el extractor la lee del codigo, no del
// comentario.

export async function cancelarPedido(db, pedido_id) {
  const sql = "UPDATE pedidos SET estado = 'cancelado' WHERE pedido_id = ? AND estado = 'nuevo'";
  await db.prepare(sql).bind(pedido_id).run();
}
