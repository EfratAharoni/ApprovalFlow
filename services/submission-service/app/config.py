from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "submission-service"
    database_url: str = "postgresql+asyncpg://approvalflow:approvalflow_dev@localhost:5432/approvalflow"
    dapr_http_port: int = 3501
    dapr_grpc_port: int = 50001
    log_level: str = "INFO"
    pubsub_name: str = "pubsub"
    submission_created_topic: str = "submission.created"
    decision_made_topic: str = "decision.made"
    approval_decided_topic: str = "approval.decided"
    payment_completed_topic: str = "payment.completed"
    payment_failed_topic: str = "payment.failed"
    statestore_name: str = "statestore"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
