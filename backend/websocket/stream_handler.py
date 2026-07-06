import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from backend.config.settings import settings
from backend.websocket.connection_manager import manager

logger = logging.getLogger("backend")


async def handle_translation_stream(
    client_ws: WebSocket,
    source: str,
    target: str,
    voice: str,
    group_id: int = None
):
    """
    Manages the bidirectional audio stream between the client and Google Gemini Live API.
    Uses the gemini-3.5-live-translate-preview model for real-time speech-to-speech translation.

    Per official docs: this model is AUDIO-only input, supports ONLY translation_config,
    no system_instruction, no speech_config, no tools. It uses continuous stream processing
    (not turn-based), so realtime_input_config with VAD is not applicable.
    """
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not configured in settings.")
        await manager.send_json_message({
            "type": "status",
            "payload": {"message": "Error: GEMINI_API_KEY is not configured on the server."}
        }, client_ws)
        await client_ws.close(code=1008, reason="API key missing")
        return

    # Build client — the Python SDK uses v1beta by default which supports the translate model
    ai_client = genai.Client(api_key=settings.GEMINI_API_KEY)

    language_map = {
        "Sinhala": "si",
        "Tamil": "ta",
        "English": "en",
        "Korean": "ko",
        "Spanish": "es",
        "Japanese": "ja",
        "Chinese": "zh",
        "French": "fr",
        "German": "de"
    }
    target_code = language_map.get(target, "ta")
    source_code = language_map.get(source, "si")

    # Minimal config as per official Gemini Live Translate docs.
    # The translate model does NOT support: speech_config, system_instruction,
    # realtime_input_config, or tools. Only use the fields shown below.
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        translation_config=types.TranslationConfig(
            target_language_code=target_code,
            echo_target_language=False,  # Stay silent if speaker is already speaking the target language
        ),
    )

    logger.info(f"Connecting to Gemini Live Translate API: {source}({source_code}) → {target}({target_code})")

    try:
        async with ai_client.aio.live.connect(model=settings.GEMINI_MODEL, config=config) as session:
            logger.info("Successfully connected to Gemini Live Translate session.")
            await client_ws.send_json({
                "type": "status",
                "payload": {"message": f"Connected. Translating {source} → {target}. Start speaking now..."}
            })

            async def client_to_gemini():
                """Forward raw PCM audio bytes from browser WebSocket to Gemini."""
                try:
                    while True:
                        message = await client_ws.receive()
                        if "bytes" in message:
                            data = message["bytes"]
                            # Send raw PCM audio — the translate model ONLY accepts audio input
                            await session.send_realtime_input(
                                audio=types.Blob(
                                    data=data,
                                    mime_type="audio/pcm;rate=16000"
                                )
                            )
                        elif "text" in message:
                            # Text input is NOT supported by the translate model.
                            # Silently ignore any text messages from the client.
                            logger.debug("Ignoring text message (translate model only accepts audio)")
                except (WebSocketDisconnect, RuntimeError):
                    logger.info("Client WebSocket disconnected inside client_to_gemini.")
                except asyncio.CancelledError:
                    pass
                except Exception as ex:
                    logger.error(f"Error in client_to_gemini: {ex}")
                    raise

            async def gemini_to_client():
                """Forward Gemini responses back to the browser WebSocket."""
                try:
                    async for response in session.receive():
                        if response.server_content:
                            sc = response.server_content

                            # Input transcription — user's spoken words in source language
                            if sc.input_transcription and sc.input_transcription.text:
                                await client_ws.send_json({
                                    "type": "transcription",
                                    "payload": {
                                        "speaker": "user",
                                        "text": sc.input_transcription.text
                                    }
                                })

                            # Output transcription — translated text in target language
                            if sc.output_transcription and sc.output_transcription.text:
                                await client_ws.send_json({
                                    "type": "translation",
                                    "payload": {
                                        "speaker": "ai",
                                        "text": sc.output_transcription.text
                                    }
                                })

                            # Translated audio chunks — raw PCM at 24kHz
                            if sc.model_turn:
                                for part in sc.model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        await client_ws.send_bytes(part.inline_data.data)

                            # Turn complete signal
                            if sc.turn_complete:
                                await client_ws.send_json({
                                    "type": "turn_complete",
                                    "payload": {}
                                })

                except asyncio.CancelledError:
                    pass
                except Exception as ex:
                    logger.error(f"Error in gemini_to_client: {ex}")
                    raise

            client_task = asyncio.create_task(client_to_gemini())
            gemini_task = asyncio.create_task(gemini_to_client())

            done, pending = await asyncio.wait(
                [client_task, gemini_task],
                return_when=asyncio.FIRST_COMPLETED
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
        logger.error(f"Error in Gemini translation loop: {str(e)}")
        try:
            await client_ws.send_json({
                "type": "status",
                "payload": {"message": f"Server connection error: {str(e)}"}
            })
        except Exception:
            pass