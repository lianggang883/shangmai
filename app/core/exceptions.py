"""Core exception definitions."""


class NotFoundError(Exception):
    """Raised when a requested resource is not found."""

    def __init__(self, message: str = "Resource not found"):
        self.message = message
        super().__init__(self.message)


class BusinessError(Exception):
    """Raised for general business logic errors."""

    def __init__(self, message: str = "Business error"):
        self.message = message
        super().__init__(self.message)


class InsufficientActionPowerError(Exception):
    """Raised when a member lacks sufficient action power balance."""

    def __init__(self, required: int, available: int):
        self.required = required
        self.available = available
        self.message = f"Insufficient action power: required {required}, available {available}"
        super().__init__(self.message)