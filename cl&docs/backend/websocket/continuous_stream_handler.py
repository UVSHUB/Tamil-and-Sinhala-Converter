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
import base64
import io
import json
import logging
import math
import os
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

# Cadence thresholds (Optimized for ultra-low latency)
MAX_CHUNK_SECONDS = 3.0  # Slices continuous speech every 3.0 seconds (down from 4.5s)
MAX_CHUNK_BYTES = int(BYTES_PER_SECOND * MAX_CHUNK_SECONDS)  # 96,000 bytes
MIN_CHUNK_BYTES = int(BYTES_PER_SECOND * 0.45)  # 450ms of speech minimum before pause trigger (down from 0.9s)
PAUSE_SILENCE_SECONDS = 0.25  # 250ms pause triggers early translation (down from 400ms)
OVERLAP_SECONDS = 0.12  # 120ms overlap to prevent boundary clipping
OVERLAP_BYTES = int(BYTES_PER_SECOND * OVERLAP_SECONDS)
NOISE_GATE_RMS = 0.005  # Sensitive noise gate threshold


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


MIME_BY_EXT = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
    ".3gp": "audio/3gpp",
    ".3gpp": "audio/3gpp",
    ".amr": "audio/amr",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".aifc": "audio/aiff",
    ".pcm": "audio/pcm",
    ".raw": "audio/pcm",
}


def detect_audio_mime(raw: bytes = b"", filename: str = "") -> str:
    """Detects the MIME type of an audio file from its filename extension or magic header bytes."""
    if filename:
        ext = os.path.splitext(filename.lower())[1]
        if ext in MIME_BY_EXT and ext not in (".pcm", ".raw"):
            return MIME_BY_EXT[ext]
        if ext in (".pcm", ".raw") and raw[:4] != b"RIFF":
            return "audio/pcm"
    if raw[:4] == b"RIFF":
        return "audio/wav"
    if raw[:3] == b"ID3" or (len(raw) >= 2 and raw[0] == 0xFF and (raw[1] & 0xE0) == 0xE0):
        return "audio/mp3"
    if raw[:4] == b"OggS":
        return "audio/ogg"
    if raw[:4] == b"fLaC":
        return "audio/flac"
    if len(raw) >= 8 and raw[4:8] == b"ftyp":
        return "audio/mp4"
    if raw[:4] == b"\x1a\x45\xdf\xa3":
        return "audio/webm"
    return "audio/pcm"


def is_gemini_api_key(api_key: str | None) -> bool:
    """Return True if `api_key` looks like a direct Google Gemini API key (e.g. AIza... or AQ....)."""
    if not api_key:
        return False
    cleaned = api_key.strip()
    if cleaned.startswith("sk_") or cleaned == "your_gemini_api_key_here":
        return False
    return cleaned.startswith(("AIza", "AQ.")) or len(cleaned) >= 20


def classify_gemini_error(err: Exception | str | None) -> str | None:
    """Return a clear user-facing error message if `err` is an API key, billing (402), or quota (429) error."""
    if not err:
        return None
    text = str(err)
    lower = text.lower()
    if "prepayment credits are depleted" in lower or "402" in text or "payment required" in lower:
        return (
            "ERROR: Gemini API key prepayment credits are depleted (HTTP 402). "
            "Please update GEMINI_API_KEY in .env (or type 'key <NEW_GEMINI_API_KEY>' in interactive mode)."
        )
    if "api_key_invalid" in lower or "api key not valid" in lower or "invalid api key" in lower:
        return (
            "ERROR: Gemini API key is invalid. "
            "Please update GEMINI_API_KEY in .env (or type 'key <NEW_GEMINI_API_KEY>' in interactive mode)."
        )
    if "resource_exhausted" in text or "429" in text or "quota" in lower:
        return (
            "ERROR: Gemini API quota exceeded (HTTP 429) for this API key. "
            "Wait a while or update GEMINI_API_KEY in .env (or type 'key <NEW_GEMINI_API_KEY>')."
        )
    return None


def create_genai_client(api_key: str, api_version: str = "v1beta") -> genai.Client:
    """Create a Google GenAI client with v1beta and clean base_url (fixes HTTP 404 in google-genai >= 3.0)."""
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            base_url="https://generativelanguage.googleapis.com",
            api_version=api_version,
        ),
    )


