def pending_orders(storage: object) -> tuple[dict[str, object], ...]:
    orders = []
    for order in storage.read_orders():
        if order["status"] == "pending":
            orders.append(order)
    return tuple(orders)


def pending_total(storage: object) -> float:
    return sum(order["total"] for order in pending_orders(storage))
