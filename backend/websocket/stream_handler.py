import asyncio
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from backend.config.settings import settings

logger = logging.getLogger("backend")


def _detect_script(text: str) -> str | None:
    """Detect whether text is predominantly Sinhala, Tamil, or English."""
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
    if si / total >= 0.3:
        return "Sinhala"
    if ta / total >= 0.3:
        return "Tamil"
    if en / total >= 0.5:
        return "English"
    return None


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

    # BCP-47 language codes
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
    target_code = language_map.get(target, "ta")
    source_code = language_map.get(source, "si")

    is_translate_model = "translate" in settings.GEMINI_MODEL.lower()

    if is_translate_model:
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
                    silence_duration_ms=650,
                )
            ),
        )
    else:
        system_prompt = (
            f"You are SinTam, a real-time speech-to-speech translator between Sinhala, Tamil, and English. "
            f"- If the user speaks Sinhala, translate immediately into natural spoken Tamil. "
            f"- If the user speaks Tamil, translate immediately into natural spoken Sinhala. "
            f"- If the user speaks English or any other language, translate into {target}. "
            f"Speak out loud in the target language and output ONLY the translated text. "
            f"Do NOT output English explanations, reasoning, thoughts, markdown, or notes. "
            f"Do NOT repeat the input speech. Direct speech translation only."
        )
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
                parts=[types.Part.from_text(text=system_prompt)]
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                    silence_duration_ms=650,
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
                "type": "lang_detected",
                "payload": {"source": source, "target": target}
            })
            await client_ws.send_json({
                "type": "status",
                "payload": {
                    "message": (
                        f"Connected [{settings.GEMINI_MODEL}]: "
                        f"{source} ↔ {target}. Start speaking!"
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
                                            model="gemini-3.6-flash",
                                            contents=prompt,
                                            config=types.GenerateContentConfig(
                                                system_instruction="You are a direct translator. Output strictly the translated text and nothing else."
                                            ),
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
                try:
                    current_user_transcript = ""
                    current_ai_translation = ""
                    turn_has_audio = False

                    async for response in session.receive():
                        if not response.server_content:
                            continue

                        sc = response.server_content

                        # Spoken source text (what the user said)
                        if sc.input_transcription and sc.input_transcription.text:
                            delta = sc.input_transcription.text
                            current_user_transcript += delta
                            detected = _detect_script(current_user_transcript)
                            if detected:
                                detected_target = "Sinhala" if detected == "Tamil" else "Tamil"
                                await client_ws.send_json({
                                    "type": "lang_detected",
                                    "payload": {
                                        "source": detected,
                                        "target": detected_target,
                                    },
                                })
                            await client_ws.send_json({
                                "type": "transcription",
                                "payload": {
                                    "speaker": "user",
                                    "text": current_user_transcript.strip(),
                                    "delta": delta,
                                },
                            })

                        # Translated output text from live voice synthesis
                        if sc.output_transcription and sc.output_transcription.text:
                            delta = sc.output_transcription.text
                            current_ai_translation += delta
                            await client_ws.send_json({
                                "type": "translation",
                                "payload": {
                                    "speaker": "ai",
                                    "text": current_ai_translation.strip(),
                                    "delta": delta,
                                },
                            })

                        # Audio bytes from model turn
                        if sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    turn_has_audio = True
                                    await client_ws.send_bytes(part.inline_data.data)

                        if sc.turn_complete:
                            await client_ws.send_json({
                                "type": "turn_complete",
                                "payload": {
                                    "user_text": current_user_transcript.strip(),
                                    "ai_text": current_ai_translation.strip(),
                                    "has_audio": turn_has_audio,
                                },
                            })
                            current_user_transcript = ""
                            current_ai_translation = ""
                            turn_has_audio = False

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
