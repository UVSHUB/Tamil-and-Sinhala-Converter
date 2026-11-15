"""
Live Interpreter Engine for /ws/translate-auto (Sinhala / Tamil / English -> chosen target).

Two modes, chosen with TRANSLATION_ENGINE in .env:

  "simultaneous" (default) - Gemini Live *translate* model. Translates WHILE the person
      is still talking, like a human simultaneous interpreter: the translated voice starts
      ~3-4 s after the speaker starts and runs ~1 s behind them. Speech that is already in
      the target language (including the translator's own voice picked up by the
      microphone) is answered with silence, so speakers cannot cause a feedback loop.

  "live" - general Gemini Live model with an interpreter prompt. Waits until the speaker
      pauses, then translates the whole sentence with full context (most accurate, but the
      voice only starts after the speaker stops).

Both keep ONE Gemini Live session open per client - no per-request quota, unlike the older
"chunked" engine (continuous_stream_handler.py) which needed a translate + TTS request for
every ~3 s of speech and exhausted the free tier within minutes.

Wire protocol (unchanged, so the web app and CLI client keep working):
  client -> server : binary 16 kHz mono 16-bit PCM, plain text to translate,
                     JSON {"type": "set_target", "target": "Tamil"|"Sinhala"},
                     JSON {"type": "set_voice", "voice": "Aoede"}
  server -> client : binary 24 kHz mono 16-bit PCM (translated voice),
                     JSON status / lang_detected / transcription / translation,
                     JSON turn_complete {"user_text": ..., "ai_text": ...} after each sentence
"""

import array
import asyncio
import base64
import json
import logging
import time

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from backend.config.settings import settings
from backend.websocket.connection_manager import manager
from backend.websocket.continuous_stream_handler import (
    BYTES_PER_SECOND,
    MAX_CHUNK_BYTES,
    MIN_CHUNK_BYTES,
    PAUSE_SILENCE_SECONDS,
    create_genai_client,
    detect_audio_mime,
    pcm_to_wav,
    synthesize_tts_audio,
    transcribe_and_translate_wav,
)

logger = logging.getLogger("backend")

SAMPLE_RATE = 16000
FRAME_SECONDS = 0.1
SILENCE_FRAME = b"\x00" * int(SAMPLE_RATE * 2 * FRAME_SECONDS)  # 100 ms of silence

# Browsers (and the phone bridge) stop sending audio while the user is quiet, but
# Gemini has to *hear* the pause to finish a sentence, so we feed it silence for a
# short while after the last real audio.
SILENCE_AFTER_SPEECH_SECONDS = 1.5
# Only start filling in silence once audio has really stopped. Packets arrive every ~100 ms
# with network jitter; filling every small gap would splice silence into the middle of
# words and garble the speech.
SILENCE_GAP_SECONDS = 0.3
LEAD_IN_FRAMES = 5  # 0.5 s of silence at the start of every session

# Simultaneous mode never signals the end of a sentence, so we close a sentence when the
# translation ends with sentence punctuation or goes quiet for this long.
SENTENCE_END = (".", "?", "!", "।", "෴")
SENTENCE_IDLE_SECONDS = 2.0

SILENT_PEAK = 64  # audio packets quieter than this (out of 32767) are not sent to the client
MAX_RECONNECT_ATTEMPTS = 5
HISTORY_TURNS = 6
LANG_CODES = {"Sinhala": "si", "Tamil": "ta"}


def normalize_target(target: str) -> str:
    return "Sinhala" if "sinhala" in (target or "").lower() else "Tamil"


def detect_language(text: str) -> str | None:
    """Detect Sinhala / Tamil / English from the Unicode script of a transcript.

    Singlish / Tanglish is common, so any Sinhala or Tamil word decides the language;
    the text counts as English only when it contains no Sinhala or Tamil at all."""
    si = sum(1 for ch in text if 0x0D80 <= ord(ch) <= 0x0DFF)
    ta = sum(1 for ch in text if 0x0B80 <= ord(ch) <= 0x0BFF)
    if si or ta:
        return "Sinhala" if si >= ta else "Tamil"
    if any(ch.isascii() and ch.isalpha() for ch in text):
        return "English"
    return None


