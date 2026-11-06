import sqlite3
import pytest

from src.database import init_db, load_customers, load_orders
from src.transformation import deduplicate_orders, transform_orders
from src.validation import validate_order


@pytest.fixture
def in_memory_db():
    """Provides an in-memory SQLite database initialized with schemas

    and foreign keys enabled.
    """
    conn = sqlite3.connect(":memory:")
    # SQLite requires foreign keys to be explicitly enabled
    conn.execute("PRAGMA foreign_keys = ON;")
    init_db(conn)
    yield conn
    conn.close()


def test_validate_order_valid():
    """Asserts that a valid order dictionary returns is_valid == True,

    empty errors, and correctly type-casted fields (quantity as int, unit_price as float).
    """
    valid_raw = {
        "order_id": "1001",
        "customer_id": "C001",
        "order_date": "2026-03-01",
        "product_id": "P101",
        "quantity": "2",
        "unit_price": "25.50",
    }

    result = validate_order(valid_raw)

    assert result.is_valid is True
    assert result.errors == []
    assert result.record["order_id"] == "1001"
    assert result.record["quantity"] == 2
    assert isinstance(result.record["quantity"], int)
    assert result.record["unit_price"] == 25.50
    assert isinstance(result.record["unit_price"], float)
    assert result.record["order_date"] == "2026-03-01"


def test_validate_order_invalid_fields():
    """Tests invalid fields (e.g. negative quantity, negative unit_price,

    invalid order_date="2026-13-45", missing customer_id).
    Asserts is_valid == False and verifies multiple errors are captured.
    """
    invalid_raw = {
        "order_id": "1002",
        "customer_id": "",
        "order_date": "2026-13-45",
        "product_id": "P102",
        "quantity": "-3",
        "unit_price": "-10.00",
    }

    result = validate_order(invalid_raw)

    assert result.is_valid is False
    assert result.record == invalid_raw  # Raw unparsed data is preserved for DLQ
    # Check that each invalid field produced an error message
    assert len(result.errors) >= 4
    error_text = " ".join(result.errors)
    assert "customer_id" in error_text
    assert "order_date" in error_text
    assert "quantity" in error_text
    assert "unit_price" in error_text


def test_deduplicate_orders():
    """Feeds a list of orders containing duplicate order_ids (e.g., two orders with order_id="1001").

    Asserts that the output contains exactly 1 unique order and 1 duplicate order.
    """
    orders = [
        {"order_id": "1001", "customer_id": "C001", "quantity": 2, "unit_price": 25.0},
        {"order_id": "1001", "customer_id": "C001", "quantity": 5, "unit_price": 25.0},
    ]

    unique_orders, duplicate_orders = deduplicate_orders(orders)

    assert len(unique_orders) == 1
    assert len(duplicate_orders) == 1
    # Ensure the first occurrence was kept in unique_orders
    assert unique_orders[0]["quantity"] == 2
    assert duplicate_orders[0]["quantity"] == 5


def test_transform_orders():
    """Feeds a valid order (e.g. quantity=2, unit_price=25.00, tax_rate=0.08).

    Asserts:
    - subtotal == 50.00
    - tax_amount == 4.00
    - total_amount == 54.00
    - processed_at timestamp exists.
    """
    orders = [
        {"order_id": "1001", "quantity": 2, "unit_price": 25.00}
    ]

    transformed = transform_orders(orders, tax_rate=0.08)

    assert len(transformed) == 1
    record = transformed[0]
    assert record["subtotal"] == 50.00
    assert record["tax_amount"] == 4.00
    assert record["total_amount"] == 54.00
    assert "processed_at" in record
    assert isinstance(record["processed_at"], str)


def test_database_load_and_idempotency(in_memory_db):
    """Inserts customer C001, then inserts an order.

    Asserts that the record exists in SQLite.
    Attempts to insert the exact same order a second time.
    Asserts that the table still has exactly 1 order row (verifying idempotency).
    """
    # 1. Insert customer C001 first to satisfy foreign key requirement
    customers = [
        {"customer_id": "C001", "name": "Alice", "email": "alice@test.com", "city": "New York"}
    ]
    load_customers(in_memory_db, customers)

    # 2. Insert order 1001
    orders = [
        {
            "order_id": "1001",
            "customer_id": "C001",
            "order_date": "2026-03-01",
            "product_id": "P101",
            "quantity": 2,
            "unit_price": 25.0,
            "subtotal": 50.0,
            "tax_amount": 4.0,
            "total_amount": 54.0,
            "processed_at": "2026-03-01T12:00:00Z",
        }
    ]
    load_orders(in_memory_db, orders)

    cursor = in_memory_db.cursor()
    cursor.execute("SELECT COUNT(*) FROM orders WHERE order_id = '1001'")
    assert cursor.fetchone()[0] == 1

    # 3. Attempt to insert the exact same order a second time
    load_orders(in_memory_db, orders)

    # Idempotency check: row count must still remain exactly 1
    cursor.execute("SELECT COUNT(*) FROM orders WHERE order_id = '1001'")
    assert cursor.fetchone()[0] == 1


def test_foreign_key_enforcement(in_memory_db):
    """Attempts to insert an order referencing a non-existent customer_id (e.g. "C999").

    Uses pytest.raises(sqlite3.IntegrityError) to verify that SQLite rejects the orphan record.
    """
    orphan_order = [
        {
            "order_id": "9999",
            "customer_id": "C999",  # Does not exist in customers table
            "order_date": "2026-03-01",
            "product_id": "P101",
            "quantity": 1,
            "unit_price": 10.0,
            "subtotal": 10.0,
            "tax_amount": 0.8,
            "total_amount": 10.8,
            "processed_at": "2026-03-01T12:00:00Z",
        }
    ]

    with pytest.raises(sqlite3.IntegrityError):
        load_orders(in_memory_db, orphan_order)

