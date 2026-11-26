// Panel de administracion: cancelar un pedido. La guarda deja de ser una
// promesa del formulario y pasa a ser parte de la sentencia.

export async function cancelarPedido(db, pedido_id) {
  const sql = "UPDATE pedidos SET estado = 'cancelado' WHERE pedido_id = ? AND estado IN ('nuevo')";
  await db.prepare(sql).bind(pedido_id).run();
}