def is_silent(pcm: bytes) -> bool:
    """True if a 16-bit PCM packet contains no audible sound."""
    samples = array.array("h", pcm[: len(pcm) // 2 * 2])
    return not samples or max(samples) < SILENT_PEAK and -min(samples) < SILENT_PEAK


def is_simultaneous(engine: str | None = None) -> bool:
    return (engine or settings.TRANSLATION_ENGINE).lower() != "live"


def build_instruction(target: str, history: list[dict] | None = None) -> str:
    """System prompt for the turn-based "live" mode."""
    context = ""
    if history:
        lines = [f"{h['speaker']}: {h['text']}" for h in history[-HISTORY_TURNS:]]
        context = "\n\nRecent conversation (for context only, do not repeat it):\n" + "\n".join(lines)
    return (
        "You are a professional real-time voice interpreter in Sri Lanka.\n"
        f"Translate everything the speaker says into {target}. The speaker may talk in Sinhala, "
        "Tamil or English, often mixed (Singlish / Tanglish).\n"
        "STRICT RULES:\n"
        f"1. Speak ONLY the {target} translation. Never answer questions, never give opinions, "
        "never add greetings, explanations or comments of your own - you are an interpreter, "
        "not an assistant. If the speaker asks a question, translate the question.\n"
        "2. Never repeat the original words. Translate the full meaning accurately and naturally, "
        "using everyday Sri Lankan phrasing and a polite tone.\n"
        "3. Keep names of people, places, brands and numbers unchanged.\n"
        f"4. Translate English loanwords naturally (e.g. 'credit card', 'balance', 'loan', 'bill') "
        f"the way a Sri Lankan {target} speaker would say them.\n"
        f"5. If the speech is already in {target}, say nothing (it may be your own voice "
        "coming back through the speakers).\n"
        "6. If you hear only noise, coughing or silence, say nothing."
        f"{context}"
    )


def build_config(target: str, voice: str, history: list[dict] | None = None,
                 engine: str | None = None, model_name: str | None = None) -> types.LiveConnectConfig:
    transcription = dict(
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )
    use_translate_config = is_simultaneous(engine) and (model_name is None or "translate" in model_name.lower())
    if use_translate_config:
        # The translate model is driven by TranslationConfig only (no prompt / voice options)
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            translation_config=types.TranslationConfig(
                target_language_code=LANG_CODES[target],
                echo_target_language=False,  # same-language speech -> silence (no echo loop)
            ),
            **transcription,
        )
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(parts=[types.Part.from_text(text=build_instruction(target, history))]),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))
        ),
        **transcription,
    )


