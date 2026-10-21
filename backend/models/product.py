"""The Product class: one tracked product."""


class Product:
    def __init__(self, id, title, url, current_price, target_price,
                 tracking_active, alert_sent, created_at, last_checked_at, last_error,
                 notify_email):
        self.id = id
        self.title = title
        self.url = url
        self.current_price = current_price
        self.target_price = target_price
        self.tracking_active = bool(tracking_active)  # SQLite stores 0/1
        self.alert_sent = bool(alert_sent)
        self.created_at = created_at
        self.last_checked_at = last_checked_at
        self.last_error = last_error
        self.notify_email = notify_email  # who receives the alert

    @classmethod
    def from_row(cls, row):
        """Build a Product from a database row (column names match the arguments)."""
        return cls(**dict(row))

    @property
    def price_gap(self):
        """current - target. Zero or negative means the target has been reached."""
        return round(self.current_price - self.target_price, 2)

    def to_dict(self):
        """Plain dictionary, ready to be sent as JSON."""
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "notify_email": self.notify_email,
            "current_price": self.current_price,
            "target_price": self.target_price,
            "price_gap": self.price_gap,
            "tracking_active": self.tracking_active,
            "alert_sent": self.alert_sent,
            "created_at": self.created_at,
            "last_checked_at": self.last_checked_at,
            "last_error": self.last_error,
        }

    def __repr__(self):
        return f"<Product {self.id}: {self.title} £{self.current_price} (target £{self.target_price})>"
