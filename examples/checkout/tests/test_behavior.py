"""Shared behavior checks for both checkout source snapshots."""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import unittest
from pathlib import Path


def load_snapshot(path: Path) -> None:
    sys.path.insert(0, str(path.resolve()))


parser = argparse.ArgumentParser()
parser.add_argument("--snapshot", required=True, type=Path)
args = parser.parse_args()
sys.argv = [sys.argv[0]]
load_snapshot(args.snapshot)

from src.orders import place_order  # noqa: E402
from src.catalog import price_for  # noqa: E402
from src.quotes import quote  # noqa: E402
from src.reconcile import pending_orders, pending_total  # noqa: E402
from src.storage import InMemoryStorage  # noqa: E402


EXPECTED_ORDER = {
    "order_id": "order-1",
    "product_id": "tea",
    "quantity": 2,
    "unit_price": 3.5,
    "total": 7.0,
    "status": "pending",
    "customer": "Ada",
}
EXPECTED_BYTES = (
    b'{"order_id":"order-1","product_id":"tea","quantity":2,'
    b'"unit_price":3.5,"total":7.0,"status":"pending","customer":"Ada"}'
)


class CheckoutBehaviorTests(unittest.TestCase):
    def test_public_call_signatures_and_quote_output(self) -> None:
        self.assertEqual(str(inspect.signature(price_for)), "(product_id: str) -> float")
        self.assertEqual(
            str(inspect.signature(quote)),
            "(product_id: str, quantity: int) -> dict[str, object]",
        )
        self.assertEqual(
            str(inspect.signature(place_order)),
            "(product_id: str, quantity: int, customer: str, storage: object) -> dict[str, object]",
        )
        self.assertEqual(
            str(inspect.signature(pending_orders)),
            "(storage: object) -> tuple[dict[str, object], ...]",
        )
        self.assertEqual(
            str(inspect.signature(pending_total)),
            "(storage: object) -> float",
        )
        self.assertEqual(
            str(inspect.signature(InMemoryStorage.append)),
            "(self, raw: bytes) -> None",
        )
        self.assertEqual(
            str(inspect.signature(InMemoryStorage.read_all)),
            "(self) -> tuple[bytes, ...]",
        )
        self.assertEqual(
            quote("tea", 2),
            {"product_id": "tea", "quantity": 2, "unit_price": 3.5, "total": 7.0},
        )

    def test_order_bytes_key_order_and_write_order(self) -> None:
        storage = InMemoryStorage()

        result = place_order("tea", 2, "Ada", storage)

        self.assertEqual(result, EXPECTED_ORDER)
        self.assertEqual(storage.operations, ["read_all", "append"])
        self.assertEqual(storage.read_all(), (EXPECTED_BYTES,))

    def test_invalid_inputs_keep_errors_and_do_not_touch_storage(self) -> None:
        cases = (
            (("missing", 1, "Ada"), KeyError, ("unknown product: missing",)),
            (("tea", 0, "Ada"), ValueError, ("quantity must be positive",)),
            (("tea", True, "Ada"), TypeError, ("quantity must be an integer",)),
            (("tea", 1, None), TypeError, ("customer must be a string",)),
            (("tea", 1, "  "), ValueError, ("customer is required",)),
        )
        for arguments, error_type, error_args in cases:
            with self.subTest(arguments=arguments):
                storage = InMemoryStorage()
                with self.assertRaises(error_type) as caught:
                    place_order(*arguments, storage)
                self.assertEqual(type(caught.exception), error_type)
                self.assertEqual(caught.exception.args, error_args)
                self.assertEqual(storage.operations, [])
                self.assertEqual(storage._rows, [])

    def test_order_ids_accumulate_and_reconciliation_filters_in_order(self) -> None:
        storage = InMemoryStorage()
        first = place_order("tea", 1, "Ada", storage)
        second = place_order("coffee", 2, "Lin", storage)
        self.assertEqual((first["order_id"], second["order_id"]), ("order-1", "order-2"))

        storage = InMemoryStorage()
        for raw in (
            b'{"order_id":"first","product_id":"tea","quantity":1,"unit_price":3.5,"total":3.5,"status":"pending","customer":"Ada"}',
            b'{"order_id":"settled","product_id":"coffee","quantity":1,"unit_price":4.25,"total":4.25,"status":"paid","customer":"Lin"}',
            b'{"order_id":"last","product_id":"coffee","quantity":2,"unit_price":4.25,"total":8.5,"status":"pending","customer":"Bo"}',
        ):
            storage.append(raw)

        orders = pending_orders(storage)
        self.assertEqual([order["order_id"] for order in orders], ["first", "last"])
        self.assertEqual(pending_total(storage), 12.0)

    def test_reads_return_an_ordered_snapshot(self) -> None:
        storage = InMemoryStorage()
        storage.append(b"first")
        snapshot = storage.read_all()
        storage.append(b"second")

        self.assertEqual(snapshot, (b"first",))
        self.assertEqual(storage.read_all(), (b"first", b"second"))

    def test_malformed_rows_keep_json_error_type_and_arguments(self) -> None:
        storage = InMemoryStorage()
        storage.append(b"{")
        with self.assertRaises(json.JSONDecodeError) as expected:
            json.loads(b"{")
        with self.assertRaises(json.JSONDecodeError) as caught:
            pending_orders(storage)

        self.assertEqual(type(caught.exception), type(expected.exception))
        self.assertEqual(caught.exception.args, expected.exception.args)

    def test_reconciliation_preserves_the_first_row_error(self) -> None:
        storage = InMemoryStorage()
        storage.append(b"{}")
        storage.append(b"{")

        with self.assertRaises(KeyError) as caught:
            pending_orders(storage)

        self.assertEqual(caught.exception.args, ("status",))


if __name__ == "__main__":
    unittest.main(verbosity=2)
