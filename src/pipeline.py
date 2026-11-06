import logging
import os
import sys

from src.database import (
    get_connection,
    get_last_watermark,
    init_db,
    load_customers,
    load_orders,
    update_watermark,
)
from src.ingestion import load_csv_records, load_json_records
from src.transformation import deduplicate_orders, transform_orders
from src.validation import route_to_dlq, validate_order


def setup_logging(log_path: str = "logs/pipeline.log") -> logging.Logger:
    """Configures and returns a logger that outputs to both console and a log file."""
    # Ensure the logs directory exists
    log_dir = os.path.dirname(log_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("ecommerce_pipeline")
    logger.setLevel(logging.INFO)

    # Avoid adding duplicate handlers if setup_logging is called multiple times
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
        )

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File handler
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def run_pipeline(
    data_dir: str = "data",
    db_path: str = "data/processed/ecommerce.db",
    incremental: bool = True
) -> dict:
    """Coordinates and executes the entire end-to-end data pipeline.

    Supports incremental ingestion based on watermark filtering.
    """
    logger = setup_logging()
    logger.info("Starting ecommerce data pipeline...")

    # Define paths based on data_dir
    customers_path = os.path.join(data_dir, "raw", "customers.json")
    orders_path = os.path.join(data_dir, "raw", "orders.csv")
    dlq_path = os.path.join(data_dir, "quarantine", "dlq.jsonl")

    conn = None
    summary = {
        "customers_loaded": 0,
        "orders_ingested": 0,
        "orders_valid": 0,
        "orders_invalid": 0,
        "orders_duplicates": 0,
        "orders_loaded": 0,
        "status": "FAILED",
    }

    try:
        # Step 1: Connect to SQLite and initialize schema
        logger.info(f"Connecting to database at {db_path}...")
        conn = get_connection(db_path)
        init_db(conn)
        logger.info("Database schema and indexes initialized.")

        # Step 2: Check watermark for incremental processing
        last_watermark = get_last_watermark(conn)

        # Step 3: Ingest and load customer records
        logger.info(f"Loading customers from {customers_path}...")
        raw_customers = load_json_records(customers_path)
        customers_loaded = load_customers(conn, raw_customers)
        summary["customers_loaded"] = customers_loaded
        logger.info(f"Successfully processed and loaded {customers_loaded} customers.")

        # Step 4: Ingest order records
        logger.info(f"Ingesting orders from {orders_path}...")
        raw_orders = load_csv_records(orders_path)
        summary["orders_ingested"] = len(raw_orders)
        logger.info(f"Ingested {len(raw_orders)} raw order records.")

        # Step 5: Filter for incremental run if watermark exists
        if incremental and last_watermark is not None:
            logger.info(f"Incremental run: filtering for orders newer than {last_watermark}")
            raw_orders = [
                row for row in raw_orders
                if row.get("order_date") and row.get("order_date") > last_watermark
            ]

            if not raw_orders:
                logger.info("No new records to process.")
                summary["status"] = "SUCCESS"
                return summary

        # Step 6: Validate each order record
        valid_orders = []
        invalid_results = []

        for record in raw_orders:
            result = validate_order(record)
            if result.is_valid:
                valid_orders.append(result.record)
            else:
                invalid_results.append(result)

        summary["orders_valid"] = len(valid_orders)
        summary["orders_invalid"] = len(invalid_results)
        logger.info(f"Validation finished: {len(valid_orders)} valid, {len(invalid_results)} invalid.")

        # Step 7: Route invalid records to DLQ (Dead Letter Queue)
        if invalid_results:
            logger.warning(f"Routing {len(invalid_results)} invalid orders to DLQ: {dlq_path}...")
            route_to_dlq(invalid_results, dlq_path, source_file=os.path.basename(orders_path))

        # Step 8: Deduplicate valid orders
        unique_orders, duplicate_orders = deduplicate_orders(valid_orders)
        summary["orders_duplicates"] = len(duplicate_orders)
        if duplicate_orders:
            logger.warning(f"Found and skipped {len(duplicate_orders)} duplicate orders.")

        # Step 9: Transform valid and unique orders
        logger.info(f"Transforming {len(unique_orders)} unique orders...")
        transformed_orders = transform_orders(unique_orders)

        # Step 10: Load transformed orders into database
        orders_loaded = load_orders(conn, transformed_orders)
        summary["orders_loaded"] = orders_loaded
        logger.info(f"Successfully loaded {orders_loaded} orders into the database.")

        # Step 11: Update watermark if new orders were loaded
        if transformed_orders:
            max_order_date = max(order["order_date"] for order in transformed_orders)
            update_watermark(conn, max_order_date)
            logger.info(f"Updated watermark to '{max_order_date}'.")

        summary["status"] = "SUCCESS"
        logger.info(f"Pipeline completed successfully. Summary: {summary}")

    except Exception:
        logger.exception("Pipeline execution failed due to an unexpected error.")
        raise
    finally:
        # Always cleanly close the database connection
        if conn is not None:
            conn.close()
            logger.info("Database connection closed.")

    return summary


if __name__ == "__main__":
    run_pipeline()
