from uuid import UUID


class DuplicateDraftError(Exception):
    """Raised when a personal identifier matches another draft application."""

    def __init__(self, existing_application_id: UUID, message: str = "Duplicate draft found") -> None:
        super().__init__(message)
        self.existing_application_id = existing_application_id
