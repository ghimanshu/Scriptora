from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Article Publishing API"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+psycopg://publishing_dev:replace-local-password@127.0.0.1:5432/publishing"
    )
    migration_database_url: str | None = None
    test_database_url: str | None = None
    jwt_signing_key: str = Field(min_length=32)
    outbox_encryption_key: str | None = None
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "publishing-backend"
    jwt_audience: str = "publishing-frontend"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_ttl_days: int = Field(default=7, ge=1, le=30)
    public_app_url: str = "http://localhost:3000"
    default_review_duration_hours: int = Field(default=120, gt=0)
    default_publication_fee_minor: int = Field(default=250000, gt=0)
    default_currency: Literal["INR"] = "INR"
    default_max_live_assignments: int = Field(default=5, gt=0)
    expiry_scan_interval_seconds: int = 60
    reminder_before_deadline_hours: int = 24
    outbox_max_attempts: int = 8
    worker_poll_interval_seconds: int = 5
    storage_driver: Literal["local", "s3"] = "local"
    local_storage_root: Path = Path("var/private-files")
    manuscript_max_bytes: int = 20971520
    payment_proof_max_bytes: int = 10485760
    scanner_driver: Literal["clamav", "bypass"] = "clamav"
    scanner_host: str = "127.0.0.1"
    scanner_port: int = 3310
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False
    mail_from: str = "publishing@example.test"
    object_storage_endpoint: str | None = None
    object_storage_bucket: str | None = None
    object_storage_region: str | None = None

    @model_validator(mode="after")
    def safe(self):
        if "REPLACE" in self.jwt_signing_key.upper():
            raise ValueError("Replace the signing-key placeholder with a random secret")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("PostgreSQL with psycopg is required")
        if self.app_env == "production":
            if not self.outbox_encryption_key:
                raise ValueError("Production requires a separate Fernet OUTBOX_ENCRYPTION_KEY")
            if self.storage_driver != "s3" or self.scanner_driver != "clamav":
                raise ValueError("Production requires private S3 storage and ClamAV")
            if (
                not self.object_storage_bucket
                or not self.smtp_use_tls
                or not self.public_app_url.startswith("https://")
            ):
                raise ValueError("Production requires bucket, SMTP TLS and HTTPS public URL")
        if self.outbox_encryption_key:
            from cryptography.fernet import Fernet

            Fernet(self.outbox_encryption_key.encode())
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
