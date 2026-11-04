from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PRECIM_", extra="ignore")

    database_url: str = "sqlite:///./data/precim.db"
    telegram_token: str = ""
    telegram_chat_id: str = ""
    scan_cycle_minutes: str = "60"  # minutos entre varreduras do Buscapé/Zoom (aceita ciclo: "30,50,60")
    amazon_enabled: bool = True  # coleta direta da Amazon por navegador automatizado
    chromium_path: str = ""  # opcional: caminho de um Chromium já instalado
    user_agent: str = "precim/0.1 (uso pessoal)"


settings = Settings()
