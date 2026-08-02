class RecruiterAIError(Exception):
    """Base exception for recruiter pipeline failures."""


class ConfigurationError(RecruiterAIError):
    """Raised when required configuration is missing or invalid."""


class ProviderError(RecruiterAIError):
    """Raised when a provider request or response fails."""


class ParsingError(RecruiterAIError):
    """Raised when a provider response cannot be parsed into the expected model."""


class RankingError(RecruiterAIError):
    """Raised when ranking cannot be completed."""


class ExportError(RecruiterAIError):
    """Raised when exporting results fails."""
