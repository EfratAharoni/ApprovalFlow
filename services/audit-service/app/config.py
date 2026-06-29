from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "audit-service"
    database_url: str = "postgresql+asyncpg://approvalflow:approvalflow_dev@localhost:5432/approvalflow"
    dapr_http_port: int = 3505
    dapr_grpc_port: int = 50005
    log_level: str = "INFO"
    pubsub_name: str = "pubsub"
    autonomy_ceiling: float = 250.0

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
