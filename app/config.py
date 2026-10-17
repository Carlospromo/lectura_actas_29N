from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://actas:actas_local@localhost:5432/actas"
    storage_endpoint: str = "http://localhost:9000"
    storage_public_endpoint: str = "http://localhost:9000"
    app_public_origin: str = "http://localhost:8001"
    storage_secret: str = "change-this-storage-secret-for-local-development"
    storage_root: str = "/data"
    session_secret: str = "change-this-for-local-development"
    max_image_bytes: int = 10 * 1024 * 1024

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
if settings.app_env == "production":
    raise RuntimeError("Production auth and storage providers are not configured; refusing to start")
