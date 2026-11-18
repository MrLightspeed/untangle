import json

from .history import read_raw_order_history
from .quotes import quote
from .storage import _catalog_price_for


def _order_unit_price(product_id: str) -> float:
    return _catalog_price_for(product_id)


def _rows_for_reconciliation(storage: object) -> tuple[bytes, ...]:
    return read_raw_order_history(storage)


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
    raw = json.dumps(order, separators=(",", ":")).encode("utf-8")
    storage.append(raw)
    return order
