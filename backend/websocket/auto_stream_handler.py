"""
Call-Center Multi-Agent Bidirectional Translation Engine (Sinhala <-> Tamil).

Business Context:
  Empowers local Sinhala-speaking call-center agents to seamlessly handle high-volume
  Tamil customer calls without requiring a large staff of human translators.

Architecture & Scalability:
  1. Concurrency Model: Supports isolated call rooms for up to 10 concurrent active calls 
     (20 parallel Gemini Live WebSocket streams: 10 Sinhala->Tamil + 10 Tamil->Sinhala).
  2. For EACH connected client in a room, we run TWO Gemini translate sessions:
     - Session A (Target: Tamil):   Translates local agent Sinhala speech -> Tamil
     - Session B (Target: Sinhala): Translates customer Tamil speech -> Sinhala
  3. Real-time language script detection toggles the "active" session dynamically.
  4. Audio output routing:
     - Speaker echo suppression (prevents feedback loops).
     - Translated audio and transcriptions are broadcast to all room callers.
"""
import asyncio
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from backend.config.settings import settings
from backend.websocket.connection_manager import manager

logger = logging.getLogger("backend")

_CODE_LANG = {"si": "Sinhala", "ta": "Tamil", "en": "English"}
_OPPOSITE   = {"ta": "si", "si": "ta", "en": "si"}


def _build_companion_instruction(source_lang: str, target_lang: str, history: list[dict[str, str]] | None = None) -> str:
    """Build a professional call-center translation instruction for the live bridge."""
    recent_context = ""
    if history:
        recent_lines = [f"{item['speaker']}: {item['text']}" for item in history[-6:]]
        recent_context = "\nRecent conversation context:\n" + "\n".join(recent_lines) + "\n"

    return (
        f"You are an expert call-center translator for Sri Lanka. "
        f"Translate spoken {source_lang} into {target_lang} only. "
        f"Keep the tone professional but natural. "
        f"CRITICAL RULES: "
        f"1. Handle Singlish and Tanglish gracefully. If the caller uses English loanwords (e.g., 'credit card', 'balance', 'loan', 'bill', 'account'), adapt them naturally into the {target_lang} context. "
        f"2. Do not translate into any other language. "
        f"3. Output only the translated text in {target_lang} with no extra filler. "
        f"{recent_context}"
    )


def _detect_language(text: str) -> str | None:
    """
    Detect whether text is predominantly Sinhala, Tamil, or English by inspecting
    Unicode script ranges.
    """
    si = ta = en = 0
    for ch in text:
        cp = ord(ch)
        if 0x0D80 <= cp <= 0x0DFF:
            si += 1
        elif 0x0B80 <= cp <= 0x0BFF:
            ta += 1
        elif (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A):
            en += 1
    total = si + ta + en
    if total == 0:
        return None
    # Prioritize native script identification
    if si > 0 and si >= ta:
        return "Sinhala"
    if ta > 0 and ta > si:
        return "Tamil"
    if en / total >= 0.5:
        return "English"
    return None


def _make_config(target_code: str, history: list[dict[str, str]] | None = None) -> types.LiveConnectConfig:
    """Build a translation LiveConnectConfig for the active route (ta or si) [Kept for test compatibility]."""
    target_lang = _CODE_LANG[target_code]
    source_lang = _CODE_LANG[_OPPOSITE[target_code]]
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[
                types.Part.from_text(
                    text=_build_companion_instruction(source_lang, target_lang, history)
                )
            ]
        ),
        translation_config=types.TranslationConfig(
            target_language_code=target_code,
            echo_target_language=True,
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
                silence_duration_ms=150,
            )
        ),
    )


