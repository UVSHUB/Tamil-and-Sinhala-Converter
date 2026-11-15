import base64
import io
import logging
import uvicorn
import os
import sqlite3
import secrets
import wave
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Security, HTTPException, status, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from google import genai
from backend.config.settings import settings
from backend.websocket.connection_manager import manager
from backend.websocket.stream_handler import handle_translation_stream
from backend.websocket.auto_stream_handler import handle_auto_translation_stream
from backend.websocket.continuous_stream_handler import (
    create_genai_client,
    detect_audio_mime,
    handle_continuous_translation_stream,
    is_gemini_api_key,
    pcm_to_wav,
    synthesize_tts_audio,
    transcribe_and_translate_wav,
)
from backend.websocket.live_interpreter_handler import handle_live_interpreter_stream

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
    if is_gemini_api_key(api_key):
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


@app.post("/api/v1/translate-audio", tags=["Translation"])
async def translate_audio_endpoint(
    request: Request,
    target: str = Query("Tamil"),
    source: str = Query("Auto-Detect"),
    voice: str = Query("Aoede"),
    api_key: str | None = Query(None),
):
    """
    Translates an audio file (.mp3, .wav, .m4a, .ogg, .flac, .aac, .webm, or .pcm) via REST
    and returns both the transcribed/translated text and the synthesized voice output as base64 WAV.
    Accepts either:
      - JSON body: {"file_path": "/path/to/file.mp3", "target": "Tamil", "voice": "Aoede"}
      - JSON body: {"audio_base64": "...", "mime_type": "audio/mp3", "target": "Tamil"}
      - Raw binary audio bytes in the request body
    """
    final_api_key = api_key if is_gemini_api_key(api_key) else settings.GEMINI_API_KEY
    if not final_api_key:
        raise HTTPException(status_code=401, detail="GEMINI_API_KEY is not configured.")

    raw_bytes = b""
    filename = ""
    explicit_mime = ""
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        body = await request.json()
        target = body.get("target", target)
        source = body.get("source", source)
        voice = body.get("voice", voice)
        explicit_mime = body.get("mime_type", "")
        if body.get("file_path"):
            fpath = os.path.expanduser(str(body["file_path"]).strip().strip('"').strip("'"))
            if not os.path.isfile(fpath):
                raise HTTPException(status_code=404, detail=f"Audio file not found: {fpath}")
            filename = fpath
            with open(fpath, "rb") as f:
                raw_bytes = f.read()
        elif body.get("audio_base64"):
            raw_bytes = base64.b64decode(body["audio_base64"])
    else:
        raw_bytes = await request.body()
        if content_type.startswith("audio/"):
            explicit_mime = content_type.split(";")[0].strip()

    if not raw_bytes:
        raise HTTPException(status_code=400, detail="No audio data or file_path provided.")

    mime_type = explicit_mime or detect_audio_mime(raw_bytes, filename)
    ai_client = create_genai_client(final_api_key)
    res_data = await transcribe_and_translate_wav(
        ai_client, raw_bytes, target_lang=target, source_lang=source, mime_type=mime_type
    )
    if not res_data:
        raise HTTPException(status_code=502, detail="Failed to transcribe/translate audio.")

    transcription = (res_data.get("transcription") or "").strip()
    translation = (res_data.get("translation") or "").strip()
    detected_lang = res_data.get("detected_language") or source

    tts_pcm = await synthesize_tts_audio(ai_client, translation, voice_name=voice)
    wav_out_b64 = ""
    if tts_pcm:
        if tts_pcm[:4] == b"RIFF":
            wav_out_bytes = tts_pcm
        else:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(tts_pcm)
            wav_out_bytes = buf.getvalue()
        wav_out_b64 = base64.b64encode(wav_out_bytes).decode("ascii")

    return {
        "detected_language": detected_lang,
        "target_language": target,
        "transcription": transcription,
        "translation": translation,
        "audio_wav_base64": wav_out_b64,
        "sample_rate": 24000,
    }
# ----------------------------------------

# Serve React Frontend (if built and present)
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
assets_path = os.path.join(frontend_path, "assets")

if os.path.isdir(assets_path):
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

if os.path.isdir(frontend_path) and os.path.isfile(os.path.join(frontend_path, "index.html")):
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
    logger.info("Frontend dist folder not found or incomplete. API and WebSocket gateway active.")


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
    - Default engine (TRANSLATION_ENGINE=simultaneous): Gemini Live translate model that
      speaks the translation while the person is still talking (see live_interpreter_handler.py).
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
        if settings.TRANSLATION_ENGINE.lower() == "chunked":
            await handle_continuous_translation_stream(websocket, target, voice, room, api_key)
        else:
            await handle_live_interpreter_stream(websocket, target, voice, room, api_key)

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