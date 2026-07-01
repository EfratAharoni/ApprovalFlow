from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    jwt_secret_key: str = Field(default="dev-secret-key-change-in-production", alias="JWT_SECRET_KEY")
    jwt_expire_hours: int = Field(default=24, alias="JWT_EXPIRE_HOURS")
    # Format: "user1:pass1:role1,user2:pass2:role2"
    users_raw: str = Field(
        default="dana:pass123:submitter,lena:pass123:approver,admin:admin123:admin",
        alias="USERS",
    )

    @property
    def users(self) -> dict:
        result = {}
        for entry in self.users_raw.split(","):
            parts = entry.strip().split(":")
            if len(parts) == 3:
                username, password, role = parts
                result[username] = {"password": password, "role": role}
        return result

    model_config = {"populate_by_name": True, "env_file": ".env"}


settings = Settings()
