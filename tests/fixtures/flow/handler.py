"""Order handler: receives an order dict, delegates pricing to the service."""

from service import price_order


def handle_order(order):
    """Price an order dict and return the total with its currency."""
    total = price_order(order)
    return {"total": total, "currency": order["currency"]}
