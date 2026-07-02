import asyncio
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from backend.config.settings import settings
from backend.websocket.turn_buffer import DeferredTurnOutput

logger = logging.getLogger("backend")


async def handle_translation_stream(
    client_ws: WebSocket,
    source: str = "Sinhala",
    target: str = "Tamil",
    voice: str = "Aoede",
):
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not configured.")
        await client_ws.send_json({
            "type": "status",
            "payload": {"message": "Error: GEMINI_API_KEY is not configured on the server."}
        })
        await client_ws.close(code=1008, reason="API key missing")
        return

    ai_client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # BCP-47 language codes for transcription hints
    language_map = {
        "Sinhala": "si",
        "Tamil":   "ta",
        "English": "en",
        "Korean":  "ko",
        "Spanish": "es",
        "Japanese": "ja",
        "Chinese": "zh",
        "French":  "fr",
        "German":  "de",
    }
    target_code = language_map.get(target, "en")
    source_code = language_map.get(source, "en")  # noqa: F841 – kept for future use

    is_translate_model = "translate" in settings.GEMINI_MODEL.lower()

    if is_translate_model:
        # Dedicated translation model: TranslationConfig drives the output language.
        # Do NOT add system_instruction, speech_config, or voice_config — these are
        # unsupported by the translate model and cause silent failures / wrong language.
        config = types.LiveConnectConfig(
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
                    silence_duration_ms=600,
                )
            ),
        )
    else:
        # Standard Live model: use system_instruction + speech/voice config.
        config = types.LiveConnectConfig(
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
                        text=(
                            f"You are SinTam, a real-time speech-to-speech translator. "
                            f"Translate spoken/written {source} into {target}. "
                            f"Output ONLY the translated {target} text. "
                            f"Do NOT output English unless {target} is English. "
                            f"Do NOT repeat the source {source} text. "
                            f"No preambles, explanations, or filler — translation only."
                        )
                    )
                ]
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

    logger.info(
        f"Connecting to Gemini Live [{settings.GEMINI_MODEL}] "
        f"{source}({source_code}) -> {target}({target_code}), voice={voice}"
    )

    try:
        async with ai_client.aio.live.connect(
            model=settings.GEMINI_MODEL, config=config
        ) as session:
            logger.info("Gemini Live session established.")
            await client_ws.send_json({
                "type": "status",
                "payload": {
                    "message": (
                        f"Connected [{settings.GEMINI_MODEL}]: "
                        f"{source} → {target}. Start speaking!"
                    )
                }
            })

            # ── Client -> Gemini ──────────────────────────────────────────────
            async def client_to_gemini():
                try:
                    while True:
                        message = await client_ws.receive()

                        if "bytes" in message and message["bytes"]:
                            await session.send_realtime_input(
                                audio=types.Blob(
                                    data=message["bytes"],
                                    mime_type="audio/pcm;rate=16000",
                                )
                            )

                        elif "text" in message and message["text"]:
                            raw = message["text"]
                            try:
                                cmd = json.loads(raw)
                                if cmd.get("type") == "update_config":
                                    # Config updates handled at connection time;
                                    # acknowledge silently.
                                    pass
                            except json.JSONDecodeError:
                                # Plain text message — translate it
                                if is_translate_model:
                                    # Translate model doesn't accept client content turns;
                                    # fall back to a quick REST call.
                                    try:
                                        prompt = (
                                            f"Translate the following from {source} to {target}. "
                                            f"Output ONLY the translated text:\n{raw}"
                                        )
                                        rest_response = ai_client.models.generate_content(
                                            model="gemini-2.0-flash",
                                            contents=prompt,
                                        )
                                        translation = (rest_response.text or "").strip()
                                        if translation:
                                            await client_ws.send_json({
                                                "type": "translation",
                                                "payload": {"speaker": "ai", "text": translation},
                                            })
                                            await client_ws.send_json({
                                                "type": "turn_complete",
                                                "payload": {},
                                            })
                                    except Exception as text_err:
                                        logger.error(f"REST text translation error: {text_err}")
                                else:
                                    # Standard live model accepts text turns
                                    content = types.Content(
                                        role="user",
                                        parts=[types.Part.from_text(text=raw)],
                                    )
                                    await session.send_client_content(
                                        turns=[content], turn_complete=True
                                    )

                except (WebSocketDisconnect, RuntimeError):
                    logger.info("Client disconnected in client_to_gemini.")
                except asyncio.CancelledError:
                    pass
                except Exception as ex:
                    logger.error(f"client_to_gemini error: {ex}")
                    raise

            # ── Gemini -> Client ──────────────────────────────────────────────
            async def gemini_to_client():
                deferred_turn = DeferredTurnOutput()
                try:
                    async for response in session.receive():
                        if not response.server_content:
                            continue

                        sc = response.server_content

                        # Spoken source text (what the user said)
                        if sc.input_transcription and sc.input_transcription.text:
                            await client_ws.send_json({
                                "type": "transcription",
                                "payload": {
                                    "speaker": "user",
                                    "text": sc.input_transcription.text,
                                },
                            })

                        # Translated output text
                        if sc.output_transcription and sc.output_transcription.text:
                            deferred_turn.add_translation(sc.output_transcription.text)

                        # Audio bytes + text from model turn
                        if sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    deferred_turn.add_audio(part.inline_data.data)
                                # Only emit text from model_turn for non-translate model
                                # (translate model already emits via output_transcription)
                                if part.text and not is_translate_model:
                                    deferred_turn.add_translation(part.text)

                        if sc.turn_complete:
                            translation = deferred_turn.translation_text()
                            if translation:
                                await client_ws.send_json({
                                    "type": "translation",
                                    "payload": {
                                        "speaker": "ai",
                                        "text": translation,
                                    },
                                })

                            for audio_chunk in deferred_turn.audio_chunks:
                                await client_ws.send_bytes(audio_chunk)

                            deferred_turn.clear()
                            await client_ws.send_json({
                                "type": "turn_complete",
                                "payload": {},
                            })

                except asyncio.CancelledError:
                    pass
                except Exception as ex:
                    logger.error(f"gemini_to_client error: {ex}")
                    raise

            client_task = asyncio.create_task(client_to_gemini())
            gemini_task = asyncio.create_task(gemini_to_client())

            done, pending = await asyncio.wait(
                [client_task, gemini_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    except WebSocketDisconnect:
        logger.info("Client browser connection closed.")
    except Exception as e:
        logger.error(f"Gemini Live session error: {e}")
        try:
            await client_ws.send_json({
                "type": "status",
                "payload": {"message": f"Server error: {e}"},
            })
        except Exception:
            pass
