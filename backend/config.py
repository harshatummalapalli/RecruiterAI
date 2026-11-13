import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH, override=False)


class Settings(BaseModel):
    """Typed application settings loaded from the environment and .env file."""

    model_config = ConfigDict(extra="ignore")

    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    crustdata_api_key: Optional[str] = Field(default=None, description="CrustData API key")
    harvest_api_key: Optional[str] = Field(default=None, description="HarvestAPI (harvestapi.io) API key")
    unipile_api_key: Optional[str] = Field(default=None, description="Unipile app Account API Key (server-side; outreach/messaging). Never the MCP test key.")
    unipile_base_url: str = Field(default="https://api.unipile.com", description="Unipile API base URL")
    unipile_webhook_secret: Optional[str] = Field(default=None, description="Shared secret used to verify inbound Unipile webhooks")
    unipile_hosted_auth_domain: Optional[str] = Field(default=None, description="White-label Hosted Auth hostname (e.g. connect.dayzero.partners), verified with Unipile, so recruiters never see the vendor. Falls back to Unipile's host when unset.")
    harvest_enrichment_top_n: int = Field(default=25, description="How many top-ranked candidates to enrich via Harvest per search")
    harvest_enrichment_concurrency: int = Field(default=3, description="Max concurrent in-flight Harvest requests per search")
    discovery_page_size: int = Field(default=50, description="CrustData /person/search page size (results per query) — backend-owned, not the frontend's")
    discovery_max_pages: int = Field(default=1, description="Max CrustData pages fetched per query")
    # Per-recruiter outreach safety caps (rolling 24h) — keep LinkedIn/email
    # sending under the thresholds that get accounts restricted. Env-overridable.
    outreach_daily_invites: int = Field(default=20, description="Max LinkedIn connection invites per recruiter per rolling 24h")
    outreach_daily_messages: int = Field(default=40, description="Max LinkedIn messages/InMails per recruiter per rolling 24h")
    outreach_daily_emails: int = Field(default=100, description="Max outreach emails per recruiter per rolling 24h")
    google_client_id: Optional[str] = Field(default=None, description="Google OAuth Client ID")
    allowed_email_domain: Optional[str] = Field(default=None, description="Email domain allowed to log in")
    super_admin_email: Optional[str] = Field(default=None, description="The single email granted admin-only views (e.g. the live credit meter). Everyone else is an ordinary recruiter.")
    session_secret_key: Optional[str] = Field(default=None, description="Secret key used to sign session cookies")
    session_max_age_seconds: int = Field(default=43200, description="Session cookie lifetime in seconds")
    session_cookie_secure: bool = Field(default=False, description="Whether the session cookie requires HTTPS")

    @classmethod
    def from_environment(cls, env: Optional[dict[str, str]] = None) -> "Settings":
        source = env if env is not None else os.environ
        raw_values = {
            "openai_api_key": source.get("OPENAI_API_KEY"),
            "crustdata_api_key": source.get("CRUSTDATA_API_KEY"),
            "harvest_api_key": source.get("HARVEST_API_KEY"),
            "unipile_api_key": source.get("UNIPILE_API_KEY"),
            "unipile_webhook_secret": source.get("UNIPILE_WEBHOOK_SECRET"),
            "unipile_hosted_auth_domain": source.get("UNIPILE_HOSTED_AUTH_DOMAIN"),
            "google_client_id": source.get("GOOGLE_CLIENT_ID"),
            "allowed_email_domain": source.get("ALLOWED_EMAIL_DOMAIN"),
            "super_admin_email": source.get("SUPER_ADMIN_EMAIL"),
            "session_secret_key": source.get("SESSION_SECRET_KEY"),
            "session_cookie_secure": source.get("SESSION_COOKIE_SECURE"),
        }
        session_max_age = source.get("SESSION_MAX_AGE_SECONDS")
        if session_max_age is not None and str(session_max_age).strip():
            raw_values["session_max_age_seconds"] = session_max_age
        harvest_top_n = source.get("HARVEST_ENRICHMENT_TOP_N")
        if harvest_top_n is not None and str(harvest_top_n).strip():
            raw_values["harvest_enrichment_top_n"] = harvest_top_n
        harvest_concurrency = source.get("HARVEST_ENRICHMENT_CONCURRENCY")
        if harvest_concurrency is not None and str(harvest_concurrency).strip():
            raw_values["harvest_enrichment_concurrency"] = harvest_concurrency
        discovery_page_size = source.get("DISCOVERY_PAGE_SIZE")
        if discovery_page_size is not None and str(discovery_page_size).strip():
            raw_values["discovery_page_size"] = discovery_page_size
        discovery_max_pages = source.get("DISCOVERY_MAX_PAGES")
        if discovery_max_pages is not None and str(discovery_max_pages).strip():
            raw_values["discovery_max_pages"] = discovery_max_pages
        for env_key, field in (
            ("OUTREACH_DAILY_INVITES", "outreach_daily_invites"),
            ("OUTREACH_DAILY_MESSAGES", "outreach_daily_messages"),
            ("OUTREACH_DAILY_EMAILS", "outreach_daily_emails"),
        ):
            value = source.get(env_key)
            if value is not None and str(value).strip():
                raw_values[field] = value
        unipile_base_url = source.get("UNIPILE_BASE_URL")
        if unipile_base_url is not None and str(unipile_base_url).strip():
            raw_values["unipile_base_url"] = str(unipile_base_url).strip()
        return cls(**raw_values)

    @field_validator(
        "openai_api_key",
        "crustdata_api_key",
        "harvest_api_key",
        "unipile_api_key",
        "unipile_webhook_secret",
        "unipile_hosted_auth_domain",
        "google_client_id",
        "allowed_email_domain",
        "super_admin_email",
        "session_secret_key",
        mode="before",
    )
    @classmethod
    def _normalize_optional_value(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @field_validator("session_cookie_secure", mode="before")
    @classmethod
    def _normalize_bool_value(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in ("1", "true", "yes", "on")


_settings: Optional[Settings] = None
_settings_env_signature: Optional[tuple[Optional[str], ...]] = None


def get_settings() -> Settings:
    """Return the current settings object for the application."""
    global _settings, _settings_env_signature
    env_signature = (
        os.environ.get("OPENAI_API_KEY"),
        os.environ.get("CRUSTDATA_API_KEY"),
        os.environ.get("HARVEST_API_KEY"),
        os.environ.get("UNIPILE_API_KEY"),
        os.environ.get("UNIPILE_BASE_URL"),
        os.environ.get("UNIPILE_WEBHOOK_SECRET"),
        os.environ.get("UNIPILE_HOSTED_AUTH_DOMAIN"),
        os.environ.get("HARVEST_ENRICHMENT_TOP_N"),
        os.environ.get("HARVEST_ENRICHMENT_CONCURRENCY"),
        os.environ.get("DISCOVERY_PAGE_SIZE"),
        os.environ.get("DISCOVERY_MAX_PAGES"),
        os.environ.get("OUTREACH_DAILY_INVITES"),
        os.environ.get("OUTREACH_DAILY_MESSAGES"),
        os.environ.get("OUTREACH_DAILY_EMAILS"),
        os.environ.get("GOOGLE_CLIENT_ID"),
        os.environ.get("ALLOWED_EMAIL_DOMAIN"),
        os.environ.get("SUPER_ADMIN_EMAIL"),
        os.environ.get("SESSION_SECRET_KEY"),
        os.environ.get("SESSION_MAX_AGE_SECONDS"),
        os.environ.get("SESSION_COOKIE_SECURE"),
    )
    if _settings is None or _settings_env_signature != env_signature:
        _settings = Settings.from_environment()
        _settings_env_signature = env_signature
    return _settings


def get_openai_api_key() -> Optional[str]:
    """Return the configured OpenAI API key from the environment or .env file."""
    return get_settings().openai_api_key


def get_crustdata_api_key() -> Optional[str]:
    """Return the configured CrustData API key from the environment or .env file."""
    return get_settings().crustdata_api_key


def get_harvest_api_key() -> Optional[str]:
    """Return the configured HarvestAPI (harvestapi.io) API key from the environment or .env file."""
    return get_settings().harvest_api_key


def get_unipile_api_key() -> Optional[str]:
    """Server-side Unipile app Account API Key (outreach/messaging). Set only on the
    server (UNIPILE_API_KEY in /etc/recruiterai.env), never the MCP test key."""
    return get_settings().unipile_api_key


def get_unipile_base_url() -> str:
    """Unipile API base URL. Configurable via UNIPILE_BASE_URL; defaults to https://api.unipile.com."""
    return get_settings().unipile_base_url


def get_unipile_webhook_secret() -> Optional[str]:
    """Shared secret used to verify inbound Unipile webhooks (UNIPILE_WEBHOOK_SECRET)."""
    return get_settings().unipile_webhook_secret


def get_unipile_hosted_auth_domain() -> Optional[str]:
    """White-label Hosted Auth hostname (UNIPILE_HOSTED_AUTH_DOMAIN) so the connect
    page is served on our own domain and recruiters never see the vendor."""
    return get_settings().unipile_hosted_auth_domain


def get_harvest_enrichment_top_n() -> int:
    """How many top-baseline-ranked candidates to enrich via Harvest per search. Configurable via
    HARVEST_ENRICHMENT_TOP_N; defaults to 25 so every candidate shown in the workspace is read in depth."""
    return get_settings().harvest_enrichment_top_n


def get_harvest_enrichment_concurrency() -> int:
    """Max number of Harvest requests allowed in flight at once for a single search's
    enrichment step. Configurable via HARVEST_ENRICHMENT_CONCURRENCY; defaults to 3."""
    return get_settings().harvest_enrichment_concurrency


def get_discovery_page_size() -> int:
    """CrustData /person/search page size — backend-owned (the frontend never sets this).
    Configurable via DISCOVERY_PAGE_SIZE; defaults to 50."""
    return get_settings().discovery_page_size


def get_discovery_max_pages() -> int:
    """Max CrustData pages fetched per query. Configurable via DISCOVERY_MAX_PAGES; defaults to 1."""
    return get_settings().discovery_max_pages


def get_outreach_daily_limits() -> dict[str, int]:
    """Per-recruiter rolling-24h outreach caps, keyed by action category. Keeps
    sending under the thresholds that get LinkedIn/email accounts restricted.
    Override via OUTREACH_DAILY_INVITES / _MESSAGES / _EMAILS."""
    settings = get_settings()
    return {
        "linkedin_invite": settings.outreach_daily_invites,
        "linkedin_message": settings.outreach_daily_messages,
        "email": settings.outreach_daily_emails,
    }


def get_google_client_id() -> Optional[str]:
    """Return the configured Google OAuth Client ID from the environment or .env file."""
    return get_settings().google_client_id


def get_super_admin_email() -> Optional[str]:
    """The single email granted admin-only views (the live credit meter). Everyone
    else is an ordinary recruiter and never sees admin surfaces. Configurable via
    SUPER_ADMIN_EMAIL."""
    return get_settings().super_admin_email


def get_allowed_email_domain() -> Optional[str]:
    """Return the email domain allowed to log in from the environment or .env file."""
    return get_settings().allowed_email_domain


def get_session_secret_key() -> Optional[str]:
    """Return the secret key used to sign session cookies."""
    return get_settings().session_secret_key


def get_session_max_age_seconds() -> int:
    """Return the session cookie lifetime in seconds."""
    return get_settings().session_max_age_seconds


def get_session_cookie_secure() -> bool:
    """Return whether the session cookie requires HTTPS."""
    return get_settings().session_cookie_secure
