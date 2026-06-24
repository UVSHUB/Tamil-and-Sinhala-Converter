import logging
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.config.settings import settings
from backend.websocket.connection_manager import manager
from backend.websocket.stream_handler import handle_voice_translation_stream

# Configuration of standard structure level platform-wide logging
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger("backend")

app = FastAPI(
    title="Sinhala ↔ Tamil Real-Time Voice Translator",
    description="FastAPI WebSocket Gateway interfacing with Google Gemini Live API",
    version="1.0.0",
)

# Apply runtime array generation splitting configuration string values
origins = settings.ALLOWED_ORIGINS.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------------
# REST Routing Layer
# ------------------------------------------------------------------------------
@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Docker container orchestration validation checks."""
    return {
        "status": "healthy",
        "service": "voice-translator-backend",
        "gemini_live_configured": bool(settings.GEMINI_API_KEY)
    }

# ------------------------------------------------------------------------------
# WebSocket Real-Time Gateway Routing Layer
# ------------------------------------------------------------------------------
@app.websocket("/ws/translate")
async def websocket_translator_endpoint(websocket: WebSocket):
    """
    Main real-time voice streaming entrypoint.
    Interfaces between Client browser sockets and Google Gemini Live API.
    """
    # 1. Register connection tracking
    await manager.connect(websocket)
    logger.info(f"🚀 Client connection pool registered: {websocket.client}")
    
    try:
        # 2. Hand off control loop directly into processing workers
        await handle_voice_translation_stream(websocket)
        
    except WebSocketDisconnect:
        logger.info(f"🔌 Client dropped stream connection context gracefully: {websocket.client}")
        
    except Exception as e:
        logger.error(f"🚨 Structural error inside translation WebSocket gateway loop: {str(e)}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except RuntimeError:
            pass # Connection dropped during exception runtime
            
    finally:
        # 3. ABSOLUTE LIFECYCLE GUARANTEE: Clear out client memory references unconditionally
        manager.disconnect(websocket)