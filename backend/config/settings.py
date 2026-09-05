from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Google Gemini Live API Authentication Key
    GEMINI_API_KEY: str = ""
    
    # Gemini Live model for real-time audio translation.
    # Use a live model instead of a general text model, or Gemini may choose unrelated output languages.
    GEMINI_MODEL: str = "gemini-2.0-flash-live-001"
    
    # Backend Server Configurations
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000
    
    # Backend local logger configurations
    LOG_LEVEL: str = "INFO"
    
    # CORS Configuration
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:80,http://127.0.0.1:8000"

    class Config:
        # Load env parameters from root directory
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
