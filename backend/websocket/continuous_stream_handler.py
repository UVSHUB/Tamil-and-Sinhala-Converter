"""
Continuous Real-Time Rolling-Chunk Translator (Sinhala <-> Tamil + English Auto-Detect).

Solves the continuous speech problem:
1. The user speaks continuously without stopping.
2. The system listens in the background non-stop (full duplex).
3. Audio is accumulated and sliced every ~4.5 - 5 seconds (or upon a natural speech pause).
4. Each ~5s slice is translated to the chosen target language (Tamil or Sinhala),
   auto-detecting whether the input speech was Sinhala, Tamil, or English.
5. The translated text is synthesized into natural audio via Gemini TTS and returned immediately.
6. The user can switch the output language (Tamil <-> Sinhala) on the fly without reconnecting.
"""

import asyncio
import io
import json
import logging
import math
import struct
import time
import wave
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from backend.config.settings import settings
from backend.websocket.connection_manager import manager

logger = logging.getLogger("backend")

# Audio specs
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit PCM = 2 bytes per sample
BYTES_PER_SECOND = SAMPLE_RATE * SAMPLE_WIDTH  # 32,000 bytes/sec

# Cadence thresholds
MAX_CHUNK_SECONDS = 4.5  # Slices continuous speech every 4.5 seconds
MAX_CHUNK_BYTES = int(BYTES_PER_SECOND * MAX_CHUNK_SECONDS)  # 144,000 bytes
MIN_CHUNK_BYTES = int(BYTES_PER_SECOND * 0.9)  # Minimum 0.9s of speech before pause trigger
PAUSE_SILENCE_SECONDS = 0.40  # 400ms pause triggers early translation
OVERLAP_SECONDS = 0.15  # 150ms overlap to prevent boundary clipping
OVERLAP_BYTES = int(BYTES_PER_SECOND * OVERLAP_SECONDS)
NOISE_GATE_RMS = 0.006  # Noise gate threshold


def calculate_rms(pcm_bytes: bytes) -> float:
    """Calculates normalized RMS volume of 16-bit mono PCM bytes."""
    num_samples = len(pcm_bytes) // 2
    if num_samples == 0:
        return 0.0
    try:
        # Unpack 16-bit signed integers
        samples = struct.unpack(f"<{num_samples}h", pcm_bytes)
        sum_sq = sum(s * s for s in samples)
        rms = math.sqrt(sum_sq / num_samples) / 32768.0
        return rms
    except Exception:
        return 0.0