async def handle_live_interpreter_stream(
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
            "payload": {"message": "Error: GEMINI_API_KEY is not configured and no custom key provided."},
        })
        await client_ws.close(code=1008, reason="API key missing")
        return

    simultaneous = is_simultaneous()
    model = settings.SIMULTANEOUS_MODEL if simultaneous else settings.INTERPRETER_MODEL
    ai_client = create_genai_client(final_api_key)
    state = {
        "target": normalize_target(target),
        "voice": voice or "Aoede",
        "history": [],
        "source": None,
        "turns_completed": 0,
        "live_connected": False,
    }

    audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=500)
    text_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=20)
    client_disconnected = asyncio.Event()
    restart_session = asyncio.Event()
    fallback_lock = asyncio.Lock()

    # ── Sending helpers ───────────────────────────────────────────────────────
    async def send_json(payload: dict, broadcast: bool = True) -> None:
        if client_disconnected.is_set():
            return
        try:
            await client_ws.send_json(payload)
        except Exception:
            client_disconnected.set()
            return
        if broadcast:
            await manager.broadcast_json_except(payload, client_ws, room_id)

    async def send_audio(data: bytes) -> None:
        if client_disconnected.is_set() or is_silent(data):
            return
        try:
            await client_ws.send_bytes(data)
        except Exception:
            client_disconnected.set()
            return
        if room_id in manager.rooms and len(manager.rooms[room_id]) > 1:
            await manager.broadcast_bytes_except(data, client_ws, room_id)

    async def status(message: str) -> None:
        await send_json({"type": "status", "payload": {"message": message}}, broadcast=False)

    async def translate_typed_text(phrase: str, target_now: str) -> str:
        """Translate typed text across candidate Gemini models."""
        prompt = (f"Translate the following text into {target_now}. It may be Sinhala, Tamil or English. "
                  f"Output ONLY the {target_now} translation, nothing else.\n\n{phrase}")
        candidate_models = [
            settings.TRANSLATE_MODEL,
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite-preview",
            "gemini-flash-latest",
        ]
        last_err = None
        for m in candidate_models:
            try:
                response = await asyncio.to_thread(
                    ai_client.models.generate_content, model=m, contents=prompt
                )
                txt = (response.text or "").strip()
                if txt:
                    return txt
            except Exception as exc:
                last_err = exc
                continue
        if last_err:
            raise last_err
        return ""

    async def handle_typed_text_direct(phrase: str) -> None:
        target_now = state["target"]
        await send_json({"type": "transcription",
                         "payload": {"speaker": "user", "text": phrase, "detected_lang": detect_language(phrase)}})
        try:
            translation = await translate_typed_text(phrase, target_now)
        except Exception as err:
            logger.warning(f"Typed text translation failed: {err}")
            await status("Typed text could not be translated (Gemini request failed).")
            return
        await send_json({"type": "translation",
                         "payload": {"speaker": "ai", "text": translation, "target_lang": target_now}})
        tts_bytes = await synthesize_tts_audio(ai_client, translation, state["voice"])
        if tts_bytes:
            await send_audio(tts_bytes)
        state["turns_completed"] += 1
        await send_json({"type": "turn_complete", "payload": {"user_text": phrase, "ai_text": translation}})

    async def ensure_eof_translated(pcm_bytes: bytes, turns_before: int) -> None:
        """Guarantees that audio followed by audio_eof is transcribed, translated, and spoken
        even if the Live session has not connected or did not emit a response."""
        if state["live_connected"]:
            await asyncio.sleep(2.2)
        if client_disconnected.is_set() or state["turns_completed"] > turns_before:
            return
        if not pcm_bytes or is_silent(pcm_bytes):
            return
        async with fallback_lock:
            if client_disconnected.is_set() or state["turns_completed"] > turns_before:
                return
            target_now = state["target"]
            res_data = await transcribe_and_translate_wav(ai_client, pcm_to_wav(pcm_bytes), target_now)
            if not res_data or state["turns_completed"] > turns_before:
                return
            heard = (res_data.get("transcription") or "").strip()
            said = (res_data.get("translation") or "").strip()
            lang = res_data.get("detected_language") or detect_language(heard) or "Sinhala"
            if not heard and not said:
                return
            state["source"] = lang
            await send_json({"type": "lang_detected", "payload": {"source": lang, "target": target_now}})
            if heard:
                await send_json({"type": "transcription",
                                 "payload": {"speaker": "user", "text": heard, "detected_lang": lang}})
            if said:
                await send_json({"type": "translation",
                                 "payload": {"speaker": "ai", "text": said, "target_lang": target_now}})
                tts_bytes = await synthesize_tts_audio(ai_client, said, state["voice"])
                if tts_bytes:
                    await send_audio(tts_bytes)
            state["turns_completed"] += 1
            await send_json({"type": "turn_complete", "payload": {"user_text": heard, "ai_text": said}})

    # ── Task 1: read audio / text / commands from the client ────────────────
    async def read_client() -> None:
        client_pcm = bytearray()
        try:
            while not client_disconnected.is_set():
                msg = await client_ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes"):
                    chunk = msg["bytes"]
                    if not is_silent(chunk) or client_pcm:
                        client_pcm.extend(chunk)
                    if audio_queue.full():
                        audio_queue.get_nowait()  # drop the oldest frame, keep latency low
                    audio_queue.put_nowait(chunk)
                elif msg.get("text"):
                    raw = msg["text"].strip()
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        data = None
                    if not isinstance(data, dict):
                        if raw:
                            if simultaneous or not state["live_connected"]:
                                asyncio.create_task(handle_typed_text_direct(raw))
                            elif not text_queue.full():
                                text_queue.put_nowait(raw)  # plain text phrase to translate
                        continue
                    if data.get("type") == "set_target":
                        new_target = normalize_target(data.get("target", "Tamil"))
                        if new_target != state["target"]:
                            state["target"] = new_target
                            restart_session.set()
                        await status(f"Output language switched to {state['target']}")
                        await send_json({"type": "lang_detected",
                                         "payload": {"source": state["source"] or "Auto-Detect", "target": state["target"]}})
                    elif data.get("type") == "set_voice":
                        new_voice = data.get("voice") or "Aoede"
                        if new_voice != state["voice"]:
                            state["voice"] = new_voice
                            if not simultaneous:  # the translate model has a fixed voice
                                restart_session.set()
                        await status(f"Voice set to {state['voice']}")
                    elif data.get("type") == "audio_eof":
                        pcm_snapshot = bytes(client_pcm)
                        client_pcm.clear()
                        turns_before = state["turns_completed"]
                        if not audio_queue.full():
                            audio_queue.put_nowait(b"__AUDIO_EOF__")
                        if pcm_snapshot:
                            asyncio.create_task(ensure_eof_translated(pcm_snapshot, turns_before))
                    elif data.get("type") == "audio_file":
                        raw_audio = base64.b64decode(data.get("data_b64", ""))
                        mime = data.get("mime_type") or detect_audio_mime(raw_audio)
                        if raw_audio:
                            res_data = await transcribe_and_translate_wav(
                                ai_client, raw_audio, target_lang=state["target"], mime_type=mime
                            )
                            if res_data:
                                heard = (res_data.get("transcription") or "").strip()
                                said = (res_data.get("translation") or "").strip()
                                lang = res_data.get("detected_language") or detect_language(heard) or "Sinhala"
                                state["source"] = lang
                                await send_json({"type": "lang_detected", "payload": {"source": lang, "target": state["target"]}})
                                if heard:
                                    await send_json({"type": "transcription", "payload": {"speaker": "user", "text": heard, "detected_lang": lang}})
                                if said:
                                    await send_json({"type": "translation", "payload": {"speaker": "ai", "text": said, "target_lang": state["target"]}})
                                    tts_bytes = await synthesize_tts_audio(ai_client, said, state["voice"])
                                    if tts_bytes:
                                        await send_audio(tts_bytes)
                                state["turns_completed"] += 1
                                await send_json({"type": "turn_complete", "payload": {"user_text": heard, "ai_text": said}})
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            client_disconnected.set()

    async def run_chunked_fallback() -> None:
        """Continuous rolling-chunk fallback when Gemini Live WebSocket models are unavailable."""
        await status(f"Translator ready -> {state['target']}. Speak in Sinhala, Tamil or English.")
        await send_json({"type": "lang_detected",
                         "payload": {"source": state["source"] or "Auto-Detect", "target": state["target"]}})
        accumulated = bytearray()
        silence_bytes = 0
        silence_threshold = int(BYTES_PER_SECOND * PAUSE_SILENCE_SECONDS)
        while not client_disconnected.is_set():
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                if len(accumulated) >= MIN_CHUNK_BYTES:
                    slice_bytes = bytes(accumulated)
                    accumulated.clear()
                    silence_bytes = 0
                    turns_before = state["turns_completed"]
                    asyncio.create_task(ensure_eof_translated(slice_bytes, turns_before))
                continue
            if chunk == b"__AUDIO_EOF__":
                if len(accumulated) > 0:
                    slice_bytes = bytes(accumulated)
                    accumulated.clear()
                    silence_bytes = 0
                    turns_before = state["turns_completed"]
                    asyncio.create_task(ensure_eof_translated(slice_bytes, turns_before))
                continue
            if not is_silent(chunk):
                silence_bytes = 0
                accumulated.extend(chunk)
            elif len(accumulated) > 0:
                accumulated.extend(chunk)
                silence_bytes += len(chunk)
            if len(accumulated) >= MAX_CHUNK_BYTES or (len(accumulated) >= MIN_CHUNK_BYTES and silence_bytes >= silence_threshold):
                slice_bytes = bytes(accumulated)
                accumulated.clear()
                silence_bytes = 0
                turns_before = state["turns_completed"]
                asyncio.create_task(ensure_eof_translated(slice_bytes, turns_before))

    # ── Task 2: one Gemini Live session at a time (reconnects when needed) ───
    async def run_sessions() -> None:
        candidate_models = []
        for m in (
            model,
            settings.INTERPRETER_MODEL,
            "gemini-2.0-flash-live-001",
            "gemini-2.5-flash-native-audio-preview-12-2025",
            "gemini-live-2.5-flash-preview",
        ):
            if m and m not in candidate_models:
                candidate_models.append(m)

        model_idx = 0
        failures = 0
        while not client_disconnected.is_set():
            restart_session.clear()
            target_now = state["target"]
            active_model = candidate_models[model_idx % len(candidate_models)]
            config = build_config(target_now, state["voice"], state["history"], model_name=active_model)
            try:
                async with ai_client.aio.live.connect(model=active_model, config=config) as session:
                    failures = 0
                    state["live_connected"] = True
                    mode = "simultaneous" if ("translate" in active_model.lower() and simultaneous) else "turn-based"
                    logger.info(f"Live interpreter session open (room={room_id}, model={active_model}, {mode}, target={target_now})")
                    await status(f"Live interpreter ready [{active_model}] -> {target_now}. Speak in Sinhala, Tamil or English.")
                    await send_json({"type": "lang_detected",
                                     "payload": {"source": state["source"] or "Auto-Detect", "target": target_now}})
                    await run_one_session(session, target_now)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                state["live_connected"] = False
                if client_disconnected.is_set():
                    return
                failures += 1
                model_idx += 1
                text = str(err)
                logger.warning(f"Live interpreter session error ({failures}/{ len(candidate_models)}, model={active_model}): {text}")
                if "RESOURCE_EXHAUSTED" in text or "429" in text or "quota" in text.lower():
                    await status("Gemini quota exceeded for this API key. Wait a while or use a key with billing enabled.")
                    return
                if failures >= len(candidate_models):
                    logger.info("Switching to chunked audio translation fallback.")
                    await run_chunked_fallback()
                    return
                await asyncio.sleep(0.3)

    async def run_one_session(session, target_now: str) -> None:
        """Pump audio/text into the session and results back to the client until
        the client leaves, the target/voice changes, or the session ends."""
        turn = {
            "heard": "",
            "said": "",
            "last_output": 0.0,
            "pcm": bytearray(),
            "audio_sent": False,
            "turns_completed": 0,
        }
        # Loops also check this flag: on Python 3.11, asyncio.wait_for() can swallow a
        # cancel() that arrives together with a new audio packet, which would leave the
        # task running and block the switch to a new session forever.
        stopping = asyncio.Event()

        async def finish_turn() -> None:
            heard, said = turn["heard"].strip(), turn["said"].strip()
            had_audio = turn["audio_sent"]
            turn["heard"], turn["said"] = "", ""
            turn["pcm"].clear()
            turn["audio_sent"] = False
            turn["turns_completed"] += 1
            state["turns_completed"] += 1
            if heard or said:
                logger.info(f"[{room_id}] {state['source']} -> {target_now}: {heard!r} => {said!r}")
                if heard:
                    state["history"].append({"speaker": "speaker", "text": heard})
                if said:
                    state["history"].append({"speaker": "interpreter", "text": said})
                state["history"] = state["history"][-HISTORY_TURNS * 2:]
                if said and not had_audio:
                    tts_bytes = await synthesize_tts_audio(ai_client, said, state["voice"])
                    if tts_bytes:
                        await send_audio(tts_bytes)
            await send_json({"type": "turn_complete", "payload": {"user_text": heard, "ai_text": said}})

        async def fallback_process_pcm(pcm_bytes: bytes) -> None:
            """If Gemini Live did not emit a translation after audio_eof, transcribe & translate the WAV directly."""
            await asyncio.sleep(2.5)
            if stopping.is_set() or turn["turns_completed"] > 0 or turn["said"].strip():
                return
            if not pcm_bytes or is_silent(pcm_bytes):
                return
            res_data = await transcribe_and_translate_wav(ai_client, pcm_to_wav(pcm_bytes), target_now)
            if not res_data or turn["turns_completed"] > 0 or turn["said"].strip():
                return
            heard = (res_data.get("transcription") or "").strip()
            said = (res_data.get("translation") or "").strip()
            lang = res_data.get("detected_language") or detect_language(heard) or "Sinhala"
            if not heard and not said:
                return
            state["source"] = lang
            await send_json({"type": "lang_detected", "payload": {"source": lang, "target": target_now}})
            if heard:
                await send_json({"type": "transcription",
                                 "payload": {"speaker": "user", "text": heard, "detected_lang": lang}})
            if said:
                await send_json({"type": "translation",
                                 "payload": {"speaker": "ai", "text": said, "target_lang": target_now}})
                tts_bytes = await synthesize_tts_audio(ai_client, said, state["voice"])
                if tts_bytes:
                    await send_audio(tts_bytes)
            turn["turns_completed"] += 1
            await send_json({"type": "turn_complete", "payload": {"user_text": heard, "ai_text": said}})

        async def handle_typed_text(phrase: str) -> None:
            await send_json({"type": "transcription",
                             "payload": {"speaker": "user", "text": phrase, "detected_lang": detect_language(phrase)}})
            if simultaneous:
                try:
                    translation = await translate_typed_text(phrase, target_now)
                except Exception as err:
                    logger.warning(f"Typed text translation failed: {err}")
                    await status("Typed text could not be translated (Gemini request failed).")
                    return
                await send_json({"type": "translation",
                                 "payload": {"speaker": "ai", "text": translation, "target_lang": target_now}})
                tts_bytes = await synthesize_tts_audio(ai_client, translation, state["voice"])
                if tts_bytes:
                    await send_audio(tts_bytes)
                await send_json({"type": "turn_complete", "payload": {"user_text": phrase, "ai_text": translation}})
            else:
                turn["heard"] = phrase
                await session.send_client_content(
                    turns=[types.Content(role="user", parts=[types.Part.from_text(text=phrase)])],
                    turn_complete=True,
                )

        async def forward_input() -> None:
            # A short lead-in of silence lets Gemini catch the first word
            for _ in range(LEAD_IN_FRAMES):
                await session.send_realtime_input(
                    audio=types.Blob(data=SILENCE_FRAME, mime_type=f"audio/pcm;rate={SAMPLE_RATE}")
                )
            last_audio = 0.0
            while not stopping.is_set():
                if not text_queue.empty():
                    asyncio.create_task(handle_typed_text(text_queue.get_nowait()))
                try:
                    chunk = await asyncio.wait_for(audio_queue.get(), timeout=FRAME_SECONDS)
                    if chunk == b"__AUDIO_EOF__":
                        pcm_snapshot = bytes(turn["pcm"])
                        for _ in range(10):
                            await session.send_realtime_input(
                                audio=types.Blob(data=SILENCE_FRAME, mime_type=f"audio/pcm;rate={SAMPLE_RATE}")
                            )
                        if pcm_snapshot:
                            asyncio.create_task(fallback_process_pcm(pcm_snapshot))
                        continue
                    last_audio = time.monotonic()
                    if not is_silent(chunk) or turn["pcm"]:
                        turn["pcm"].extend(chunk)
                except asyncio.TimeoutError:
                    gap = time.monotonic() - last_audio
                    if gap < SILENCE_GAP_SECONDS or gap > SILENCE_GAP_SECONDS + SILENCE_AFTER_SPEECH_SECONDS:
                        continue
                    chunk = SILENCE_FRAME  # the speaker paused: let Gemini hear it and finish the sentence
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={SAMPLE_RATE}")
                )

        async def sentence_watchdog() -> None:
            """Simultaneous mode: close a sentence once the translation has gone quiet."""
            while not stopping.is_set():
                await asyncio.sleep(0.2)
                if turn["said"].strip() and time.monotonic() - turn["last_output"] > SENTENCE_IDLE_SECONDS:
                    await finish_turn()

        async def receive_output() -> None:
            # session.receive() ends after every completed turn, so keep calling it.
            # A real disconnect from Gemini raises an exception instead.
            while True:
                received = 0
                async for response in session.receive():
                    received += 1
                    await handle_response(response)
                if received == 0:  # stream ended without data: Gemini closed the session
                    raise ConnectionError("Gemini Live session closed by server")

        async def handle_response(response) -> None:
            sc = response.server_content
            if not sc:
                return

            if sc.input_transcription and sc.input_transcription.text:
                turn["heard"] += sc.input_transcription.text
                heard = turn["heard"].strip()
                lang = detect_language(heard)
                if lang and lang != state["source"]:
                    state["source"] = lang
                    await send_json({"type": "lang_detected", "payload": {"source": lang, "target": target_now}})
                if heard:
                    await send_json({"type": "transcription",
                                     "payload": {"speaker": "user", "text": heard, "detected_lang": lang}})

            if sc.output_transcription and sc.output_transcription.text:
                turn["said"] += sc.output_transcription.text
                turn["last_output"] = time.monotonic()
                said = turn["said"].strip()
                if said:
                    await send_json({"type": "translation",
                                     "payload": {"speaker": "ai", "text": said, "target_lang": target_now}})

            if sc.model_turn:
                for part in sc.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        turn["audio_sent"] = True
                        await send_audio(part.inline_data.data)

            sentence_done = simultaneous and turn["said"].rstrip().endswith(SENTENCE_END)
            if sc.turn_complete or sc.interrupted or sentence_done:
                await finish_turn()

        workers = [forward_input(), receive_output()]
        if simultaneous:
            workers.append(sentence_watchdog())
        tasks = [asyncio.create_task(w) for w in workers]
        stop_signals = [asyncio.create_task(client_disconnected.wait()),
                        asyncio.create_task(restart_session.wait())]
        try:
            done, _ = await asyncio.wait(tasks + stop_signals, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stopping.set()
            for t in tasks + stop_signals:
                t.cancel()
            await asyncio.gather(*tasks, *stop_signals, return_exceptions=True)
        if turn["heard"].strip() or turn["said"].strip():
            await finish_turn()  # don't lose a half-finished sentence on reconnect
        for t in done:
            if t in tasks and not t.cancelled() and t.exception():
                raise t.exception()

    reader = asyncio.create_task(read_client())
    sessions = asyncio.create_task(run_sessions())
    try:
        await asyncio.wait([reader, sessions], return_when=asyncio.FIRST_COMPLETED)
    finally:
        client_disconnected.set()
        for t in (reader, sessions):
            t.cancel()
        await asyncio.gather(reader, sessions, return_exceptions=True)
        logger.info(f"Live interpreter closed for room: {room_id}")
