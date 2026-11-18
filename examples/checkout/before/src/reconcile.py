import json

from .orders import _rows_for_reconciliation


def pending_orders(storage: object) -> tuple[dict[str, object], ...]:
    orders = []
    for raw in _rows_for_reconciliation(storage):
        order = json.loads(raw)
        if order["status"] == "pending":
            orders.append(order)
    return tuple(orders)


def pending_total(storage: object) -> float:
    return sum(order["total"] for order in pending_orders(storage))
