import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.config.settings import settings
from backend.websocket.connection_manager import manager
from backend.websocket.stream_handler import handle_translation_stream

# Setup structured logger
logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger("backend")

app = FastAPI(
    title="Sinhala ↔ Tamil Real-Time Voice Translator",
    description="FastAPI WebSocket Gateway interfacing with Google Gemini Live API",
    version="1.0.0",
)

# CORS configuration
origins = settings.ALLOWED_ORIGINS.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------------
# REST Routes
# ------------------------------------------------------------------------------
@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    """Health check endpoint for Docker container checks and ingress routers."""
    return {
        "status": "healthy",
        "service": "voice-translator-backend",
        "gemini_live_configured": bool(settings.GEMINI_API_KEY)
    }

# ------------------------------------------------------------------------------
# WebSocket Gateway Routes
# ------------------------------------------------------------------------------
@app.websocket("/ws/translate")
async def websocket_translator_endpoint(websocket: WebSocket):
    """
    Main real-time voice streaming entrypoint.
    Receives Client float32 PCM frames, downsizes/converts, forwards to Gemini API,
    and returns synthesized audio translation and transcriptions back to Client.
    """
    await manager.connect(websocket)
    logger.info(f"Client connection established: {websocket.client}")
    
    try:
        await handle_translation_stream(websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"Client connection disconnected: {websocket.client}")
    except Exception as e:
        logger.error(f"Error in translation WebSocket loop: {str(e)}")
        manager.disconnect(websocket)
        await websocket.close(code=1011, reason="Internal server error")
