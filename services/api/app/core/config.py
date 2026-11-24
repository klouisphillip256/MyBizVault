import os
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./mybizvault.db"
    frontend_origin: str = "http://127.0.0.1:5173"
    cookie_secure: bool = False
    development_verification: bool = False
    storage_backend: Literal["local", "s3", "database"] = "local"
    storage_local_path: str = "./vault_objects"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    sms_webhook_url: str | None = None
    sms_webhook_token: str | None = None
    brevo_api_key: str | None = None
    brevo_sender_email: str | None = None
    brevo_sender_name: str = "MyBizVault"
    at_api_key: str | None = None
    at_username: str = "sandbox"
    at_sandbox: bool = True
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_graph_version: str = "v24.0"
    whatsapp_test_mode: bool = True
    brevo_webhook_token: str | None = None
    at_webhook_token: str | None = None
    ussd_callback_token: str | None = None
    meta_app_secret: str | None = None
    meta_verify_token: str | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

if os.getenv("VERCEL") and (settings.database_url.startswith("sqlite") or settings.storage_backend == "local"):
    raise RuntimeError("Vercel requires PostgreSQL DATABASE_URL and non-local STORAGE_BACKEND")


def sqlalchemy_database_url(url: str) -> str:
    """Use the installed psycopg v3 driver for provider PostgreSQL URLs."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url
