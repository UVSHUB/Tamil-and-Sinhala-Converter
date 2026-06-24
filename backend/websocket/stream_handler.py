import asyncio
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from backend.config.settings import settings

logger = logging.getLogger("backend")

async def handle_translation_stream(client_ws: WebSocket, source: str = "Sinhala", target: str = "Tamil"):
    """
    Handles a translation session for a client WebSocket:
    1. Establishes connection to the Google Gemini Live API.
    2. Runs concurrent async loops:
       - client_to_gemini: Streams client PCM audio frames to Gemini Live.
       - gemini_to_client: Receives synthesized audio + translation texts from Gemini and forwards to browser.
    """
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not configured in settings.")
        await client_ws.send_json({
            "type": "status",
            "payload": {"message": "Error: GEMINI_API_KEY is not configured on the server."}
        })
        await client_ws.close(code=1008, reason="API key missing")
        return

    # Initialize Google GenAI client
    ai_client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Map target language to its BCP-47 code for Gemini Live Translation model
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

    # Configure the Gemini Live session parameters for the Translation model
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        translation_config=types.TranslationConfig(
            target_language_code=target_code,
            echo_target_language=True
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
                silence_duration_ms=300,
            )
        )
    )

    logger.info(f"Connecting to Gemini Live API using model: {settings.GEMINI_MODEL}...")

    try:
        async with ai_client.aio.live.connect(model=settings.GEMINI_MODEL, config=config) as session:
            logger.info("Successfully connected to Gemini Live API session.")
            await client_ws.send_json({
                "type": "status",
                "payload": {"message": "Connected to Gemini Live API. Start speaking now..."}
            })

            # Loop 1: Client WebSocket -> Gemini Live Session
            async def client_to_gemini():
                try:
                    while True:
                        message = await client_ws.receive()
                        if "bytes" in message:
                            data = message["bytes"]
                            # Stream raw 16-bit 16kHz PCM audio chunk to Gemini
                            await session.send_realtime_input(
                                media=types.Blob(
                                    data=data,
                                    mime_type="audio/pcm;rate=16000"
                                )
                            )
                        elif "text" in message:
                            text_data = message["text"]
                            try:
                                cmd = json.loads(text_data)
                                if cmd.get("type") == "update_config":
                                    pass
                            except json.JSONDecodeError:
                                await session.send_realtime_input(text=text_data)
                except (WebSocketDisconnect, RuntimeError):
                    logger.info("Client WebSocket disconnected inside client_to_gemini task.")
                except asyncio.CancelledError:
                    pass
                except Exception as ex:
                    logger.error(f"Error in client_to_gemini: {ex}")
                    raise

            # Loop 2: Gemini Live Session -> Client WebSocket
            async def gemini_to_client():
                try:
                    async for response in session.receive():
                        # Process response items from the Gemini Live stream
                        if response.server_content:
                            # 1. Check for user input audio transcription
                            if response.server_content.input_transcription:
                                text = response.server_content.input_transcription.text
                                if text:
                                    await client_ws.send_json({
                                        "type": "transcription",
                                        "payload": {
                                            "speaker": "user",
                                            "text": text
                                        }
                                    })

                            # 2. Check for model turn output parts
                            if response.server_content.model_turn:
                                parts = response.server_content.model_turn.parts
                                for part in parts:
                                    # Synthesized translation audio (24kHz Mono 16-bit PCM)
                                    if part.inline_data:
                                        audio_bytes = part.inline_data.data
                                        await client_ws.send_bytes(audio_bytes)

                                    # Text transcription of the translation
                                    if part.text:
                                        await client_ws.send_json({
                                            "type": "translation",
                                            "payload": {
                                                "speaker": "ai",
                                                "text": part.text
                                            }
                                        })
                        
                            # 3. Forward turn complete signal to notify client to resume capturing mic
                            if response.server_content.turn_complete:
                                await client_ws.send_json({
                                    "type": "turn_complete",
                                    "payload": {}
                                })
                except asyncio.CancelledError:
                    pass
                except Exception as ex:
                    logger.error(f"Error in gemini_to_client: {ex}")
                    raise

            # Run both tasks concurrently and gracefully clean them up when one exits
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