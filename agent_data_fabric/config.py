"""Runtime configuration.

Settings resolve, highest priority first: CLI flags (passed as init kwargs) ->
environment variables (prefixed ``AGENT_FABRIC_``) -> an optional ``.env`` file ->
an optional ``fabric.config.yaml`` file -> field defaults. Credentials are
**never** written to the semantic model; see :func:`redact_dsn`.
"""

from __future__ import annotations

import contextvars
import os
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

DEFAULT_CONFIG_FILENAME = "fabric.config.yaml"
CONFIG_FILE_ENV_VAR = "AGENT_FABRIC_CONFIG"

# Threaded from Settings.__init__ to settings_customise_sources (a classmethod
# pydantic-settings invokes internally, with no way to pass extra arguments
# through it directly).
_config_file_ctx: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "_agent_fabric_config_file", default=None
)


def resolve_config_path(explicit: str | Path | None = None) -> Path | None:
    """Resolve the config file to load, or ``None`` if none applies.

    An explicit path (from ``--config`` or ``AGENT_FABRIC_CONFIG``) must exist.
    The implicit default (``./fabric.config.yaml``) is silently skipped when
    absent, so projects that don't use a config file are unaffected.
    """

    if explicit is not None:
        path = Path(explicit)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        return path

    env_value = os.environ.get(CONFIG_FILE_ENV_VAR)
    if env_value:
        path = Path(env_value)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found ({CONFIG_FILE_ENV_VAR}): {path}")
        return path

    default = Path(DEFAULT_CONFIG_FILENAME)
    return default if default.exists() else None


class Settings(BaseSettings):
    """Connection and safety configuration."""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_FABRIC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def __init__(self, *, _config_file: str | Path | None = None, **values: Any) -> None:
        token = _config_file_ctx.set(resolve_config_path(_config_file))
        try:
            super().__init__(**values)
        finally:
            _config_file_ctx.reset(token)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings, dotenv_settings]

        config_path = _config_file_ctx.get()
        if config_path is not None:
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=config_path))

        sources.append(file_secret_settings)
        return tuple(sources)

    dsn: str | None = None
    include_schemas: Annotated[list[str], NoDecode] = Field(default_factory=list)
    exclude_schemas: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["pg_catalog", "information_schema"]
    )
    default_sample_limit: int = Field(default=10, ge=1)
    max_sample_limit: int = Field(default=100, ge=1)
    query_timeout_seconds: int = Field(default=15, ge=1)

    # MongoDB discovery.
    mongo_sample_size: int = Field(default=100, ge=1)
    include_collections: Annotated[list[str], NoDecode] = Field(default_factory=list)
    exclude_collections: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator(
        "include_schemas",
        "exclude_schemas",
        "include_collections",
        "exclude_collections",
        mode="before",
    )
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
