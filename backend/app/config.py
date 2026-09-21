"""Centralized, secret-file aware MariaDB configuration."""
from __future__ import annotations

import os
import secrets
import warnings
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def _file_or_value(name: str) -> str | None:
    file_name = os.getenv(f"{name}_FILE")
    if file_name:
        try:
            return Path(file_name).read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise RuntimeError(f"Cannot read {name}_FILE") from exc
    return os.getenv(name)


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str | URL
    secret: str
    pool_size: int
    max_overflow: int
    pool_recycle: int
    pool_pre_ping: bool
    database_ssl_ca: str | None


def _require_mariadb(url: str | URL) -> str | URL:
    if make_url(url).get_backend_name() != "mariadb":
        raise RuntimeError("Only MariaDB is supported")
    return url


def load_settings() -> Settings:
    environment = os.getenv("WHO_COULD_ENV", "production").lower()
    secret = _file_or_value("WHO_COULD_SECRET")
    if not secret and environment == "development":
        warnings.warn("Using a random process-only development secret", RuntimeWarning)
        secret = secrets.token_urlsafe(48)
    if not secret or len(secret) < 32:
        raise RuntimeError("WHO_COULD_SECRET must contain at least 32 characters")

    explicit = os.getenv("DATABASE_URL")
    engine = os.getenv("DATABASE_ENGINE", "mariadb").lower()
    if engine != "mariadb":
        raise RuntimeError("Only MariaDB is supported")

    if explicit:
        url: str | URL = explicit if environment == "test" and make_url(explicit).get_backend_name() == "sqlite" else _require_mariadb(explicit)
    else:
        password = _file_or_value("DATABASE_PASSWORD")
        if not password:
            raise RuntimeError("DATABASE_PASSWORD or DATABASE_PASSWORD_FILE is required for MariaDB")
        url = URL.create(
            "mariadb+pymysql",
            username=os.getenv("DATABASE_USER", "who_could"),
            password=password,
            host=os.getenv("DATABASE_HOST", "localhost"),
            port=int(os.getenv("DATABASE_PORT", "3306")),
            database=os.getenv("DATABASE_NAME", "who_could"),
        )

    return Settings(
        environment,
        url,
        secret,
        int(os.getenv("DATABASE_POOL_SIZE", "5")),
        int(os.getenv("DATABASE_MAX_OVERFLOW", "5")),
        int(os.getenv("DATABASE_POOL_RECYCLE", "1800")),
        _boolean("DATABASE_POOL_PRE_PING", True),
        os.getenv("DATABASE_SSL_CA"),
    )


settings = load_settings()
