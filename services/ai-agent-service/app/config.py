from decimal import Decimal
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "ai-agent-service"
    database_url: str = "postgresql+asyncpg://approvalflow:approvalflow_dev@localhost:5432/approvalflow"
    dapr_http_port: int = 3502
    log_level: str = "INFO"

    pubsub_name: str = "pubsub"
    submission_created_topic: str = "submission.created"
    decision_made_topic: str = "decision.made"
    statestore_name: str = "statestore"

    # LLM — swappable by env only (M15)
    llm_model: str = "gemini/gemini-1.5-flash"
    llm_api_key: str = ""
    llm_mock: bool = False          # set True in tests / CI to skip real API calls
    llm_max_iterations: int = 5     # max agent tool-calling iterations

    # Autonomy thresholds (overridden by Dapr config store in prod; M13)
    autonomy_ceiling: Decimal = Decimal("250")
    autonomy_confidence: float = 0.80
    fx_hard_stop: Decimal = Decimal("1000")
    receipt_threshold: Decimal = Decimal("25")
    saas_cap: Decimal = Decimal("200")
    hw_cap: Decimal = Decimal("1000")
    meal_per_attendee: Decimal = Decimal("75")
    client_entertain_cap: Decimal = Decimal("500")
    travel_manager_cap: Decimal = Decimal("1500")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
