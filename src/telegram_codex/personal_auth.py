from __future__ import annotations

import hashlib
import os
import secrets
import time
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from .config import ConfigurationError, validate_high_entropy_secret

_DEFAULT_SCOPE = "telegram:personal"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} is required for remote MCP authentication")
    return value


def _scopes_from_env() -> list[str]:
    raw = os.getenv("TELEGRAM_MCP_OAUTH_SCOPES", _DEFAULT_SCOPE)
    scopes = [item.strip() for item in raw.replace(",", " ").split() if item.strip()]
    if not scopes:
        raise ConfigurationError("TELEGRAM_MCP_OAUTH_SCOPES must contain at least one scope")
    return scopes


def _scope_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item for item in value.split() if item]
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return []


def _require_secure_url(
    value: str, name: str, *, allow_loopback_http: bool = False
) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a valid HTTPS URL") from exc
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    secure_scheme = scheme == "https" or (
        allow_loopback_http and scheme == "http" and hostname in _LOOPBACK_HOSTS
    )
    if (
        not secure_scheme
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port is not None
        and not 1 <= port <= 65535
    ):
        raise ConfigurationError(
            f"{name} must use HTTPS without credentials or a fragment; "
            "static mode permits HTTP only for a loopback host"
        )
    return value


def _require_https_url(value: str, name: str) -> str:
    return _require_secure_url(value, name)


def _require_mcp_resource_url(
    value: str, *, allow_loopback_http: bool = False
) -> str:
    value = _require_secure_url(
        value,
        "TELEGRAM_MCP_PUBLIC_URL",
        allow_loopback_http=allow_loopback_http,
    )
    parsed = urlsplit(value)
    if parsed.path != "/mcp" or parsed.query:
        raise ConfigurationError(
            "TELEGRAM_MCP_PUBLIC_URL must identify the exact /mcp endpoint "
            "without a query or trailing slash"
        )
    return value


class StaticTokenVerifier(TokenVerifier):
    """Private-development verifier.

    This mode protects `/mcp` with one high-entropy bearer token. It is useful
    for curl/MCP Inspector and private tunnel smoke tests, but it is not the
    ChatGPT production authentication path because there is no OAuth login or
    refresh-token flow for ChatGPT to perform.
    """

    def __init__(self, token: str, scopes: list[str]) -> None:
        token = validate_high_entropy_secret(token, "TELEGRAM_MCP_STATIC_TOKEN")
        self._digest = hashlib.sha256(token.encode("utf-8")).digest()
        self._scopes = list(scopes)

    async def verify_token(self, token: str) -> AccessToken | None:
        supplied = hashlib.sha256(token.encode("utf-8")).digest()
        if not secrets.compare_digest(self._digest, supplied):
            return None
        return AccessToken(
            token=token,
            client_id="telegram-personal-static",
            subject="personal-owner",
            scopes=self._scopes,
            claims={"iss": "telegram-personal-static"},
        )


class IntrospectionTokenVerifier(TokenVerifier):
    """RFC 7662 verifier for an external OAuth/OIDC authorization server."""

    def __init__(
        self,
        *,
        introspection_url: str,
        client_id: str,
        client_secret: str,
        issuer_url: str,
        resource_url: str,
        owner_subject: str,
        timeout_seconds: float = 5.0,
    ) -> None:
        introspection_url = _require_https_url(
            introspection_url, "TELEGRAM_OAUTH_INTROSPECTION_URL"
        )
        issuer_url = _require_https_url(issuer_url, "TELEGRAM_OAUTH_ISSUER_URL")
        resource_url = _require_mcp_resource_url(resource_url)
        owner_subject = owner_subject.strip()
        if not owner_subject:
            raise ConfigurationError(
                "TELEGRAM_MCP_OWNER_SUBJECT is required for remote MCP authentication"
            )
        self._introspection_url = introspection_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._issuer_url = issuer_url.rstrip("/")
        self._resource_url = resource_url
        self._owner_subject = owner_subject
        self._timeout = timeout_seconds

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._introspection_url,
                    data={"token": token, "token_type_hint": "access_token"},
                    auth=(self._client_id, self._client_secret),
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError:
            return None

        if response.status_code != 200:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        if not isinstance(payload, dict) or payload.get("active") is not True:
            return None

        issuer = payload.get("iss")
        if not isinstance(issuer, str) or issuer.rstrip("/") != self._issuer_url:
            return None

        audience = payload.get("aud")
        if isinstance(audience, str):
            audiences: Collection[Any] = (audience,)
        elif isinstance(audience, Collection) and not isinstance(
            audience, (bytes, bytearray, Mapping)
        ):
            audiences = audience
        else:
            return None
        if self._resource_url not in audiences:
            return None

        subject = payload.get("sub")
        if not isinstance(subject, str) or subject != self._owner_subject:
            return None

        expires_at: int | None = None
        if payload.get("exp") is not None:
            try:
                expires_at = int(payload["exp"])
            except (TypeError, ValueError, OverflowError):
                return None
            if expires_at <= int(time.time()):
                return None

        client_id = str(payload.get("client_id") or "oauth-client")
        scopes = _scope_list(payload.get("scope", payload.get("scopes", [])))

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=expires_at,
            resource=self._resource_url,
            subject=subject,
            claims={"iss": issuer},
        )


