"""Tests for local CSV minimization and pseudonymization."""

import csv
import tempfile
import unittest
from pathlib import Path

from prepare_transactions import OUTPUT_COLUMNS, prepare_transactions


class PrepareTransactionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.input_path = self.root / "raw.csv"
        self.output_path = self.root / "sanitized.csv"

    def write_source(self, rows: list[dict[str, str]]) -> None:
        columns = [
            "transaction_id",
            "customer_id",
            "customer_name",
            "email",
            "phone",
            "date_of_birth",
            "transaction_date",
            "product_category",
            "amount_gbp",
            "channel",
            "region",
            "last_updated",
        ]
        with self.input_path.open("w", newline="", encoding="utf-8") as source:
            writer = csv.DictWriter(source, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    def test_drops_direct_identifiers_and_hmacs_customer_id(self) -> None:
        self.write_source(
            [
                {
                    "transaction_id": "transaction-secret",
                    "customer_id": "customer-123",
                    "customer_name": "Private Name",
                    "email": "private@example.invalid",
                    "phone": "0000000000",
                    "date_of_birth": "1980-01-01",
                    "transaction_date": "01/03/2025",
                    "product_category": "Books",
                    "amount_gbp": "1,234.50",
                    "channel": "Online",
                    "region": "North",
                    "last_updated": "2025-03-02",
                }
            ]
        )

        summary = prepare_transactions(
            self.input_path, self.output_path, "test-private-key"
        )

        with self.output_path.open(newline="", encoding="utf-8") as output:
            reader = csv.DictReader(output)
            records = list(reader)
        self.assertEqual(tuple(reader.fieldnames or ()), OUTPUT_COLUMNS)
        self.assertEqual(summary.rows_written, 1)
        self.assertEqual(records[0]["amount_gbp"], "1234.50")
        self.assertEqual(records[0]["transaction_date"], "2025-03-01")
        self.assertNotIn("customer-123", self.output_path.read_text())
        for private_value in (
            "transaction-secret",
            "Private Name",
            "private@example.invalid",
            "0000000000",
            "1980-01-01",
        ):
            self.assertNotIn(private_value, self.output_path.read_text())

    def test_omits_missing_customer_id_and_retains_blank_amount(self) -> None:
        self.write_source(
            [
                {
                    "customer_id": "",
                    "transaction_date": "2025-03-01",
                    "amount_gbp": "10",
                },
                {
                    "customer_id": "customer-456",
                    "transaction_date": "2025-03-02",
                    "amount_gbp": "",
                },
            ]
        )

        summary = prepare_transactions(
            self.input_path, self.output_path, "test-private-key"
        )

        self.assertEqual(summary.rows_written, 1)
        self.assertEqual(summary.rows_without_customer_id, 1)
        self.assertEqual(summary.rows_without_amount, 1)
        with self.output_path.open(newline="", encoding="utf-8") as output:
            records = list(csv.DictReader(output))
        self.assertEqual(records[0]["amount_gbp"], "")

    def test_omits_unrecorded_date_and_reports_it(self) -> None:
        self.write_source(
            [
                {
                    "customer_id": "customer-789",
                    "transaction_date": "not recorded",
                    "amount_gbp": "10",
                },
                {
                    "customer_id": "customer-789",
                    "transaction_date": "00/00/0000",
                    "amount_gbp": "20",
                },
            ]
        )

        summary = prepare_transactions(
            self.input_path, self.output_path, "test-private-key"
        )

        self.assertEqual(summary.rows_written, 0)
        self.assertEqual(summary.rows_without_valid_transaction_date, 2)

    def test_normalizes_year_day_month_date(self) -> None:
        self.write_source(
            [
                {
                    "customer_id": "customer-789",
                    "transaction_date": "2026-13-04",
                    "amount_gbp": "10",
                }
            ]
        )

        prepare_transactions(self.input_path, self.output_path, "test-private-key")

        with self.output_path.open(newline="", encoding="utf-8") as output:
            records = list(csv.DictReader(output))
        self.assertEqual(records[0]["transaction_date"], "2026-04-13")

    def test_omits_invalid_transaction_date_and_reports_it(self) -> None:
        self.write_source(
            [
                {
                    "customer_id": "customer-789",
                    "transaction_date": "not-a-date",
                    "amount_gbp": "10",
                }
            ]
        )

        summary = prepare_transactions(
            self.input_path, self.output_path, "test-private-key"
        )

        self.assertEqual(summary.rows_written, 0)
        self.assertEqual(summary.rows_with_invalid_transaction_date, 1)

    def test_requires_hmac_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "HMAC key"):
            prepare_transactions(self.input_path, self.output_path, "")


if __name__ == "__main__":
    unittest.main()
