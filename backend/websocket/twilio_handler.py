import asyncio
import base64
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from backend.config.settings import settings
from backend.audio.twilio_audio import (
    mulaw_to_pcm16_8k,
    resample_8k_to_16k,
    pcm16_to_bytes,
    bytes_to_pcm16,
    resample_24k_to_8k,
    pcm16_to_mulaw
)

logger = logging.getLogger("backend")

async def handle_twilio_stream(client_ws: WebSocket, source: str = "Sinhala", target: str = "Tamil"):
    """
    Handles a real-time call audio stream from Twilio.
    Supports bidirectional translation using two concurrent Gemini Live sessions:
    - Inbound track (Caller, speaking `source` language) is translated to `target` language.
    - Outbound track (Callee, speaking `target` language) is translated to `source` language.
    """
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not configured in settings.")
        await client_ws.close(code=1008, reason="API key missing")
        return

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
    
    inbound_target = language_map.get(target, "ta")
    outbound_target = language_map.get(source, "si")

    # Inbound config: Caller (Sinhala) -> Gemini translates to Callee (Tamil)
    config_inbound = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        translation_config=types.TranslationConfig(
            target_language_code=inbound_target,
            echo_target_language=True
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    # Outbound config: Callee (Tamil) -> Gemini translates to Caller (Sinhala)
    config_outbound = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        translation_config=types.TranslationConfig(
            target_language_code=outbound_target,
            echo_target_language=True
        ),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    # State variables
    stream_sid = None
    call_sid = None
    inbound_session = None
    outbound_session = None
    
    write_lock = asyncio.Lock()
    
    async def send_to_twilio(payload_base64: str):
        """Helper to send media payload back to Twilio with thread-safety lock."""
        if not stream_sid:
            return
        async with write_lock:
            try:
                await client_ws.send_json({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {
                        "payload": payload_base64
                    }
                })
            except Exception as e:
                logger.error(f"Error sending audio to Twilio: {e}")

    # Listeners to stream Gemini response audio back to Twilio
    async def listen_gemini_inbound(session):
        try:
            async for response in session.receive():
                if response.server_content:
                    if response.server_content.input_transcription:
                        text = response.server_content.input_transcription.text
                        if text:
                            logger.info(f"[Gemini Inbound Input Transcription]: {text}")
                    if response.server_content.output_transcription:
                        text = response.server_content.output_transcription.text
                        if text:
                            logger.info(f"[Gemini Inbound Translation Transcription]: {text}")
                            
                    if response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if part.text:
                                logger.info(f"[Gemini Inbound Text Response]: {part.text}")
                            if part.inline_data:
                                pcm_24k_bytes = part.inline_data.data
                                logger.debug(f"Gemini Inbound audio output: {len(pcm_24k_bytes)} bytes")
                                samples_24k = bytes_to_pcm16(pcm_24k_bytes)
                                samples_8k = resample_24k_to_8k(samples_24k)
                                mulaw_data = pcm16_to_mulaw(samples_8k)
                                payload_b64 = base64.b64encode(mulaw_data).decode("utf-8")
                                await send_to_twilio(payload_b64)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in Gemini Inbound listener: {e}")

    async def listen_gemini_outbound(session):
        try:
            async for response in session.receive():
                if response.server_content:
                    if response.server_content.input_transcription:
                        text = response.server_content.input_transcription.text
                        if text:
                            logger.info(f"[Gemini Outbound Input Transcription]: {text}")
                    if response.server_content.output_transcription:
                        text = response.server_content.output_transcription.text
                        if text:
                            logger.info(f"[Gemini Outbound Translation Transcription]: {text}")
                            
                    if response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if part.text:
                                logger.info(f"[Gemini Outbound Text Response]: {part.text}")
                            if part.inline_data:
                                pcm_24k_bytes = part.inline_data.data
                                logger.debug(f"Gemini Outbound audio output: {len(pcm_24k_bytes)} bytes")
                                samples_24k = bytes_to_pcm16(pcm_24k_bytes)
                                samples_8k = resample_24k_to_8k(samples_24k)
                                mulaw_data = pcm16_to_mulaw(samples_8k)
                                payload_b64 = base64.b64encode(mulaw_data).decode("utf-8")
                                await send_to_twilio(payload_b64)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in Gemini Outbound listener: {e}")

    # Async tasks trackers
    active_tasks = []

    try:
        # Establish connection to the Inbound Gemini Session immediately
        async with ai_client.aio.live.connect(model=settings.GEMINI_MODEL, config=config_inbound) as in_session:
            inbound_session = in_session
            logger.info("Twilio Inbound Gemini Live Session connected.")
            
            inbound_task = asyncio.create_task(listen_gemini_inbound(inbound_session))
            active_tasks.append(inbound_task)
            
            # Since outbound session is lazily loaded when outbound track audio is seen,
            # we manage its lifecycle inside a context manager or manually.
            # To handle it cleanly, we can use a manual connect or standard aio context if we know it's bridged.
            # However, since we are inside `async with in_session`, we can run an inner connection for outbound.
            # To do this cleanly, we can open the outbound connection on demand.
            
            async def run_outbound_and_listen():
                nonlocal outbound_session
                logger.info("Initializing lazy Twilio Outbound Gemini Live Session...")
                async with ai_client.aio.live.connect(model=settings.GEMINI_MODEL, config=config_outbound) as out_session:
                    outbound_session = out_session
                    logger.info("Twilio Outbound Gemini Live Session connected.")
                    outbound_task = asyncio.create_task(listen_gemini_outbound(outbound_session))
                    active_tasks.append(outbound_task)
                    
                    # Keep outbound session alive as long as we need
                    while True:
                        await asyncio.sleep(1)
            
            outbound_runner_task = None
            media_counter = 0

            while True:
                data = await client_ws.receive_text()
                msg = json.loads(data)
                
                event = msg.get("event")
                if event == "start":
                    stream_sid = msg.get("streamSid")
                    call_sid = msg.get("start", {}).get("callSid")
                    logger.info(f"Twilio call stream started. StreamSid: {stream_sid}, CallSid: {call_sid}")
                    
                elif event == "media":
                    media = msg.get("media", {})
                    track = media.get("track")
                    payload = media.get("payload")
                    
                    if not payload:
                        continue
                        
                    media_counter += 1
                    if media_counter % 100 == 0:
                        logger.info(f"Processed 100 audio frames from Twilio (current track: {track}, total: {media_counter})")
                        
                    raw_mulaw = base64.b64decode(payload)
                    samples_8k = mulaw_to_pcm16_8k(raw_mulaw)
                    samples_16k = resample_8k_to_16k(samples_8k)
                    pcm_16k_bytes = pcm16_to_bytes(samples_16k)
                    
                    if track == "inbound":
                        # Send to inbound Gemini translator (translates Sinhala -> Tamil)
                        if inbound_session:
                            await inbound_session.send_realtime_input(
                                audio=types.Blob(
                                    data=pcm_16k_bytes,
                                    mime_type="audio/pcm;rate=16000"
                                )
                            )
                    elif track == "outbound":
                        # Lazy connect outbound session on first outbound track frame (Tamil -> Sinhala)
                        if not outbound_runner_task:
                            outbound_runner_task = asyncio.create_task(run_outbound_and_listen())
                            active_tasks.append(outbound_runner_task)
                            # Give it a brief moment to connect
                            await asyncio.sleep(0.5)
                        
                        if outbound_session:
                            await outbound_session.send_realtime_input(
                                audio=types.Blob(
                                    data=pcm_16k_bytes,
                                    mime_type="audio/pcm;rate=16000"
                                )
                            )
                            
                elif event == "stop":
                    logger.info(f"Twilio call stream stopped. StreamSid: {stream_sid}")
                    break

    except WebSocketDisconnect:
        logger.info("Twilio WebSocket connection disconnected.")
    except Exception as e:
        logger.error(f"Error in Twilio translation loop: {str(e)}")
    finally:
        # Cancel all background tasks
        logger.info("Cleaning up Twilio call translation tasks...")
        for task in active_tasks:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("Twilio translation loop clean up complete.")
