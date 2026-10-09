"""Create a pseudonymized, minimized CSV from customer transaction exports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


OUTPUT_COLUMNS = (
    "customer_key",
    "transaction_date",
    "product_category",
    "amount_gbp",
    "channel",
    "region",
)
REQUIRED_INPUT_COLUMNS = {
    "customer_id",
    "transaction_date",
    "product_category",
    "amount_gbp",
    "channel",
    "region",
}


@dataclass(frozen=True)
class PreparationSummary:
    rows_written: int
    rows_without_customer_id: int
    rows_without_amount: int
    rows_without_valid_transaction_date: int
    rows_with_invalid_transaction_date: int


def _format_amount(value: str, row_number: int) -> str:
    cleaned = value.strip().replace(",", "")
    if not cleaned:
        return ""
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(
            f"Invalid amount_gbp at CSV row {row_number}; expected a number."
        ) from exc
    if not amount.is_finite():
        raise ValueError(
            f"Invalid amount_gbp at CSV row {row_number}; expected a finite number."
        )
    return format(amount, "f")


def _normalize_transaction_date(value: str, row_number: int) -> str | None:
    cleaned = value.strip()
    if cleaned.casefold() in {"", "not recorded", "00/00/0000"}:
        return None

    try:
        return date.fromisoformat(cleaned).isoformat()
    except ValueError:
        try:
            return datetime.strptime(cleaned, "%d/%m/%Y").date().isoformat()
        except ValueError:
            try:
                return datetime.strptime(cleaned, "%Y-%d-%m").date().isoformat()
            except ValueError as exc:
                raise ValueError(
                    f"Invalid transaction_date at CSV row {row_number}; "
                    "expected YYYY-MM-DD, DD/MM/YYYY, or YYYY-DD-MM."
                ) from exc


def prepare_transactions(
    input_path: Path,
    output_path: Path,
    hmac_key: str,
) -> PreparationSummary:
    """Write only approved transaction fields and an HMAC customer key."""
    if not hmac_key:
        raise ValueError("A non-empty customer ID HMAC key is required.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    rows_without_customer_id = 0
    rows_without_amount = 0
    rows_without_valid_transaction_date = 0
    rows_with_invalid_transaction_date = 0
    temporary_path: Path | None = None

    try:
        with input_path.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            input_columns = set(reader.fieldnames or ())
            missing_columns = REQUIRED_INPUT_COLUMNS - input_columns
            if missing_columns:
                missing = ", ".join(sorted(missing_columns))
                raise ValueError(f"Input CSV is missing required columns: {missing}")

            with tempfile.NamedTemporaryFile(
                mode="w",
                newline="",
                encoding="utf-8",
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as destination:
                temporary_path = Path(destination.name)
                os.chmod(temporary_path, 0o600)
                writer = csv.DictWriter(
                    destination,
                    fieldnames=OUTPUT_COLUMNS,
                    extrasaction="ignore",
                )
                writer.writeheader()

                for row_number, row in enumerate(reader, start=2):
                    try:
                        normalized_date = _normalize_transaction_date(
                            row.get("transaction_date") or "", row_number
                        )
                    except ValueError:
                        rows_with_invalid_transaction_date += 1
                        continue
                    if normalized_date is None:
                        rows_without_valid_transaction_date += 1
                        continue

                    customer_id = (row.get("customer_id") or "").strip()
                    if not customer_id:
                        rows_without_customer_id += 1
                        continue

                    raw_amount = row.get("amount_gbp") or ""
                    amount = _format_amount(raw_amount, row_number)
                    if not amount:
                        rows_without_amount += 1

                    customer_key = hmac.new(
                        hmac_key.encode("utf-8"),
                        customer_id.encode("utf-8"),
                        hashlib.sha256,
                    ).hexdigest()
                    writer.writerow(
                        {
                            "customer_key": customer_key,
                            "transaction_date": normalized_date,
                            "product_category": (row.get("product_category") or "").strip(),
                            "amount_gbp": amount,
                            "channel": (row.get("channel") or "").strip(),
                            "region": (row.get("region") or "").strip(),
                        }
                    )
                    rows_written += 1

        temporary_path.replace(output_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    return PreparationSummary(
        rows_written=rows_written,
        rows_without_customer_id=rows_without_customer_id,
        rows_without_amount=rows_without_amount,
        rows_without_valid_transaction_date=rows_without_valid_transaction_date,
        rows_with_invalid_transaction_date=rows_with_invalid_transaction_date,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write a privacy-reduced transaction CSV for the segmentation demo."
    )
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    args = parser.parse_args()

    hmac_key = os.environ.get("CUSTOMER_ID_HMAC_KEY", "")
    summary = prepare_transactions(args.input_csv, args.output_csv, hmac_key)
    print(f"Sanitized transactions written: {summary.rows_written}")
    print(f"Transactions omitted (missing customer ID): {summary.rows_without_customer_id}")
    print(
        "Transactions omitted (blank/unrecorded transaction date): "
        f"{summary.rows_without_valid_transaction_date}"
    )
    print(
        "Transactions omitted (invalid transaction date): "
        f"{summary.rows_with_invalid_transaction_date}"
    )
    print(f"Transactions with blank amount retained: {summary.rows_without_amount}")
    print(f"Output CSV: {args.output_csv}")


if __name__ == "__main__":
    main()
