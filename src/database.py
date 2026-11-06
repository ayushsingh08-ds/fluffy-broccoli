from datetime import datetime, timezone
import os
import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    """Connects to SQLite at db_path, ensures parent directory exists,

    and enables foreign key constraint enforcement.
    """
    # Create parent directories if they don't exist yet
    parent_dir = os.path.dirname(db_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)

    # SQLite disables foreign key checks by default; explicitly enable them
    conn.execute("PRAGMA foreign_keys = ON;")

    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Creates the customers, orders, and pipeline_state tables along with required indexes

    if they do not already exist.
    """
    create_customers_table = """
    CREATE TABLE IF NOT EXISTS customers (
        customer_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        city TEXT NOT NULL
    );
    """

    create_orders_table = """
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT PRIMARY KEY,
        customer_id TEXT NOT NULL,
        order_date TEXT NOT NULL,
        product_id TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        subtotal REAL NOT NULL,
        tax_amount REAL NOT NULL,
        total_amount REAL NOT NULL,
        processed_at TEXT NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
    );
    """

    # Table to track the watermark for incremental ETL runs
    create_pipeline_state_table = """
    CREATE TABLE IF NOT EXISTS pipeline_state (
        pipeline_name TEXT PRIMARY KEY,
        last_processed_watermark TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """

    # Indexes to speed up queries by customer and order date
    create_idx_orders_customer = """
    CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
    """
    create_idx_orders_date = """
    CREATE INDEX IF NOT EXISTS idx_orders_order_date ON orders(order_date);
    """

    with conn:
        conn.execute(create_customers_table)
        conn.execute(create_orders_table)
        conn.execute(create_pipeline_state_table)
        conn.execute(create_idx_orders_customer)
        conn.execute(create_idx_orders_date)


def load_customers(conn: sqlite3.Connection, customers: list[dict]) -> int:
    """Inserts customer records into the customers table in an idempotent manner.

    If a customer already exists, updates their name, email, and city.

    Returns:
        int: The number of customer records processed.
    """
    if not customers:
        return 0

    # Upsert query: insert new record or update existing fields on conflict
    upsert_query = """
    INSERT INTO customers (customer_id, name, email, city)
    VALUES (:customer_id, :name, :email, :city)
    ON CONFLICT(customer_id) DO UPDATE SET
        name = excluded.name,
        email = excluded.email,
        city = excluded.city;
    """

    with conn:
        conn.executemany(upsert_query, customers)

    return len(customers)


def load_orders(conn: sqlite3.Connection, orders: list[dict]) -> int:
    """Inserts transformed order records into the orders table in an idempotent manner.

    If an order already exists, it is ignored (DO NOTHING).

    Returns:
        int: The number of order records processed.
    """
    if not orders:
        return 0

    insert_query = """
    INSERT INTO orders (
        order_id,
        customer_id,
        order_date,
        product_id,
        quantity,
        unit_price,
        subtotal,
        tax_amount,
        total_amount,
        processed_at
    )
    VALUES (
        :order_id,
        :customer_id,
        :order_date,
        :product_id,
        :quantity,
        :unit_price,
        :subtotal,
        :tax_amount,
        :total_amount,
        :processed_at
    )
    ON CONFLICT(order_id) DO NOTHING;
    """

    with conn:
        conn.executemany(insert_query, orders)

    return len(orders)


def get_last_watermark(
    conn: sqlite3.Connection,
    pipeline_name: str = "orders_etl"
) -> str | None:
    """Retrieves the last processed watermark for the given pipeline name.

    Returns None if no watermark has been recorded yet.
    """
    query = """
    SELECT last_processed_watermark
    FROM pipeline_state
    WHERE pipeline_name = ?;
    """
    cursor = conn.cursor()
    cursor.execute(query, (pipeline_name,))
    row = cursor.fetchone()
    return row[0] if row else None


def update_watermark(
    conn: sqlite3.Connection,
    watermark: str,
    pipeline_name: str = "orders_etl"
) -> None:
    """Upserts the latest watermark and UTC timestamp for the specified pipeline."""
    now_utc = datetime.now(timezone.utc).isoformat()
    upsert_query = """
    INSERT INTO pipeline_state (pipeline_name, last_processed_watermark, updated_at)
    VALUES (?, ?, ?)
    ON CONFLICT(pipeline_name) DO UPDATE SET
        last_processed_watermark = excluded.last_processed_watermark,
        updated_at = excluded.updated_at;
    """
    with conn:
        conn.execute(upsert_query, (pipeline_name, watermark, now_utc))
