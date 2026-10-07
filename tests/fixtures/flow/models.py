"""Domain models: discount rules per customer tier."""


class Discount:
    """A fractional discount rate (0.2 means twenty percent off)."""

    def __init__(self, rate):
        self.rate = rate

    @classmethod
    def for_customer(cls, customer):
        """Return the discount for a customer dict with an optional vip flag."""
        if customer.get("vip"):
            return cls(0.2)
        return cls(0.0)