async def transcribe_and_translate_wav(
    ai_client: genai.Client,
    wav_data: bytes,
    target_lang: str = "Tamil",
    source_lang: str = "Auto-Detect",
    mime_type: str = "audio/wav",
) -> dict | None:
    """Transcribes speech from audio bytes (WAV, MP3, M4A, OGG, FLAC, AAC, WEBM) and translates it into target_lang using Gemini."""
    if mime_type == "audio/pcm":
        wav_data = pcm_to_wav(wav_data)
        mime_type = "audio/wav"
    translate_models = [
        settings.TRANSLATE_MODEL,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.8-flash",
        "gemini-flash-latest",
    ]
    source_hint = (
        "Detect whether the speaker spoke Sinhala, Tamil, or English."
        if source_lang.lower() in ("auto", "auto-detect", "")
        else f"The speaker is speaking {source_lang} (possibly mixed with English loanwords)."
    )
    prompt = (
        "You are an expert real-time voice translator in Sri Lanka. "
        "The user speaks naturally in Sinhala, Tamil, or English (including Singlish and Tanglish). "
        f"1. {source_hint} "
        "2. Transcribe the speech text verbatim. "
        f"3. Translate the meaning accurately and fluently into {target_lang}. "
        "If the speaker already spoke the target language, keep it natural and correct in that language. "
        "If the audio is silent, background coughs, or noise, leave transcription and translation as empty strings. "
        "Respond ONLY with valid JSON with keys: "
        '{"detected_language": "Sinhala"|"Tamil"|"English", "transcription": "...", "translation": "..."}'
    )
    setattr(ai_client, "_last_gemini_error", None)
    for model_name in translate_models:
        try:
            res = await asyncio.to_thread(
                ai_client.models.generate_content,
                model=model_name,
                contents=[
                    types.Part.from_bytes(data=wav_data, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
            text = (res.text or "").strip()
            if text:
                return json.loads(text)
        except Exception as ex:
            setattr(ai_client, "_last_gemini_error", ex)
            logger.debug(f"Model {model_name} error: {ex}, trying fallback...")
            if classify_gemini_error(ex):
                break
            continue
    return None


async def synthesize_tts_audio(
    ai_client: genai.Client,
    text: str,
    voice_name: str = "Aoede",
) -> bytes | None:
    """Synthesizes 24kHz 16-bit mono PCM audio for `text` using Gemini TTS models."""
    if not text or not text.strip():
        return None
    tts_models = [
        settings.TTS_MODEL,
        "gemini-2.5-flash-preview-tts",
        "gemini-3.8-flash-lite-tts",
        "gemini-3.1-flash-tts-preview",
        "gemini-3.8-flash-tts",
    ]
    for tts_model in tts_models:
        try:
            tts_res = await asyncio.to_thread(
                ai_client.models.generate_content,
                model=tts_model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name or "Aoede")
                        )
                    ),
                ),
            )
            if tts_res.candidates and tts_res.candidates[0].content:
                for p in tts_res.candidates[0].content.parts:
                    if p.inline_data and p.inline_data.data:
                        return p.inline_data.data
        except Exception as tts_err:
            logger.debug(f"TTS {tts_model} error: {tts_err}, trying fallback...")
            continue
    return None


async def handle_continuous_translation_stream(
    client_ws: WebSocket,
    target: str = "Tamil",
    voice: str = "Aoede",
    room_id: str = "default",
    api_key: str | None = None,
) -> None:
    final_api_key = api_key if is_gemini_api_key(api_key) else settings.GEMINI_API_KEY
    if not final_api_key:
        await client_ws.send_json({
            "type": "status",
            "payload": {"message": "Error: GEMINI_API_KEY is not configured and no custom key provided."}
        })
        await client_ws.close(code=1008, reason="API key missing")
        return

    ai_client = create_genai_client(final_api_key)

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
                        elif msg_type == "audio_eof":
                            if not audio_queue.full():
                                audio_queue.put_nowait(b"__AUDIO_EOF__")
                        elif msg_type == "audio_file":
                            raw_audio = base64.b64decode(data.get("data_b64", ""))
                            mime = data.get("mime_type") or detect_audio_mime(raw_audio)
                            if raw_audio:
                                res_data = await transcribe_and_translate_wav(
                                    ai_client, raw_audio, target_lang=state["target_lang"], mime_type=mime
                                )
                                if res_data:
                                    transcription = (res_data.get("transcription") or "").strip()
                                    translation = (res_data.get("translation") or "").strip()
                                    detected_lang = res_data.get("detected_language") or "Sinhala"
                                    await safe_send_json({"type": "lang_detected", "payload": {"source": detected_lang, "target": state["target_lang"]}})
                                    if transcription:
                                        await safe_send_json({"type": "transcription", "payload": {"speaker": "user", "text": transcription, "detected_lang": detected_lang}})
                                    if translation:
                                        await safe_send_json({"type": "translation", "payload": {"speaker": "ai", "text": translation, "target_lang": state["target_lang"]}})
                                        tts_bytes = await synthesize_tts_audio(ai_client, translation, state["voice"])
                                        if tts_bytes:
                                            await safe_send_bytes(tts_bytes)
                                    await safe_send_json({"type": "turn_complete", "payload": {"user_text": transcription, "ai_text": translation}})
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
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.18)
            except asyncio.TimeoutError:
                # When speaker pauses, frontend AudioWorklet drops silence frames so queue times out.
                # Flush the speech segment immediately for ultra-low latency response!
                if len(accumulated_speech) >= MIN_CHUNK_BYTES:
                    state["segment_count"] += 1
                    seg_id = state["segment_count"]
                    audio_slice = bytes(accumulated_speech)
                    accumulated_speech.clear()
                    silence_bytes = 0
                    if not process_queue.full():
                        process_queue.put_nowait((seg_id, audio_slice, state["target_lang"], state["voice"]))
                continue

            if chunk is None:
                break

            if chunk == b"__AUDIO_EOF__":
                if len(accumulated_speech) > 0:
                    state["segment_count"] += 1
                    seg_id = state["segment_count"]
                    audio_slice = bytes(accumulated_speech)
                    accumulated_speech.clear()
                    silence_bytes = 0
                    if not process_queue.full():
                        process_queue.put_nowait((seg_id, audio_slice, state["target_lang"], state["voice"]))
                continue

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
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite-preview",
            "gemini-3.8-flash",
            "gemini-flash-latest",
        ]
        tts_models = [
            settings.TTS_MODEL,
            "gemini-3.8-flash-lite-tts",
            "gemini-3.1-flash-tts-preview",
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
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                        ),
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

            # Signal turn complete for UI & CLI clients
            turn_payload = {
                "type": "turn_complete",
                "payload": {"user_text": transcription, "ai_text": translation},
            }
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
