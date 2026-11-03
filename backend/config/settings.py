from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Google Gemini Live API Authentication Key
    GEMINI_API_KEY: str = ""
    
    # Gemini Live model for live streaming routes (/ws/translate, /ws/translate-auto).
    GEMINI_MODEL: str = "gemini-3.5-live-translate-preview"

    # Engine behind /ws/translate-auto (used by the web app and CLI client):
    #   "simultaneous" - translates WHILE the person talks; voice starts ~3-4 s after they
    #                    start speaking (Gemini Live translate model). Default.
    #   "live"         - waits for the speaker to pause, then translates the whole sentence
    #                    (most accurate, slower to start).
    #   "chunked"      - old engine: one translate + one TTS request per ~3 s of speech
    #                    (slow, and exhausts the free-tier quota quickly).
    TRANSLATION_ENGINE: str = "simultaneous"
    SIMULTANEOUS_MODEL: str = "gemini-3.5-live-translate-preview"
    INTERPRETER_MODEL: str = "gemini-3.8-live"

    # Chunked engine models:
    #   TRANSLATE_MODEL  - speech-to-translation: detects Sinhala/Tamil/English, transcribes & translates
    #   TTS_MODEL        - speech synthesis for the translated text (24 kHz PCM / WAV)
    TRANSLATE_MODEL: str = "gemini-3.5-flash-lite"
    TTS_MODEL: str = "gemini-3.8-flash-lite-tts"
    
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
