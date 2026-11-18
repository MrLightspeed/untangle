from .catalog import price_for


def quote(product_id: str, quantity: int) -> dict[str, object]:
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise TypeError("quantity must be an integer")
    if quantity <= 0:
        raise ValueError("quantity must be positive")

    unit_price = price_for(product_id)
    return {
        "product_id": product_id,
        "quantity": quantity,
        "unit_price": unit_price,
        "total": unit_price * quantity,
    }
