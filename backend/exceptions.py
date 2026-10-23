"""Our own error types.

Each error carries the HTTP status code it should produce, so the API
layer can turn any of them into a proper JSON response automatically.
"""


class PriceHawkError(Exception):
    """Base class for all PriceHawk errors."""
    status_code = 500
    code = "error"  # machine-readable, so the extension never has to guess from the wording


class ValidationError(PriceHawkError):
    """The user sent something invalid (bad price, bad body...)."""
    status_code = 400
    code = "invalid"


class LimitReachedError(ValidationError):
    """This email already tracks the maximum number of products."""
    code = "limit_reached"


class UnsupportedURLError(ValidationError):
    """The URL is not a product page from a supported website."""


class ProductNotFoundError(PriceHawkError):
    status_code = 404


class DuplicateProductError(PriceHawkError):
    status_code = 409
    code = "duplicate"


class DemoModeError(PriceHawkError):
    """A demo-only feature was used while DEMO_MODE is off."""
    status_code = 403


class ScraperError(PriceHawkError):
    """The website could not be reached or gave a bad response."""
    status_code = 502


class PriceNotFoundError(ScraperError):
    """The page loaded, but the title/price was not where we expected."""
