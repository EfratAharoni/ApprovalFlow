from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "approval-service"
    database_url: str = "postgresql+asyncpg://approvalflow:approvalflow_dev@localhost:5432/approvalflow"
    dapr_http_port: int = 3503
    dapr_grpc_port: int = 50003
    log_level: str = "INFO"
    pubsub_name: str = "pubsub"
    decision_made_topic: str = "decision.made"
    approval_decided_topic: str = "approval.decided"
    statestore_name: str = "statestore"
    hitl_timeout_hours: int = 48
    timeout_check_interval_seconds: int = 600  # 10 minutes

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
