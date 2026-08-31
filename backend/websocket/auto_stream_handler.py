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
_FORCE_TARGET = "ta"


def _build_companion_instruction(source_lang: str, target_lang: str, history: list[dict[str, str]] | None = None) -> str:
    """Build a strict Tamil-only translation instruction for the live bridge."""
    recent_context = ""
    if history:
        recent_lines = [f"{item['speaker']}: {item['text']}" for item in history[-6:]]
        recent_context = "\nRecent conversation context:\n" + "\n".join(recent_lines) + "\n"

    return (
        "You are a real-time Sinhala-Tamil translation engine. "
        f"Translate spoken {source_lang} into {target_lang} only. "
        "Do not translate into any other language. "
        "Do not act as a general AI assistant, do not ask questions, do not explain, and do not add commentary. "
        "Output only the translated text in Tamil with no extra filler. "
        "If the user speaks in Sinhala or Tamil, output Tamil only. "
        "Keep the translation accurate and natural. "
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
    if si / total >= 0.5:
        return "Sinhala"
    if ta / total >= 0.5:
        return "Tamil"
    if en / total >= 0.5:
        return "English"
    return None


def _make_config(target_code: str, history: list[dict[str, str]] | None = None) -> types.LiveConnectConfig:
    """Build a Tamil-only translation LiveConnectConfig for the active route."""
    target_code = _FORCE_TARGET
    target_lang = _CODE_LANG[target_code]
    source_lang = "Sinhala or Tamil"
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
                silence_duration_ms=500,
            )
        ),
    )


