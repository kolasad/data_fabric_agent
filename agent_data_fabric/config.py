"""Runtime configuration.

Settings are read from environment variables (prefixed ``AGENT_FABRIC_``) or an
optional ``.env`` file. Credentials are **never** written to the semantic model;
see :func:`redact_dsn`.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Connection and safety configuration."""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_FABRIC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    dsn: str | None = None
    include_schemas: Annotated[list[str], NoDecode] = Field(default_factory=list)
    exclude_schemas: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["pg_catalog", "information_schema"]
    )
    default_sample_limit: int = Field(default=10, ge=1)
    max_sample_limit: int = Field(default=100, ge=1)
    query_timeout_seconds: int = Field(default=15, ge=1)

    @field_validator("include_schemas", "exclude_schemas", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow comma-separated env values (e.g. ``public,sales``)."""

        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


def redact_dsn(dsn: str) -> str:
    """Return ``dsn`` with any password removed, safe for logging/serialization."""

    try:
        parts = urlsplit(dsn)
    except ValueError:
        return "<redacted>"

    if parts.hostname is None:
        # Not a URL-style DSN; drop it entirely to avoid leaking secrets.
        return "<redacted>"

    userinfo = ""
    if parts.username:
        userinfo = parts.username
        if parts.password:
            userinfo += ":***"
        userinfo += "@"

    host = parts.hostname or ""
    if parts.port:
        host += f":{parts.port}"

    netloc = f"{userinfo}{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
