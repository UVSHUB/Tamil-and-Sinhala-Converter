from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Google Gemini Live API Authentication Key
    GEMINI_API_KEY: str = ""
    
    # Gemini AI model to target for real-time live content generation
    GEMINI_MODEL: str = "gemini-2.0-flash-exp"
    
    # Backend local logger configurations
    LOG_LEVEL: str = "INFO"
    
    # CORS Configuration
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:80"

    class Config:
        # Load env parameters from root directory
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