def _build_live_interpreter_instruction(history: list[dict[str, str]] | None = None) -> str:
    """Build high-speed bilingual interpreter instruction matching the Gemini Mobile App Live experience."""
    recent_context = ""
    if history:
        recent_lines = [f"{item['speaker']}: {item['text']}" for item in history[-6:]]
        recent_context = "\nRecent conversation context:\n" + "\n".join(recent_lines) + "\n"

    return (
        "You are an ultra-fast, real-time live bilingual voice interpreter between Sinhala and Tamil for a telephone call center.\n"
        "Your sole task is immediate spoken translation:\n"
        "1. When the speaker speaks in Sinhala, immediately speak the natural, fluent translation in Tamil.\n"
        "2. When the speaker speaks in Tamil, immediately speak the natural, fluent translation in Sinhala.\n"
        "3. Output ONLY the translated speech. Never repeat the original words.\n"
        "4. Never add commentary, explanations, greetings, or conversational filler like 'Sure', 'Understood', or 'Translation:'.\n"
        "5. Seamlessly handle Singlish (Sinhala mixed with English) and Tanglish (Tamil mixed with English). Adapt business and technical loanwords (e.g., 'credit card', 'account number', 'balance', 'loan', 'bill', 'PIN') naturally into the target language.\n"
        "6. Use natural Sri Lankan conversational tone and accurate pronunciation.\n"
        f"{recent_context}"
    )


def _make_live_interpreter_config(voice: str = "Aoede", history: list[dict[str, str]] | None = None) -> types.LiveConnectConfig:
    """Build single-session ultra-low latency live bilingual interpreter config."""
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=voice
                )
            )
        ),
        system_instruction=types.Content(
            parts=[
                types.Part.from_text(
                    text=_build_live_interpreter_instruction(history)
                )
            ]
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
                silence_duration_ms=150,
            )
        ),
    )


