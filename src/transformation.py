from datetime import datetime, timezone


def deduplicate_orders(
    orders: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Separates unique orders from duplicates based on 'order_id'.
    The FIRST occurrence of an order_id is kept; subsequent occurrences
    are categorized as duplicates.

    Returns:
        tuple: (unique_orders, duplicate_orders)
    """
    seen_order_ids = set()
    unique_orders = []
    duplicate_orders = []

    for order in orders:
        order_id = order.get("order_id")

        # If we have already seen this order_id, it is a duplicate
        if order_id in seen_order_ids:
            duplicate_orders.append(order)
        else:
            # First time seeing this order_id, keep it in uniques
            seen_order_ids.add(order_id)
            unique_orders.append(order)

    return unique_orders, duplicate_orders


def transform_orders(
    orders: list[dict],
    tax_rate: float = 0.08
) -> list[dict]:
    """Enriches validated and deduplicated order records with financial metrics.

    For each order:
    1. Calculate subtotal = quantity * unit_price
    2. Calculate tax_amount = subtotal * tax_rate
    3. Calculate total_amount = subtotal + tax_amount
    4. Round all financial metrics to 2 decimal places.
    5. Add a new field: 'processed_at' (current UTC timestamp in ISO 8601).

    Returns:
        list[dict]: New list of enriched dictionaries (do not mutate inputs in-place).
    """
    enriched_orders = []
    # Generate the UTC timestamp once for this processing run
    current_time = datetime.now(timezone.utc).isoformat()

    for order in orders:
        # Create a shallow copy so we do not mutate the input dictionary
        transformed_order = order.copy()

        # Compute monetary values using quantity and unit price
        subtotal = transformed_order["quantity"] * transformed_order["unit_price"]
        tax_amount = subtotal * tax_rate
        total_amount = subtotal + tax_amount

        # Store calculated metrics rounded to 2 decimal places
        transformed_order["subtotal"] = round(subtotal, 2)
        transformed_order["tax_amount"] = round(tax_amount, 2)
        transformed_order["total_amount"] = round(total_amount, 2)

        # Attach processing timestamp
        transformed_order["processed_at"] = current_time

        enriched_orders.append(transformed_order)

    return enriched_orders
