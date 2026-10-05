from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Google Gemini Live API Authentication Key
    GEMINI_API_KEY: str = ""
    
    # Gemini Live model for live streaming routes (/ws/translate, /ws/translate-auto).
    GEMINI_MODEL: str = "gemini-3.5-live-translate-preview"

    # Continuous engine models:
    #   TRANSLATE_MODEL  - speech-to-translation: detects Sinhala/Tamil/English, transcribes & translates
    #   TTS_MODEL        - speech synthesis for the translated text (24 kHz PCM / WAV)
    TRANSLATE_MODEL: str = "gemini-3.1-flash-lite-preview"
    TTS_MODEL: str = "gemini-3.8-flash-tts"
    
    # Backend Server Configurations
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000
    
    # Backend local logger configurations
    LOG_LEVEL: str = "INFO"
    
    # CORS Configuration
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:80,http://127.0.0.1:8000,http://localhost:5180"

    class Config:
        # Load env parameters from root directory
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
