from .catalog import price_for


class InMemoryStorage:
    def __init__(self) -> None:
        self._rows: list[bytes] = []
        self.operations: list[str] = []

    def append(self, raw: bytes) -> None:
        self.operations.append("append")
        self._rows.append(bytes(raw))

    def read_all(self) -> tuple[bytes, ...]:
        self.operations.append("read_all")
        return tuple(self._rows)


def _catalog_price_for(product_id: str) -> float:
    return price_for(product_id)
