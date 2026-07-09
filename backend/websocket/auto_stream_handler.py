"""
Room-based Multi-device Walkie-Talkie Bidirectional Translation (Sinhala <-> Tamil).

Architecture:
  1. For EACH connected client in a room, we run TWO Gemini translate sessions:
     - Session A: target=Tamil   (translates Sinhala -> Tamil)
     - Session B: target=Sinhala (translates Tamil -> Sinhala)

  2. Both sessions receive all incoming audio from their client.
  3. Real-time language detection via input_transcription toggles the "active" session.
  4. Audio output routing:
     - The speaker does NOT hear their own translation (prevents speaker-to-mic feedback loops).
     - The translated voice audio is broadcast to all OTHER clients in the room.
     - Both speaker and listener see the transcription and translation texts on their screen.
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

_CODE_LANG = {"si": "Sinhala", "ta": "Tamil"}
_OPPOSITE   = {"ta": "si", "si": "ta"}


def _detect_language(text: str) -> str | None:
    """
    Detect whether text is predominantly Sinhala or Tamil by inspecting
    Unicode script ranges.
    """
    si = ta = 0
    for ch in text:
        cp = ord(ch)
        if 0x0D80 <= cp <= 0x0DFF:
            si += 1
        elif 0x0B80 <= cp <= 0x0BFF:
            ta += 1
    total = si + ta
    if total == 0:
        return None
    if si / total >= 0.6:
        return "Sinhala"
    if ta / total >= 0.6:
        return "Tamil"
    return None


def _make_config(target_code: str) -> types.LiveConnectConfig:
    """
    Build a translate LiveConnectConfig for the given target language.
    echo_target_language=True is critical so input_transcription always
    arrives even when the user speaks in the target language.
    """
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
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
        "active": "ta",          # Assume Sinhala input initially (output Tamil)
        "last_notified": None,
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
        config = _make_config(target_code)

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
                                    transcript = sc.input_transcription.text
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
                                    trans_payload = {
                                        "type": "translation",
                                        "payload": {
                                            "speaker": "ai",
                                            "text": sc.output_transcription.text,
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
