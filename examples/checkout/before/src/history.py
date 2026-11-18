def read_raw_order_history(storage: object) -> tuple[bytes, ...]:
    return storage.read_all()
