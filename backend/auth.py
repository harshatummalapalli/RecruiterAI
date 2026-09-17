import logging
from typing import Any, Dict

from fastapi import HTTPException, Request
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from backend.config import (
    get_allowed_email_domain,
    get_google_client_id,
    get_session_max_age_seconds,
    get_session_secret_key,
)

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "recruiterai_session"
_SESSION_SALT = "recruiterai-session"


def verify_google_id_token(token: str) -> Dict[str, Any]:
    """Verify a Google ID token's signature, audience, and expiry. Returns the token claims."""
    client_id = get_google_client_id()
    if not client_id:
        logger.warning("Google sign-in is unavailable — GOOGLE_CLIENT_ID is not configured")
        raise HTTPException(status_code=503, detail="Sign-in is currently unavailable. Please contact your administrator.")

    try:
        return google_id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
    except ValueError:
        logger.warning("Rejected an invalid Google credential")
        raise HTTPException(status_code=401, detail="Invalid Google credential.")


def check_domain_allowed(claims: Dict[str, Any]) -> None:
    """Raise if the token's email isn't a verified address on the allowed domain."""
    allowed_domain = get_allowed_email_domain()
    if not allowed_domain:
        logger.warning("Sign-in is unavailable — ALLOWED_EMAIL_DOMAIN is not configured")
        raise HTTPException(status_code=503, detail="Sign-in is currently unavailable. Please contact your administrator.")

    email = claims.get("email")
    email_verified = claims.get("email_verified")
    if not email or not email_verified:
        raise HTTPException(status_code=403, detail="Your Google account's email is not verified.")

    email_domain = email.rsplit("@", 1)[-1].lower()
    if email_domain != allowed_domain.lower():
        raise HTTPException(status_code=403, detail=f"Only @{allowed_domain} accounts can sign in.")


def _serializer() -> URLSafeTimedSerializer:
    secret_key = get_session_secret_key()
    if not secret_key:
        logger.warning("Sessions are unavailable — SESSION_SECRET_KEY is not configured")
        raise HTTPException(status_code=503, detail="Sign-in is currently unavailable. Please contact your administrator.")
    return URLSafeTimedSerializer(secret_key, salt=_SESSION_SALT)


def create_session_cookie_value() -> str:
    """Create a signed, opaque session token. Carries no PII — access is shared after login."""
    return _serializer().dumps({"authenticated": True})


def verify_session_cookie(value: str) -> bool:
    """Return True if the given cookie value is a valid, unexpired session token."""
    try:
        _serializer().loads(value, max_age=get_session_max_age_seconds())
        return True
    except (BadSignature, SignatureExpired):
        return False


def require_session(request: Request) -> None:
    """FastAPI dependency gating an endpoint behind a valid session cookie."""
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie_value or not verify_session_cookie(cookie_value):
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