@dataclass(frozen=True, slots=True)
class PersonalAuthBundle:
    mode: str
    verifier: TokenVerifier
    settings: AuthSettings


def load_personal_auth_from_env() -> PersonalAuthBundle:
    """Build fail-closed auth for the remote Personal MCP endpoint.

    `oauth` is the production/ChatGPT mode. `static` exists only for trusted
    private smoke tests. There is deliberately no unauthenticated remote mode.
    """

    mode = os.getenv("TELEGRAM_MCP_AUTH_MODE", "oauth").strip().lower()
    resource_url = _required("TELEGRAM_MCP_PUBLIC_URL")
    scopes = _scopes_from_env()

    if mode == "oauth":
        resource_url = _require_mcp_resource_url(resource_url)
        issuer_url = _require_https_url(
            _required("TELEGRAM_OAUTH_ISSUER_URL"), "TELEGRAM_OAUTH_ISSUER_URL"
        )
        verifier: TokenVerifier = IntrospectionTokenVerifier(
            introspection_url=_require_https_url(
                _required("TELEGRAM_OAUTH_INTROSPECTION_URL"),
                "TELEGRAM_OAUTH_INTROSPECTION_URL",
            ),
            client_id=_required("TELEGRAM_OAUTH_INTROSPECTION_CLIENT_ID"),
            client_secret=_required("TELEGRAM_OAUTH_INTROSPECTION_CLIENT_SECRET"),
            issuer_url=issuer_url,
            resource_url=resource_url,
            owner_subject=_required("TELEGRAM_MCP_OWNER_SUBJECT"),
        )
    elif mode == "static":
        resource_url = _require_mcp_resource_url(
            resource_url,
            allow_loopback_http=True,
        )
        issuer_url = _require_secure_url(
            os.getenv("TELEGRAM_MCP_STATIC_ISSUER_URL", "https://auth.invalid").strip(),
            "TELEGRAM_MCP_STATIC_ISSUER_URL",
            allow_loopback_http=True,
        )
        static_token = validate_high_entropy_secret(
            _required("TELEGRAM_MCP_STATIC_TOKEN"), "TELEGRAM_MCP_STATIC_TOKEN"
        )
        connect_token = os.getenv("TELEGRAM_CONNECT_TOKEN", "").strip()
        if connect_token:
            connect_token = validate_high_entropy_secret(
                connect_token, "TELEGRAM_CONNECT_TOKEN"
            )
            static_digest = hashlib.sha256(static_token.encode("utf-8")).digest()
            connect_digest = hashlib.sha256(connect_token.encode("utf-8")).digest()
            if secrets.compare_digest(static_digest, connect_digest):
                raise ConfigurationError(
                    "TELEGRAM_MCP_STATIC_TOKEN and TELEGRAM_CONNECT_TOKEN must be different secrets"
                )
        verifier = StaticTokenVerifier(static_token, scopes)
    else:
        raise ConfigurationError(
            "TELEGRAM_MCP_AUTH_MODE must be 'oauth' or 'static'; remote unauthenticated mode is disabled"
        )

    settings = AuthSettings(
        issuer_url=AnyHttpUrl(issuer_url),
        resource_server_url=AnyHttpUrl(resource_url),
        required_scopes=scopes,
    )
    return PersonalAuthBundle(mode=mode, verifier=verifier, settings=settings)
