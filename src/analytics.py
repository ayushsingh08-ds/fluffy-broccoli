import os
import sqlite3


def get_daily_revenue_report(conn: sqlite3.Connection) -> list[dict]:
    """Generates daily revenue metrics ordered chronologically by order_date.

    Metrics:
    - order_date
    - order_count: Total orders placed on that day
    - total_revenue: Sum of total_amount (rounded to 2 decimal places)
    - avg_order_value: Average total_amount per order (rounded to 2 decimal places)
    """
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    SELECT
        order_date,
        COUNT(order_id) AS order_count,
        ROUND(COALESCE(SUM(total_amount), 0.0), 2) AS total_revenue,
        ROUND(COALESCE(AVG(total_amount), 0.0), 2) AS avg_order_value
    FROM orders
    GROUP BY order_date
    ORDER BY order_date ASC;
    """

    cursor.execute(query)
    return [dict(row) for row in cursor.fetchall()]


def get_top_customers_report(conn: sqlite3.Connection, limit: int = 5) -> list[dict]:
    """Generates a ranking of top customers by total spending.

    Metrics:
    - customer_id
    - name
    - city
    - total_orders: Total count of orders placed by customer
    - total_spent: Total sum of total_amount spent (rounded to 2 decimal places)
    """
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Left join ensures customers with 0 orders can be safely queried without errors
    query = """
    SELECT
        c.customer_id,
        c.name,
        c.city,
        COUNT(o.order_id) AS total_orders,
        ROUND(COALESCE(SUM(o.total_amount), 0.0), 2) AS total_spent
    FROM customers c
    LEFT JOIN orders o ON c.customer_id = o.customer_id
    GROUP BY c.customer_id, c.name, c.city
    ORDER BY total_spent DESC
    LIMIT ?;
    """

    cursor.execute(query, (limit,))
    return [dict(row) for row in cursor.fetchall()]


def get_product_performance_report(conn: sqlite3.Connection) -> list[dict]:
    """Generates product performance metrics ordered by total revenue.

    Metrics:
    - product_id
    - units_sold: Total quantity sold
    - total_revenue: Total sum of subtotal (rounded to 2 decimal places)
    """
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
    SELECT
        product_id,
        COALESCE(SUM(quantity), 0) AS units_sold,
        ROUND(COALESCE(SUM(subtotal), 0.0), 2) AS total_revenue
    FROM orders
    GROUP BY product_id
    ORDER BY total_revenue DESC;
    """

    cursor.execute(query)
    return [dict(row) for row in cursor.fetchall()]


def generate_markdown_report(
    conn: sqlite3.Connection,
    output_path: str = "reports/summary.md"
) -> None:
    """Executes all analytical queries and exports a formatted Markdown business report."""
    # Ensure destination folder exists
    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    daily_rev = get_daily_revenue_report(conn)
    top_cust = get_top_customers_report(conn)
    prod_perf = get_product_performance_report(conn)

    # Build markdown sections
    lines = [
        "# E-Commerce Business Performance Summary",
        "",
        "This report is automatically generated from the processed orders and customers database.",
        "",
        "## 1. Daily Revenue Summary",
        "",
        "| Order Date | Order Count | Total Revenue ($) | Avg Order Value ($) |",
        "| :--- | :--- | :--- | :--- |",
    ]

    if daily_rev:
        for row in daily_rev:
            lines.append(
                f"| {row['order_date']} | {row['order_count']} | ${row['total_revenue']:.2f} | ${row['avg_order_value']:.2f} |"
            )
    else:
        lines.append("| No records | 0 | $0.00 | $0.00 |")

    lines.extend([
        "",
        "## 2. Top Customers",
        "",
        "| Customer ID | Name | City | Total Orders | Total Spent ($) |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ])

    if top_cust:
        for row in top_cust:
            lines.append(
                f"| {row['customer_id']} | {row['name']} | {row['city']} | {row['total_orders']} | ${row['total_spent']:.2f} |"
            )
    else:
        lines.append("| No records | N/A | N/A | 0 | $0.00 |")

    lines.extend([
        "",
        "## 3. Product Performance",
        "",
        "| Product ID | Units Sold | Total Revenue ($) |",
        "| :--- | :--- | :--- |",
    ])

    if prod_perf:
        for row in prod_perf:
            lines.append(
                f"| {row['product_id']} | {row['units_sold']} | ${row['total_revenue']:.2f} |"
            )
    else:
        lines.append("| No records | 0 | $0.00 |")

    lines.append("")

    # Write out the complete markdown document
    with open(output_path, mode="w", encoding="utf-8") as f:
        f.write("\n".join(lines))
