import json
from collections.abc import Iterator


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

    def write_order(self, order: dict[str, object]) -> bytes:
        raw = json.dumps(order, separators=(",", ":")).encode("utf-8")
        self.append(raw)
        return raw

    def read_orders(self) -> Iterator[dict[str, object]]:
        for raw in self.read_all():
            yield json.loads(raw)
