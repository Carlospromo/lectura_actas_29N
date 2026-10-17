from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://actas:actas_local@localhost:5432/actas"
    s3_endpoint: str = "http://localhost:9000"
    s3_public_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "actas-private"
    s3_access_key: str = "localdev"
    s3_secret_key: str = "localdevsecret"
    session_secret: str = "change-this-for-local-development"
    max_image_bytes: int = 10 * 1024 * 1024

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
if settings.app_env == "production":
    raise RuntimeError("Production auth and storage providers are not configured; refusing to start")
