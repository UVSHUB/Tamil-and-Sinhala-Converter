import logging
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.config.settings import settings
from backend.websocket.connection_manager import manager
from backend.websocket.stream_handler import handle_translation_stream

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger("backend")

app = FastAPI(
    title="Sinhala ↔ Tamil Real-Time Voice Translator",
    description="FastAPI WebSocket Gateway interfacing with Google Gemini Live API",
    version="1.0.0",
)

origins = settings.ALLOWED_ORIGINS.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "voice-translator-backend",
        "gemini_live_configured": bool(settings.GEMINI_API_KEY)
    }


@app.websocket("/ws/translate")
async def websocket_translator_endpoint(
    websocket: WebSocket,
    source: str = "Sinhala",
    target: str = "Tamil"
):
    await manager.connect(websocket)
    logger.info(f"Client connected: {websocket.client} (translating {source} -> {target})")

    try:
        await handle_translation_stream(websocket, source, target)

    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {websocket.client}")

    except Exception as e:
        logger.error(f"WebSocket gateway error: {str(e)}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except RuntimeError:
            pass

    finally:
        manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=True
    )