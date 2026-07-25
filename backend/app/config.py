from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file = ".env", env_prefix = "RC_")

    app_name: str = "RaverCircuit API"

    home_lat: float = 34.05
    home_lon: float = -118.24
    annual_budget: float = 3000.0
    production_taste: float = 0.5

    # travel heuristic
    drive_km_threshold: float = 400.0
    drive_cost_flat: float = 60.0
    fly_cost_flat: float = 350.0

    # scoring weights — must sum to 1.0
    w_lineup_value: float = 0.35
    w_cost_efficiency: float = 0.20
    w_chain_bonus: float = 0.10
    w_crew: float = 0.15
    w_production_fit: float = 0.10
    w_weather_comfort: float = 0.10

    dynamodb_endpoint: str | None = None

    @model_validator(mode = "after")
    def _weights_sum_to_one(self):
        total = (self.w_lineup_value + self.w_cost_efficiency + self.w_chain_bonus + self.w_crew + self.w_production_fit + self.w_weather_comfort)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring weights must sum to 1.0, got {total}")
        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()