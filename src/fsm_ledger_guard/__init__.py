"""fsm-ledger-guard — auditoría algebraica de máquinas de estados financieras.

Certifica, antes de desplegar, que un grafo de pagos o pedidos no puede crear ni
perder unidades: ciclos con fuga, estados muertos, recursos retenidos sin salida
y transiciones monetarias sin guarda. Emite SARIF 2.1.0 y un recibo
``conservation/1`` que ``conservation-ledger`` recomputa por su cuenta.
"""
from __future__ import annotations

__version__ = "0.1.1"
