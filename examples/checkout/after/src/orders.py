from .quotes import quote


def place_order(product_id: str, quantity: int, customer: str, storage: object) -> dict[str, object]:
    details = quote(product_id, quantity)
    if not isinstance(customer, str):
        raise TypeError("customer must be a string")
    if not customer.strip():
        raise ValueError("customer is required")

    rows = storage.read_all()
    order = {
        "order_id": f"order-{len(rows) + 1}",
        "product_id": product_id,
        "quantity": quantity,
        "unit_price": details["unit_price"],
        "total": details["total"],
        "status": "pending",
        "customer": customer,
    }
    storage.write_order(order)
    return order