async def handle_auto_translation_stream(
    client_ws: WebSocket,
    voice: str = "Aoede",
    room_id: str = "default",
) -> None:
    """
    Handles a single client's automatic translation stream inside a room.
    Funnels audio to two Gemini sessions, and broadcasts the output to other room members.
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

    # State for this client
    state = {
        "active": _FORCE_TARGET,
        "last_notified": None,
        "history": [],
    }

    queue_ta: asyncio.Queue = asyncio.Queue(maxsize=300)
    queue_si: asyncio.Queue = asyncio.Queue(maxsize=300)

    client_disconnected = asyncio.Event()

    # ── Safe communication helpers ───────────────────────────────────────────
    async def safe_send_json(payload: dict) -> bool:
        try:
            await client_ws.send_json(payload)
            return True
        except Exception:
            client_disconnected.set()
            return False

    # ── Client reader: read incoming mic and push to both session queues ─────
    async def read_client_forever():
        try:
            while True:
                msg = await client_ws.receive()
                if "bytes" in msg and msg["bytes"]:
                    chunk = msg["bytes"]
                    if not queue_ta.full():
                        queue_ta.put_nowait(chunk)
                    # Force Tamil-only output for this app mode.
                    if not queue_si.full():
                        queue_si.put_nowait(chunk)
        except (WebSocketDisconnect, RuntimeError):
            logger.info(f"Client disconnected from room {room_id}.")
        finally:
            client_disconnected.set()
            try: queue_ta.put_nowait(None)
            except asyncio.QueueFull: pass
            try: queue_si.put_nowait(None)
            except asyncio.QueueFull: pass

    # ── Session runner ───────────────────────────────────────────────────────
    async def run_session(target_code: str, in_queue: asyncio.Queue):
        source_lang = _CODE_LANG[_OPPOSITE[target_code]]
        target_lang = _CODE_LANG[target_code]
        # Force all output to Tamil for this app mode.
        if target_code != _FORCE_TARGET:
            target_code = _FORCE_TARGET
        target_lang = _CODE_LANG[_FORCE_TARGET]
        config = _make_config(target_code, state["history"])

        while not client_disconnected.is_set():
            try:
                async with ai_client.aio.live.connect(
                    model=model, config=config
                ) as session:
                    logger.info(f"Session [{target_code}] opened for client in room: {room_id}")

                    # Forward audio
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
                            logger.error(f"[{target_code}] forward_audio error: {ex}")

                    # Receive responses
                    async def receive_responses():
                        try:
                            async for response in session.receive():
                                if client_disconnected.is_set():
                                    break
                                sc = response.server_content
                                if not sc:
                                    continue

                                # ── Transcription & Lang Detection ────────────
                                if sc.input_transcription and sc.input_transcription.text:
                                    transcript = sc.input_transcription.text.strip()
                                    if transcript:
                                        state["history"].append({"speaker": "user", "text": transcript})
                                        if len(state["history"]) > 12:
                                            state["history"] = state["history"][-12:]
                                    detected = _detect_language(transcript)

                                    if detected is not None:
                                        if detected == source_lang:
                                            if state["active"] != target_code:
                                                state["active"] = target_code
                                                logger.info(f"Lang switch detected: {detected} -> active={target_code}")
                                        elif detected == target_lang:
                                            if state["active"] == target_code:
                                                state["active"] = _OPPOSITE[target_code]
                                                logger.info(f"Yielding lang: detected={detected}, switching to {state['active']}")

                                    # Broadcast lang_detected to sender and other clients in room
                                    active_src = _CODE_LANG[_OPPOSITE[state["active"]]]
                                    active_tgt = _CODE_LANG[state["active"]]
                                    notif_key = f"{active_src}->{active_tgt}"
                                    if state["last_notified"] != notif_key:
                                        state["last_notified"] = notif_key
                                        notif_payload = {
                                            "type": "lang_detected",
                                            "payload": {"source": active_src, "target": active_tgt},
                                        }
                                        await safe_send_json(notif_payload)
                                        await manager.broadcast_json_except(notif_payload, client_ws, room_id)

                                    # Send user transcription to sender and other clients (if this session is active)
                                    if state["active"] == target_code:
                                        transcript_payload = {
                                            "type": "transcription",
                                            "payload": {
                                                "speaker": "user",
                                                "text": transcript,
                                                "detected_lang": detected,
                                            },
                                        }
                                        await safe_send_json(transcript_payload)
                                        await manager.broadcast_json_except(transcript_payload, client_ws, room_id)

                                # Gate: only broadcast translations from the active session
                                if state["active"] != target_code:
                                    continue

                                # ── Broadcast translation text to both speaker and listener ──
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

                                # ── Broadcast translated audio bytes ──
                                # If only 1 device is in the room, send audio to the speaker themselves.
                                # If 2 or more devices are in the room, send it ONLY to the other devices
                                # (preventing speaker-to-mic feedback loops).
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

                                # ── Turn complete status ──────────────────────
                                if sc.turn_complete:
                                    turn_payload = {"type": "turn_complete", "payload": {}}
                                    await safe_send_json(turn_payload)
                                    await manager.broadcast_json_except(turn_payload, client_ws, room_id)

                        except asyncio.CancelledError:
                            pass
                        except Exception as ex:
                            logger.error(f"[{target_code}] receive_responses error: {ex}")

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
                logger.warning(f"[{target_code}] session error: {sess_err}. Reconnecting...")
                await asyncio.sleep(1)

    # ── Notify initial setup ─────────────────────────────────────────────────
    await safe_send_json({
        "type": "lang_detected",
        "payload": {"source": "Sinhala", "target": "Tamil"},
    })
    state["last_notified"] = "Sinhala->Tamil"

    await safe_send_json({
        "type": "status",
        "payload": {"message": f"Connected to room '{room_id}'! Other devices in this room will receive your translation."}
    })

    client_reader = asyncio.create_task(read_client_forever())
    session_ta    = asyncio.create_task(run_session("ta", queue_ta))
    session_si    = asyncio.create_task(run_session("si", queue_si))

    try:
        await asyncio.wait(
            [client_reader, session_ta, session_si],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for t in [client_reader, session_ta, session_si]:
            t.cancel()
            try: await t
            except asyncio.CancelledError: pass
        logger.info(f"Handler for client in room {room_id} finished.")
