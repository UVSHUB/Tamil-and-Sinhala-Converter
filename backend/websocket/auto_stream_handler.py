"""
Auto-detect bidirectional Sinhala <-> Tamil translation using the translate model.

Strategy:
  - Uses the SAME translate model as the main stream_handler (the one confirmed
    to work with the API key: e.g. gemini-3.5-live-translate-preview).
  - Maintains a single client WebSocket while cycling Gemini sessions.
  - Starts with target=Tamil (expecting the user to speak Sinhala).
  - When the input transcription reveals Tamil script, closes the current
    Gemini session and reopens one with target=Sinhala.
  - The audio from the client is buffered in an asyncio.Queue so it feeds
    whichever Gemini session is active.
"""
import asyncio
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from backend.config.settings import settings

logger = logging.getLogger("backend")

_CODE_LANG = {"si": "Sinhala", "ta": "Tamil"}
_OPPOSITE = {"ta": "si", "si": "ta"}


def _detect_language(text: str):
    sinhala = 0
    tamil = 0
    for ch in text:
        cp = ord(ch)
        if 0x0D80 <= cp <= 0x0DFF:
            sinhala += 1
        elif 0x0B80 <= cp <= 0x0BFF:
            tamil += 1
    total = sinhala + tamil
    if total == 0:
        return None
    if sinhala / total >= 0.6:
        return "Sinhala"
    if tamil / total >= 0.6:
        return "Tamil"
    return None


def _build_translate_config(target_code: str) -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        translation_config=types.TranslationConfig(
            target_language_code=target_code,
            echo_target_language=False,
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
                silence_duration_ms=600,
            )
        ),
    )


async def handle_auto_translation_stream(
    client_ws: WebSocket,
    voice: str = "Aoede",
) -> None:
    if not settings.GEMINI_API_KEY:
        await client_ws.send_json({
            "type": "status",
            "payload": {"message": "Error: GEMINI_API_KEY is not configured."}
        })
        await client_ws.close(code=1008, reason="API key missing")
        return

    model = settings.GEMINI_MODEL
    ai_client = genai.Client(api_key=settings.GEMINI_API_KEY)

    audio_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    client_disconnected = asyncio.Event()

    async def read_client_forever():
        try:
            while True:
                msg = await client_ws.receive()
                if "bytes" in msg and msg["bytes"]:
                    await audio_queue.put(("audio", msg["bytes"]))
                elif "text" in msg and msg["text"]:
                    await audio_queue.put(("text", msg["text"]))
        except (WebSocketDisconnect, RuntimeError):
            logger.info("Client WebSocket disconnected.")
        finally:
            client_disconnected.set()
            await audio_queue.put(None)

    client_reader = asyncio.create_task(read_client_forever())

    current_target_code = "ta"

    try:
        while not client_disconnected.is_set():
            source_lang = _CODE_LANG[_OPPOSITE[current_target_code]]
            target_lang = _CODE_LANG[current_target_code]
            config = _build_translate_config(current_target_code)

            logger.info(f"Opening session [{model}]: {source_lang} -> {target_lang}")

            try:
                await client_ws.send_json({
                    "type": "lang_detected",
                    "payload": {"source": source_lang, "target": target_lang},
                })
            except Exception:
                break

            flip_needed = asyncio.Event()

            try:
                async with ai_client.aio.live.connect(model=model, config=config) as session:
                    logger.info("Gemini translate session established.")
                    try:
                        await client_ws.send_json({
                            "type": "status",
                            "payload": {
                                "message": (
                                    f"Auto Mode: Speak {source_lang} to get {target_lang}. "
                                    "Language is detected and switched automatically!"
                                )
                            },
                        })
                    except Exception:
                        break

                    async def forward_audio():
                        try:
                            while not flip_needed.is_set() and not client_disconnected.is_set():
                                try:
                                    item = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
                                except asyncio.TimeoutError:
                                    continue
                                if item is None:
                                    client_disconnected.set()
                                    return
                                msg_type, data = item
                                if msg_type == "audio":
                                    await session.send_realtime_input(
                                        audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                                    )
                        except asyncio.CancelledError:
                            pass
                        except Exception as ex:
                            logger.error(f"forward_audio error: {ex}")

                    async def receive_responses():
                        try:
                            async for response in session.receive():
                                if flip_needed.is_set() or client_disconnected.is_set():
                                    break
                                sc = response.server_content
                                if not sc:
                                    continue

                                if sc.input_transcription and sc.input_transcription.text:
                                    transcript = sc.input_transcription.text
                                    detected = _detect_language(transcript)
                                    try:
                                        await client_ws.send_json({
                                            "type": "transcription",
                                            "payload": {
                                                "speaker": "user",
                                                "text": transcript,
                                                "detected_lang": detected,
                                            },
                                        })
                                    except Exception:
                                        client_disconnected.set()
                                        return
                                    if detected is not None:
                                        expected_source = _CODE_LANG[_OPPOSITE[current_target_code]]
                                        if detected != expected_source:
                                            logger.info(f"Language flip: {detected} != {expected_source}")
                                            flip_needed.set()
                                            break

                                if sc.output_transcription and sc.output_transcription.text:
                                    try:
                                        await client_ws.send_json({
                                            "type": "translation",
                                            "payload": {
                                                "speaker": "ai",
                                                "text": sc.output_transcription.text,
                                            },
                                        })
                                    except Exception:
                                        client_disconnected.set()
                                        return

                                if sc.model_turn:
                                    for part in sc.model_turn.parts:
                                        if part.inline_data and part.inline_data.data:
                                            try:
                                                await client_ws.send_bytes(part.inline_data.data)
                                            except Exception:
                                                client_disconnected.set()
                                                return

                                if sc.turn_complete:
                                    try:
                                        await client_ws.send_json({
                                            "type": "turn_complete",
                                            "payload": {},
                                        })
                                    except Exception:
                                        client_disconnected.set()
                                        return
                        except asyncio.CancelledError:
                            pass
                        except Exception as ex:
                            logger.error(f"receive_responses error: {ex}")

                    fwd_task = asyncio.create_task(forward_audio())
                    rcv_task = asyncio.create_task(receive_responses())
                    done, pending = await asyncio.wait([fwd_task, rcv_task], return_when=asyncio.FIRST_COMPLETED)
                    for t in pending:
                        t.cancel()
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass

            except Exception as session_err:
                logger.error(f"Gemini session error: {session_err}")
                try:
                    await client_ws.send_json({
                        "type": "status",
                        "payload": {"message": f"Session error: {session_err}"},
                    })
                except Exception:
                    pass
                break

            if flip_needed.is_set() and not client_disconnected.is_set():
                current_target_code = _OPPOSITE[current_target_code]
                drained = 0
                while not audio_queue.empty():
                    try:
                        audio_queue.get_nowait()
                        drained += 1
                    except asyncio.QueueEmpty:
                        break
                if drained:
                    logger.info(f"Drained {drained} stale packets before session flip.")
                await asyncio.sleep(0.15)
            else:
                break
    finally:
        client_reader.cancel()
        try:
            await client_reader
        except asyncio.CancelledError:
            pass
        logger.info("Auto-detect handler exited.")
