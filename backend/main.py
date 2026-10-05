import logging
import uvicorn
import os
import sqlite3
import secrets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Security, HTTPException, status, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from backend.config.settings import settings
from backend.websocket.connection_manager import manager
from backend.websocket.stream_handler import handle_translation_stream
from backend.websocket.auto_stream_handler import handle_auto_translation_stream
from backend.websocket.continuous_stream_handler import handle_continuous_translation_stream

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger("backend")

app = FastAPI(
    title="Sinhala <-> Tamil Real-Time Voice Translator",
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

# --- SECURITY DATABASE CHECK LOGIC ---
DB_FILE = 'api_keys.db'
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT UNIQUE,
            is_active INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

def is_key_valid(api_key: str | None = None) -> bool:
    # If server has GEMINI_API_KEY configured in environment, allow connections
    if settings.GEMINI_API_KEY:
        return True
    if not api_key:
        return False
    if api_key.startswith("AIza"):
        return True
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT is_active FROM users WHERE api_key = ?", (api_key,))
        result = c.fetchone()
        conn.close()
        return bool(result and result[0] == 1)
    except Exception:
        return False
# ---------------------------------------

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing Database...")
    init_db()

@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "voice-translator-backend",
        "gemini_live_configured": bool(settings.GEMINI_API_KEY)
    }

# --- NEW: API KEY GENERATION ENDPOINT ---
@app.post("/api/generate-key", tags=["Security"])
async def generate_api_key():
    # Generate a secure, 32-character random string
    new_key = "sk_" + secrets.token_hex(16)
    
    # Connect to the existing SQLite database and save the key
    # Setting is_active to 1 so the key is immediately usable
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO users (api_key, is_active) VALUES (?, 1)", (new_key,))
    conn.commit()
    conn.close()
    
    return {"api_key": new_key}
# ----------------------------------------

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
    room: str = "default",
    api_key: str | None = Query(None)  # Security & Custom Gemini key parameter
):
    # Security check blocks access if key is invalid
    if not is_key_valid(api_key):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    connected = await manager.connect(websocket, room)
    if not connected:
        return
    logger.info(f"Client connected: {websocket.client} (room={room}, translating {source} -> {target} with initial voice: {voice})")

    try:
        await handle_translation_stream(websocket, source, target, voice, api_key)
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


@app.websocket("/ws/translate-continuous")
@app.websocket("/ws/translate-stream")
@app.websocket("/ws/translate-auto")
async def websocket_auto_translator_endpoint(
    websocket: WebSocket,
    target: str = "Tamil",
    voice: str = "Aoede",
    room: str = "default",
    api_key: str | None = Query(None)  # Security & Custom Gemini key parameter
):
    """
    Continuous real-time translation endpoint:
    - Automatically detects input language (Sinhala / Tamil / English).
    - Translates into selected target language (Tamil or Sinhala).
    - Listens in the background non-stop and outputs audio every ~4.5 - 5 seconds.
    """
    # Security check blocks access if key is invalid
    if not is_key_valid(api_key):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    connected = await manager.connect(websocket, room)
    if not connected:
        return
    logger.info(f"Client connected (continuous mode): {websocket.client}, room={room}, target={target}, voice={voice}")

    try:
        await handle_continuous_translation_stream(websocket, target, voice, room, api_key)

    except WebSocketDisconnect:
        logger.info(f"Client disconnected (continuous mode): {websocket.client}")
    except Exception as e:
        logger.error(f"WebSocket continuous gateway error: {str(e)}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except RuntimeError:
            pass
            
    finally:
        manager.disconnect(websocket, room)


@app.websocket("/ws/translate-live")
async def websocket_live_interpreter_endpoint(
    websocket: WebSocket,
    voice: str = "Aoede",
    room: str = "default",
    api_key: str | None = None
):
    """Legacy single-session live interpreter bridge."""
    connected = await manager.connect(websocket, room)
    if not connected:
        return
    logger.info(f"Client connected (live mode): {websocket.client}, room={room}, voice={voice}")
    try:
        await handle_auto_translation_stream(websocket, voice, room, api_key)
    except WebSocketDisconnect:
        logger.info(f"Client disconnected (live mode): {websocket.client}")
    except Exception as e:
        logger.error(f"WebSocket live gateway error: {str(e)}")
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