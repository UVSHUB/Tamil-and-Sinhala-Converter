import logging
import uvicorn
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.config.settings import settings
from backend.websocket.connection_manager import manager
from backend.websocket.stream_handler import handle_translation_stream
from backend.websocket.auto_stream_handler import handle_auto_translation_stream

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

# Serve React Frontend
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")

if os.path.exists(frontend_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_path, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Ignore API and WS routes
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            return {"error": "Not Found"}
        
        # Serve specific requested files if they exist in dist
        file_path = os.path.join(frontend_path, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
            
        # Fallback to index.html for React Router SPA
        return FileResponse(os.path.join(frontend_path, "index.html"))
else:
    logger.warning("Frontend dist folder not found. Only API and WebSocket routes are active.")


@app.websocket("/ws/translate")
async def websocket_translator_endpoint(
    websocket: WebSocket,
    source: str = "Sinhala",
    target: str = "Tamil",
    voice: str = "Aoede",
    room: str = "default"
):
    connected = await manager.connect(websocket, room)
    if not connected:
        return
    logger.info(f"Client connected: {websocket.client} (room={room}, translating {source} -> {target} with initial voice: {voice})")

    try:
        await handle_translation_stream(websocket, source, target, voice)

    except WebSocketDisconnect:
        logger.info(f"Client disconnected: {websocket.client}")

    except Exception as e:
        logger.error(f"WebSocket gateway error: {str(e)}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except RuntimeError:
            pass

    finally:
        manager.disconnect(websocket, room)


@app.websocket("/ws/translate-auto")
async def websocket_auto_translator_endpoint(
    websocket: WebSocket,
    voice: str = "Aoede",
    room: str = "default"
):
    """
    Bidirectional auto-detect endpoint: no source/target language params needed.
    Automatically detects whether the user is speaking Sinhala or Tamil and
    translates to the other language in real time.
    """
    connected = await manager.connect(websocket, room)
    if not connected:
        return
    logger.info(f"Client connected (auto mode): {websocket.client}, room={room}, voice={voice}")

    try:
        await handle_auto_translation_stream(websocket, voice, room)

    except WebSocketDisconnect:
        logger.info(f"Client disconnected (auto mode): {websocket.client}")

    except Exception as e:
        logger.error(f"WebSocket auto gateway error: {str(e)}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except RuntimeError:
            pass

    finally:
        manager.disconnect(websocket, room)


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=True
    )