def pcm_to_wav(pcm_bytes: bytes) -> bytes:
    """Wraps raw 16kHz 16-bit mono PCM into a valid WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


async def handle_continuous_translation_stream(
    client_ws: WebSocket,
    target: str = "Tamil",
    voice: str = "Aoede",
    room_id: str = "default",
    api_key: str | None = None,
) -> None:
    final_api_key = api_key if (api_key and api_key.startswith("AIza")) else settings.GEMINI_API_KEY
    if not final_api_key:
        await client_ws.send_json({
            "type": "status",
            "payload": {"message": "Error: GEMINI_API_KEY is not configured and no custom key provided."}
        })
        await client_ws.close(code=1008, reason="API key missing")
        return

    ai_client = genai.Client(api_key=final_api_key)

    # State container
    state = {
        "target_lang": "Tamil" if "tamil" in target.lower() else "Sinhala",
        "voice": voice,
        "history": [],
        "segment_count": 0,
    }

    client_disconnected = asyncio.Event()
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=500)
    process_queue: asyncio.Queue[tuple[int, bytes, str, str]] = asyncio.Queue(maxsize=30)

    async def safe_send_json(payload: dict) -> bool:
        if client_disconnected.is_set():
            return False
        try:
            await client_ws.send_json(payload)
            return True
        except Exception:
            client_disconnected.set()
            return False

    async def safe_send_bytes(data: bytes) -> bool:
        if client_disconnected.is_set():
            return False
        try:
            await client_ws.send_bytes(data)
            return True
        except Exception:
            client_disconnected.set()
            return False

    # Notify connected status and current configuration
    await safe_send_json({
        "type": "status",
        "payload": {
            "message": (
                f"Continuous Stream Engine Active! Target: {state['target_lang']}. "
                "Listening non-stop; translates every ~4.5s continuously."
            )
        }
    })
    await safe_send_json({
        "type": "lang_detected",
        "payload": {"source": "Auto-Detect", "target": state["target_lang"]},
    })

    # ──────────────────────────────────────────────────────────────────────────
    # Task 1: Ingest WebSocket messages from client (Mic PCM + JSON commands)
    # ──────────────────────────────────────────────────────────────────────────
    async def read_client():
        try:
            while not client_disconnected.is_set():
                msg = await client_ws.receive()
                if "bytes" in msg and msg["bytes"]:
                    chunk = msg["bytes"]
                    if not audio_queue.full():
                        audio_queue.put_nowait(chunk)
                elif "text" in msg and msg["text"]:
                    raw = msg["text"].strip()
                    try:
                        data = json.loads(raw)
                        msg_type = data.get("type")
                        if msg_type == "set_target":
                            new_target = data.get("target", "Tamil")
                            state["target_lang"] = "Tamil" if "tamil" in new_target.lower() else "Sinhala"
                            logger.info(f"Updated target language to: {state['target_lang']}")
                            await safe_send_json({
                                "type": "status",
                                "payload": {"message": f"Output language switched to {state['target_lang']}"}
                            })
                            await safe_send_json({
                                "type": "lang_detected",
                                "payload": {"source": "Auto-Detect", "target": state["target_lang"]},
                            })
                        elif msg_type == "set_voice":
                            new_voice = data.get("voice", "Aoede")
                            state["voice"] = new_voice
                            await safe_send_json({
                                "type": "status",
                                "payload": {"message": f"TTS Voice set to {state['voice']}"}
                            })
                    except json.JSONDecodeError:
                        pass
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            client_disconnected.set()
            try:
                audio_queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    # ──────────────────────────────────────────────────────────────────────────
    # Task 2: Rolling Buffer & VAD Slicer (Continuous 4.5s Cadence)
    # ──────────────────────────────────────────────────────────────────────────
    async def slice_audio_cadence():
        accumulated_speech = bytearray()
        silence_bytes = 0
        silence_threshold_bytes = int(BYTES_PER_SECOND * PAUSE_SILENCE_SECONDS)

        while not client_disconnected.is_set():
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.15)
            except asyncio.TimeoutError:
                continue

            if chunk is None:
                break

            rms = calculate_rms(chunk)
            is_voiced = rms >= NOISE_GATE_RMS

            if is_voiced:
                silence_bytes = 0
                accumulated_speech.extend(chunk)
            else:
                if len(accumulated_speech) > 0:
                    accumulated_speech.extend(chunk)
                    silence_bytes += len(chunk)

            # Check Cadence Conditions
            curr_len = len(accumulated_speech)

            # Condition A: Continuous speech reached maximum ~4.5 seconds duration
            should_slice_continuous = curr_len >= MAX_CHUNK_BYTES

            # Condition B: Natural pause after sufficient speech
            should_slice_pause = curr_len >= MIN_CHUNK_BYTES and silence_bytes >= silence_threshold_bytes

            if should_slice_continuous or should_slice_pause:
                state["segment_count"] += 1
                seg_id = state["segment_count"]
                audio_slice = bytes(accumulated_speech)

                # Keep overlap to preserve words on slice boundary
                if should_slice_continuous and curr_len > OVERLAP_BYTES:
                    accumulated_speech = bytearray(accumulated_speech[-OVERLAP_BYTES:])
                else:
                    accumulated_speech.clear()

                silence_bytes = 0

                # Queue the slice for async translation and TTS synthesis
                if not process_queue.full():
                    process_queue.put_nowait((seg_id, audio_slice, state["target_lang"], state["voice"]))
                else:
                    logger.warning("Process queue full, dropping oldest slice.")

    # ──────────────────────────────────────────────────────────────────────────
    # Task 3: Translation & Speech Synthesis Worker
    # ──────────────────────────────────────────────────────────────────────────
    async def process_translation_slices():
        translate_models = [
            settings.TRANSLATE_MODEL,
            "gemini-3.1-flash-lite-preview",
            "gemini-3.5-flash",
            "gemini-flash-latest",
        ]
        tts_models = [
            settings.TTS_MODEL,
            "gemini-3.8-flash-tts",
            "gemini-2.5-flash-preview-tts",
        ]

        while not client_disconnected.is_set():
            try:
                seg_id, pcm_bytes, target_lang, voice_name = await asyncio.wait_for(
                    process_queue.get(), timeout=0.25
                )
            except asyncio.TimeoutError:
                continue

            if client_disconnected.is_set():
                break

            wav_data = pcm_to_wav(pcm_bytes)
            prompt = (
                "You are an expert real-time voice translator in Sri Lanka. "
                "The user speaks naturally in Sinhala, Tamil, or English (including Singlish and Tanglish). "
                f"1. Detect whether the speaker spoke Sinhala, Tamil, or English. "
                "2. Transcribe the speech text verbatim. "
                f"3. Translate the meaning accurately and fluently into {target_lang}. "
                "If the speaker already spoke the target language, keep it natural and correct in that language. "
                "If the audio is silent, background coughs, or noise, leave transcription and translation as empty strings. "
                "Respond ONLY with valid JSON with keys: "
                '{"detected_language": "Sinhala"|"Tamil"|"English", "transcription": "...", "translation": "..."}'
            )

            res_data = None
            t0 = time.time()

            # Step 1: Speech-to-Translated-Text
            for model_name in translate_models:
                try:
                    res = await asyncio.to_thread(
                        ai_client.models.generate_content,
                        model=model_name,
                        contents=[
                            types.Part.from_bytes(data=wav_data, mime_type="audio/wav"),
                            prompt,
                        ],
                        config=types.GenerateContentConfig(response_mime_type="application/json"),
                    )
                    text = (res.text or "").strip()
                    if text:
                        res_data = json.loads(text)
                        break
                except Exception as ex:
                    logger.debug(f"Model {model_name} error: {ex}, trying fallback...")
                    continue

            if not res_data:
                continue

            transcription = (res_data.get("transcription") or "").strip()
            translation = (res_data.get("translation") or "").strip()
            detected_lang = res_data.get("detected_language") or "Sinhala"

            if not transcription or not translation:
                continue

            logger.info(
                f"[Seg #{seg_id}] ({time.time()-t0:.2f}s) "
                f"{detected_lang} -> {target_lang}: '{transcription}' => '{translation}'"
            )

            # Broadcast detected language and transcripts
            lang_payload = {
                "type": "lang_detected",
                "payload": {"source": detected_lang, "target": target_lang},
            }
            await safe_send_json(lang_payload)
            await manager.broadcast_json_except(lang_payload, client_ws, room_id)

            user_payload = {
                "type": "transcription",
                "payload": {
                    "speaker": "user",
                    "text": transcription,
                    "detected_lang": detected_lang,
                },
            }
            await safe_send_json(user_payload)
            await manager.broadcast_json_except(user_payload, client_ws, room_id)

            ai_payload = {
                "type": "translation",
                "payload": {
                    "speaker": "ai",
                    "text": translation,
                    "target_lang": target_lang,
                },
            }
            await safe_send_json(ai_payload)
            await manager.broadcast_json_except(ai_payload, client_ws, room_id)

            # Step 2: Speech Synthesis (TTS) for the translated text
            audio_bytes = None
            for tts_model in tts_models:
                try:
                    tts_res = await asyncio.to_thread(
                        ai_client.models.generate_content,
                        model=tts_model,
                        contents=translation,
                        config=types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=types.SpeechConfig(
                                voice_config=types.VoiceConfig(
                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                                )
                            ),
                        ),
                    )
                    if tts_res.candidates and tts_res.candidates[0].content:
                        for p in tts_res.candidates[0].content.parts:
                            if p.inline_data and p.inline_data.data:
                                audio_bytes = p.inline_data.data
                                break
                    if audio_bytes:
                        break
                except Exception as tts_err:
                    logger.debug(f"TTS {tts_model} error: {tts_err}, trying fallback...")
                    continue

            if audio_bytes:
                # Send synthesized audio bytes directly to the client
                await safe_send_bytes(audio_bytes)
                if room_id in manager.rooms and len(manager.rooms[room_id]) > 1:
                    await manager.broadcast_bytes_except(audio_bytes, client_ws, room_id)

            # Signal turn complete for UI
            turn_payload = {"type": "turn_complete", "payload": {}}
            await safe_send_json(turn_payload)
            await manager.broadcast_json_except(turn_payload, client_ws, room_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Run all tasks concurrently
    # ──────────────────────────────────────────────────────────────────────────
    task_read = asyncio.create_task(read_client())
    task_slice = asyncio.create_task(slice_audio_cadence())
    task_proc = asyncio.create_task(process_translation_slices())

    try:
        await asyncio.wait(
            [task_read, task_slice, task_proc],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        client_disconnected.set()
        for t in [task_read, task_slice, task_proc]:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        logger.info(f"Continuous translation session closed for room: {room_id}")