async def handle_auto_translation_stream(
    client_ws: WebSocket,
    voice: str = "Aoede",
    room_id: str = "default",
) -> None:
    """
    Handles real-time live bilingual Sinhala <-> Tamil voice translation via a single unified
    Gemini Live session, matching the instant sub-second turnaround of the Gemini Mobile App.
    """
    if not settings.GEMINI_API_KEY:
        await client_ws.send_json({
            "type": "status",
            "payload": {"message": "Error: GEMINI_API_KEY is not configured."}
        })
        await client_ws.close(code=1008, reason="API key missing")
        return

    model = settings.GEMINI_MODEL
    ai_client = genai.Client(api_key=settings.GEMINI_API_KEY)

    state = {
        "source": "Sinhala",
        "target": "Tamil",
        "last_notified": None,
        "history": [],
    }

    in_queue: asyncio.Queue = asyncio.Queue(maxsize=400)
    client_disconnected = asyncio.Event()

    # ── Safe communication helper ────────────────────────────────────────────
    async def safe_send_json(payload: dict) -> bool:
        try:
            await client_ws.send_json(payload)
            return True
        except Exception:
            client_disconnected.set()
            return False

    # ── Client reader: continuously stream incoming audio from client ────────
    async def read_client_forever():
        try:
            while True:
                msg = await client_ws.receive()
                if "bytes" in msg and msg["bytes"]:
                    chunk = msg["bytes"]
                    if not in_queue.full():
                        in_queue.put_nowait(chunk)
        except (WebSocketDisconnect, RuntimeError):
            logger.info(f"Client disconnected from room {room_id}.")
        finally:
            client_disconnected.set()
            try: in_queue.put_nowait(None)
            except asyncio.QueueFull: pass

    # ── Notify initial setup ─────────────────────────────────────────────────
    await safe_send_json({
        "type": "lang_detected",
        "payload": {"source": "Sinhala", "target": "Tamil"},
    })
    state["last_notified"] = "Sinhala->Tamil"

    await safe_send_json({
        "type": "status",
        "payload": {"message": f"Connected to room '{room_id}'! Gemini Live bilingual interpreter active."}
    })

    client_reader = asyncio.create_task(read_client_forever())

    # ── Single unified Gemini Live Interpreter Session ───────────────────────
    async def run_live_bridge():
        config = _make_live_interpreter_config(voice=voice, history=state["history"])
        while not client_disconnected.is_set():
            try:
                async with ai_client.aio.live.connect(model=model, config=config) as session:
                    logger.info(f"Unified Gemini Live interpreter active for room: {room_id}")

                    # 1. Forward microphone audio chunks to Gemini Live
                    async def forward_audio():
                        try:
                            while not client_disconnected.is_set():
                                try:
                                    chunk = await asyncio.wait_for(in_queue.get(), timeout=0.3)
                                except asyncio.TimeoutError:
                                    continue
                                if chunk is None:
                                    client_disconnected.set()
                                    return
                                await session.send_realtime_input(
                                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                                )
                        except asyncio.CancelledError:
                            pass
                        except Exception as ex:
                            logger.error(f"forward_audio error: {ex}")

                    # 2. Receive live transcriptions and translated audio
                    async def receive_responses():
                        try:
                            async for response in session.receive():
                                if client_disconnected.is_set():
                                    break
                                sc = response.server_content
                                if not sc:
                                    continue

                                # ── Real-time input transcription & script detection ──
                                if sc.input_transcription and sc.input_transcription.text:
                                    transcript = sc.input_transcription.text.strip()
                                    if transcript:
                                        state["history"].append({"speaker": "user", "text": transcript})
                                        if len(state["history"]) > 12:
                                            state["history"] = state["history"][-12:]
                                        
                                        detected = _detect_language(transcript)
                                        if detected == "Sinhala":
                                            state["source"], state["target"] = "Sinhala", "Tamil"
                                        elif detected == "Tamil":
                                            state["source"], state["target"] = "Tamil", "Sinhala"

                                        notif_key = f"{state['source']}->{state['target']}"
                                        if state["last_notified"] != notif_key:
                                            state["last_notified"] = notif_key
                                            notif_payload = {
                                                "type": "lang_detected",
                                                "payload": {"source": state["source"], "target": state["target"]},
                                            }
                                            await safe_send_json(notif_payload)
                                            await manager.broadcast_json_except(notif_payload, client_ws, room_id)

                                        transcript_payload = {
                                            "type": "transcription",
                                            "payload": {
                                                "speaker": "user",
                                                "text": transcript,
                                                "detected_lang": detected or state["source"],
                                            },
                                        }
                                        await safe_send_json(transcript_payload)
                                        await manager.broadcast_json_except(transcript_payload, client_ws, room_id)

                                # ── Real-time output translation transcription ────────
                                if sc.output_transcription and sc.output_transcription.text:
                                    ai_text = sc.output_transcription.text.strip()
                                    if ai_text:
                                        state["history"].append({"speaker": "ai", "text": ai_text})
                                        if len(state["history"]) > 12:
                                            state["history"] = state["history"][-12:]
                                        
                                        trans_payload = {
                                            "type": "translation",
                                            "payload": {
                                                "speaker": "ai",
                                                "text": ai_text,
                                            },
                                        }
                                        await safe_send_json(trans_payload)
                                        await manager.broadcast_json_except(trans_payload, client_ws, room_id)

                                # ── Live translated audio bytes streaming ──────────────
                                if sc.model_turn:
                                    for part in sc.model_turn.parts:
                                        if part.inline_data and part.inline_data.data:
                                            room_size = len(manager.rooms.get(room_id, set()))
                                            if room_size <= 1:
                                                try:
                                                    await client_ws.send_bytes(part.inline_data.data)
                                                except Exception:
                                                    client_disconnected.set()
                                                    return
                                            else:
                                                await manager.broadcast_bytes_except(part.inline_data.data, client_ws, room_id)

                                # ── Turn complete notification ────────────────────────
                                if sc.turn_complete:
                                    turn_payload = {"type": "turn_complete", "payload": {}}
                                    await safe_send_json(turn_payload)
                                    await manager.broadcast_json_except(turn_payload, client_ws, room_id)

                        except asyncio.CancelledError:
                            pass
                        except Exception as ex:
                            logger.error(f"receive_responses error: {ex}")

                    fwd = asyncio.create_task(forward_audio())
                    rcv = asyncio.create_task(receive_responses())

                    _, pending = await asyncio.wait([fwd, rcv], return_when=asyncio.FIRST_COMPLETED)
                    for t in pending:
                        t.cancel()
                        try: await t
                        except asyncio.CancelledError: pass

            except Exception as sess_err:
                if client_disconnected.is_set():
                    return
                logger.warning(f"Live interpreter session error: {sess_err}. Reconnecting in 1s...")
                await asyncio.sleep(1)

    live_bridge = asyncio.create_task(run_live_bridge())

    try:
        await asyncio.wait(
            [client_reader, live_bridge],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for t in [client_reader, live_bridge]:
            t.cancel()
            try: await t
            except asyncio.CancelledError: pass
        logger.info(f"Handler for client in room {room_id} finished.")
