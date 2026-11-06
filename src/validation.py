from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any


@dataclass
class ValidationResult:
    is_valid: bool
    record: dict[str, Any]
    errors: list[str]


def validate_order(raw_record: dict) -> ValidationResult:
    """Validates a raw order record against business rules and schemas.

    Rules enforced:
    1. order_id: Required (non-empty string or positive integer).
    2. customer_id: Required non-empty string.
    3. order_date: Required string in valid ISO format YYYY-MM-DD.
    4. product_id: Required non-empty string.
    5. quantity: Must be convertible to int and strictly > 0.
    6. unit_price: Must be convertible to float and >= 0.0.

    Returns:
        ValidationResult with:
        - If failed: is_valid=False, record=raw_record, errors=[all accumulated error messages]
        - If passed: is_valid=True, record=cleaned_and_typecast_dict, errors=[]
    """
    errors: list[str] = []
    cleaned_record: dict[str, Any] = {}

    # 1. order_id: Required (non-empty string or positive integer)
    order_id = raw_record.get("order_id")
    if order_id is None:
        errors.append("order_id is missing or null.")
    elif isinstance(order_id, int):
        if order_id <= 0:
            errors.append(f"order_id must be a positive integer, got {order_id}.")
        else:
            cleaned_record["order_id"] = order_id
    elif isinstance(order_id, str):
        val = order_id.strip()
        if not val:
            errors.append("order_id cannot be an empty string.")
        else:
            cleaned_record["order_id"] = val
    else:
        errors.append(f"order_id must be a string or integer, got {type(order_id).__name__}.")

    # 2. customer_id: Required non-empty string
    customer_id = raw_record.get("customer_id")
    if customer_id is None:
        errors.append("customer_id is missing or null.")
    elif isinstance(customer_id, str):
        val = customer_id.strip()
        if not val:
            errors.append("customer_id cannot be an empty string.")
        else:
            cleaned_record["customer_id"] = val
    else:
        errors.append(f"customer_id must be a string, got {type(customer_id).__name__}.")

    # 3. order_date: Required string in valid ISO format YYYY-MM-DD
    order_date = raw_record.get("order_date")
    if order_date is None:
        errors.append("order_date is missing or null.")
    elif isinstance(order_date, str):
        val = order_date.strip()
        try:
            parsed_date = datetime.strptime(val, "%Y-%m-%d")
            # Preserve / standardize to YYYY-MM-DD string
            cleaned_record["order_date"] = parsed_date.strftime("%Y-%m-%d")
        except ValueError:
            errors.append(f"order_date '{val}' is not a valid date in ISO format YYYY-MM-DD.")
    else:
        errors.append(f"order_date must be a string, got {type(order_date).__name__}.")

    # 4. product_id: Required non-empty string
    product_id = raw_record.get("product_id")
    if product_id is None:
        errors.append("product_id is missing or null.")
    elif isinstance(product_id, str):
        val = product_id.strip()
        if not val:
            errors.append("product_id cannot be an empty string.")
        else:
            cleaned_record["product_id"] = val
    else:
        errors.append(f"product_id must be a string, got {type(product_id).__name__}.")

    # 5. quantity: Must be convertible to int and strictly > 0
    quantity = raw_record.get("quantity")
    if quantity is None or (isinstance(quantity, str) and not quantity.strip()):
        errors.append("quantity is missing or empty.")
    else:
        try:
            qty_int = int(quantity)
            if qty_int <= 0:
                errors.append(f"quantity must be strictly greater than 0, got {qty_int}.")
            else:
                cleaned_record["quantity"] = qty_int
        except (ValueError, TypeError):
            errors.append(f"quantity '{quantity}' cannot be converted to int.")

    # 6. unit_price: Must be convertible to float and >= 0.0
    unit_price = raw_record.get("unit_price")
    if unit_price is None or (isinstance(unit_price, str) and not unit_price.strip()):
        errors.append("unit_price is missing or empty.")
    else:
        try:
            price_float = float(unit_price)
            if price_float < 0.0:
                errors.append(f"unit_price must be greater than or equal to 0.0, got {price_float}.")
            else:
                cleaned_record["unit_price"] = price_float
        except (ValueError, TypeError):
            errors.append(f"unit_price '{unit_price}' cannot be converted to float.")

    # Outcome
    if errors:
        return ValidationResult(is_valid=False, record=raw_record, errors=errors)

    return ValidationResult(is_valid=True, record=cleaned_record, errors=[])


def route_to_dlq(
    invalid_results: list[ValidationResult],
    dlq_file_path: str,
    source_file: str,
) -> int:
    """Appends invalid records to a Dead Letter Queue file in JSON Lines (.jsonl) format.

    Each line written to dlq_file_path is a standalone JSON object:
    {
        "timestamp": "2026-11-05T18:08:51Z",
        "source_file": "orders.csv",
        "errors": ["..."],
        "raw_record": {...}
    }

    Returns:
        int: The number of records written to the DLQ.
    """
    # Filter to ensure we only quarantine invalid results
    records_to_write = [res for res in invalid_results if not res.is_valid]
    if not records_to_write:
        return 0

    # Ensure parent directory exists before writing
    parent_dir = os.path.dirname(dlq_file_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    # Use datetime.now(timezone.utc).isoformat() for standardized UTC timestamps
    timestamp = datetime.now(timezone.utc).isoformat()

    count = 0
    # Open file in append mode ('a') with UTF-8 encoding
    with open(dlq_file_path, mode="a", encoding="utf-8") as f:
        for res in records_to_write:
            dlq_entry = {
                "timestamp": timestamp,
                "source_file": source_file,
                "errors": res.errors,
                "raw_record": res.record,
            }
            # Write line-by-line in JSON Lines format (.jsonl)
            f.write(json.dumps(dlq_entry) + "\n")
            count += 1

    return count



