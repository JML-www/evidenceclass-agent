"""Stable retrieval errors exposed to ingestion and publication callers."""


class RetrievalError(RuntimeError):
    pass


class SourceRegistrationError(RetrievalError):
    pass


class PublicationGateError(RetrievalError):
    pass


class DocumentParseError(RetrievalError):
    def __init__(self, message: str, *, page: int | None = None) -> None:
        self.page = page
        prefix = f"page {page}: " if page is not None else ""
        super().__init__(prefix + message)


class RetrievalConfigurationError(RetrievalError):
    pass
