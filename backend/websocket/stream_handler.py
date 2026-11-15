import asyncio
import base64
import json
import logging
import time
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from backend.config.settings import settings
from backend.websocket.continuous_stream_handler import (
    create_genai_client,
    detect_audio_mime,
    is_gemini_api_key,
    pcm_to_wav,
    synthesize_tts_audio,
    transcribe_and_translate_wav,
)
from backend.websocket.live_interpreter_handler import (
    SENTENCE_END,
    SENTENCE_IDLE_SECONDS,
    SILENCE_FRAME,
    is_silent,
)

logger = logging.getLogger("backend")


async def handle_translation_stream(
    client_ws: WebSocket,
    source: str = "Sinhala",
    target: str = "Tamil",
    voice: str = "Aoede",
    api_key: str | None = None,
):
    final_api_key = api_key if is_gemini_api_key(api_key) else settings.GEMINI_API_KEY
    if not final_api_key:
        logger.error("GEMINI_API_KEY is not configured and no custom key provided.")
        await client_ws.send_json({
            "type": "status",
            "payload": {"message": "Error: GEMINI_API_KEY is not configured on the server and no custom api_key was provided."}
        })
        await client_ws.close(code=1008, reason="API key missing")
        return

    ai_client = create_genai_client(final_api_key)

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
                    silence_duration_ms=200,
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
                            f"You are an expert call-center translator for Sri Lanka. "
                            f"Translate spoken/written {source} into {target} and vice versa. "
                            f"Keep the tone professional but natural. "
                            f"CRITICAL RULES: "
                            f"1. Handle Singlish (Sinhala+English) and Tanglish (Tamil+English) gracefully. If the caller uses English loanwords (e.g., 'credit card', 'balance', 'loan'), translate them accurately into the equivalent natural {target} business term, or keep the loanword if it is standard industry practice. "
                            f"2. Output ONLY the translated {target} text. "
                            f"3. Do NOT output English unless {target} is English. "
                            f"4. Do NOT repeat the source text. No preambles or explanations."
                        )
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

            turn = {
                "heard": "",
                "said": "",
                "last_output": 0.0,
                "pcm": bytearray(),
                "audio_sent": False,
                "turns_completed": 0,
            }
            stopping = asyncio.Event()

            async def finish_turn() -> None:
                heard, said = turn["heard"].strip(), turn["said"].strip()
                had_audio = turn["audio_sent"]
                turn["heard"], turn["said"] = "", ""
                turn["pcm"].clear()
                turn["audio_sent"] = False
                turn["turns_completed"] += 1
                if said and not had_audio:
                    tts_bytes = await synthesize_tts_audio(ai_client, said, voice)
                    if tts_bytes:
                        await client_ws.send_bytes(tts_bytes)
                await client_ws.send_json({
                    "type": "turn_complete",
                    "payload": {"user_text": heard, "ai_text": said},
                })

            async def fallback_process_pcm(pcm_bytes: bytes) -> None:
                await asyncio.sleep(2.5)
                if stopping.is_set() or turn["turns_completed"] > 0 or turn["said"].strip():
                    return
                if not pcm_bytes or is_silent(pcm_bytes):
                    return
                res_data = await transcribe_and_translate_wav(
                    ai_client, pcm_to_wav(pcm_bytes), target, source
                )
                if not res_data or turn["turns_completed"] > 0 or turn["said"].strip():
                    return
                heard = (res_data.get("transcription") or "").strip()
                said = (res_data.get("translation") or "").strip()
                if not heard and not said:
                    return
                if heard:
                    await client_ws.send_json({
                        "type": "transcription",
                        "payload": {"speaker": "user", "text": heard, "detected_lang": source},
                    })
                if said:
                    await client_ws.send_json({
                        "type": "translation",
                        "payload": {"speaker": "ai", "text": said, "target_lang": target},
                    })
                    tts_bytes = await synthesize_tts_audio(ai_client, said, voice)
                    if tts_bytes:
                        await client_ws.send_bytes(tts_bytes)
                turn["turns_completed"] += 1
                await client_ws.send_json({
                    "type": "turn_complete",
                    "payload": {"user_text": heard, "ai_text": said},
                })

            # ── Client -> Gemini ──────────────────────────────────────────────
            async def client_to_gemini():
                try:
                    while not stopping.is_set():
                        message = await client_ws.receive()
                        if message.get("type") == "websocket.disconnect":
                            break

                        if "bytes" in message and message["bytes"]:
                            chunk = message["bytes"]
                            if not is_silent(chunk) or turn["pcm"]:
                                turn["pcm"].extend(chunk)
                            await session.send_realtime_input(
                                audio=types.Blob(
                                    data=chunk,
                                    mime_type="audio/pcm;rate=16000",
                                )
                            )

                        elif "text" in message and message["text"]:
                            raw = message["text"]
                            try:
                                cmd = json.loads(raw)
                                if isinstance(cmd, dict):
                                    if cmd.get("type") == "update_config":
                                        pass
                                    elif cmd.get("type") == "audio_eof":
                                        pcm_snapshot = bytes(turn["pcm"])
                                        for _ in range(10):
                                            await session.send_realtime_input(
                                                audio=types.Blob(
                                                    data=SILENCE_FRAME,
                                                    mime_type="audio/pcm;rate=16000",
                                                )
                                            )
                                        if pcm_snapshot:
                                            asyncio.create_task(fallback_process_pcm(pcm_snapshot))
                                    elif cmd.get("type") == "audio_file":
                                        raw_audio = base64.b64decode(cmd.get("data_b64", ""))
                                        mime = cmd.get("mime_type") or detect_audio_mime(raw_audio)
                                        if raw_audio:
                                            res_data = await transcribe_and_translate_wav(
                                                ai_client, raw_audio, target_lang=target, source_lang=source, mime_type=mime
                                            )
                                            if res_data:
                                                heard = (res_data.get("transcription") or "").strip()
                                                said = (res_data.get("translation") or "").strip()
                                                if heard:
                                                    await client_ws.send_json({
                                                        "type": "transcription",
                                                        "payload": {"speaker": "user", "text": heard, "detected_lang": source},
                                                    })
                                                if said:
                                                    await client_ws.send_json({
                                                        "type": "translation",
                                                        "payload": {"speaker": "ai", "text": said, "target_lang": target},
                                                    })
                                                    tts_bytes = await synthesize_tts_audio(ai_client, said, voice)
                                                    if tts_bytes:
                                                        await client_ws.send_bytes(tts_bytes)
                                                turn["turns_completed"] += 1
                                                await client_ws.send_json({
                                                    "type": "turn_complete",
                                                    "payload": {"user_text": heard, "ai_text": said},
                                                })
                                    continue
                            except json.JSONDecodeError:
                                pass

                            # Plain text message — translate it
                            if is_translate_model:
                                try:
                                    prompt = (
                                        f"Translate the following from {source} to {target}. "
                                        f"Output ONLY the translated text:\n{raw}"
                                    )
                                    rest_response = await asyncio.to_thread(
                                        ai_client.models.generate_content,
                                        model=settings.TRANSLATE_MODEL,
                                        contents=prompt,
                                    )
                                    translation = (rest_response.text or "").strip()
                                    if translation:
                                        await client_ws.send_json({
                                            "type": "transcription",
                                            "payload": {"speaker": "user", "text": raw, "detected_lang": source},
                                        })
                                        await client_ws.send_json({
                                            "type": "translation",
                                            "payload": {"speaker": "ai", "text": translation, "target_lang": target},
                                        })
                                        tts_bytes = await synthesize_tts_audio(ai_client, translation, voice)
                                        if tts_bytes:
                                            await client_ws.send_bytes(tts_bytes)
                                        await client_ws.send_json({
                                            "type": "turn_complete",
                                            "payload": {"user_text": raw, "ai_text": translation},
                                        })
                                except Exception as text_err:
                                    logger.error(f"REST text translation error: {text_err}")
                            else:
                                turn["heard"] = raw
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
                finally:
                    stopping.set()

            async def sentence_watchdog():
                while not stopping.is_set():
                    await asyncio.sleep(0.2)
                    if turn["said"].strip() and time.monotonic() - turn["last_output"] > SENTENCE_IDLE_SECONDS:
                        await finish_turn()

            # ── Gemini -> Client ──────────────────────────────────────────────
            async def gemini_to_client():
                try:
                    while not stopping.is_set():
                        received = 0
                        async for response in session.receive():
                            received += 1
                            if not response.server_content:
                                continue

                            sc = response.server_content

                            # Spoken source text (what the user said)
                            if sc.input_transcription and sc.input_transcription.text:
                                turn["heard"] += sc.input_transcription.text
                                heard = turn["heard"].strip()
                                if heard:
                                    await client_ws.send_json({
                                        "type": "transcription",
                                        "payload": {
                                            "speaker": "user",
                                            "text": heard,
                                            "detected_lang": source,
                                        },
                                    })

                            # Translated output text
                            if sc.output_transcription and sc.output_transcription.text:
                                turn["said"] += sc.output_transcription.text
                                turn["last_output"] = time.monotonic()
                                said = turn["said"].strip()
                                if said:
                                    await client_ws.send_json({
                                        "type": "translation",
                                        "payload": {
                                            "speaker": "ai",
                                            "text": said,
                                            "target_lang": target,
                                        },
                                    })

                            # Audio bytes + text from model turn
                            if sc.model_turn:
                                for part in sc.model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        turn["audio_sent"] = True
                                        await client_ws.send_bytes(part.inline_data.data)
                                    # Only emit text from model_turn for non-translate model
                                    # (translate model already emits via output_transcription)
                                    if part.text and not is_translate_model:
                                        turn["said"] += part.text
                                        turn["last_output"] = time.monotonic()
                                        await client_ws.send_json({
                                            "type": "translation",
                                            "payload": {
                                                "speaker": "ai",
                                                "text": turn["said"].strip(),
                                                "target_lang": target,
                                            },
                                        })

                            sentence_done = is_translate_model and turn["said"].rstrip().endswith(SENTENCE_END)
                            if sc.turn_complete or sc.interrupted or sentence_done:
                                await finish_turn()

                        if received == 0:
                            break

                except asyncio.CancelledError:
                    pass
                except Exception as ex:
                    logger.error(f"gemini_to_client error: {ex}")
                    raise
                finally:
                    stopping.set()

            workers = [
                asyncio.create_task(client_to_gemini()),
                asyncio.create_task(gemini_to_client()),
            ]
            if is_translate_model:
                workers.append(asyncio.create_task(sentence_watchdog()))

            done, pending = await asyncio.wait(
                workers,
                return_when=asyncio.FIRST_COMPLETED,
            )
            stopping.set()

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
