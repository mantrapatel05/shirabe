# Miniature fixture for Shirabe evaluation (original example, MIT, see ../README.md).
"""Pricing service: applies customer discount rules to an order."""

from models import Discount


def price_order(order):
    """Return the order amount after the customer's discount rate."""
    discount = Discount.for_customer(order["customer"])
    return order["amount"] * (1 - discount.rate)
