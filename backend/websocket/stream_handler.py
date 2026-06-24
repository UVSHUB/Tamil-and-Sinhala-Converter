import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from backend.config.settings import settings

logger = logging.getLogger("backend.stream_handler")

client = genai.Client(api_key=settings.GEMINI_API_KEY)

async def handle_voice_translation_stream(client_ws: WebSocket):
    try:
        await client_ws.accept()
        print("🚀 Client connected over WebSocket!")
    except RuntimeError:
        pass

    model = settings.GEMINI_MODEL

    session_config = types.LiveConnectConfig(
        response_modalities=[types.LiveModality.AUDIO],
        system_instruction=types.Content(
            parts=[
                types.Part.from_text(
                    text=(
                        "You are an elite real-time, low-latency audio voice translator. "
                        "Your single responsibility is to listen to the incoming Sinhala speech audio "
                        "and instantly translate it into fluent Tamil speech. "
                        "Preserve the emotional context, speed, and vocal tone of the speaker. "
                        "Do not output introductions, conversational comments, or explanations. "
                        "Only output the direct Tamil voice translation."
                    )
                )
            ]
        ),
        generation_config=types.GenerateContentConfig(
            response_mime_type="audio/pcm",
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
                )
            )
        )
    )

    async with client.aio.live.connect(model=model, config=session_config) as gemini_session:
        print("✅ Gemini Live API connected.")

        async def send_to_gemini():
            try:
                while True:
                    try:
                        data = await client_ws.receive_bytes()
                        await gemini_session.send_realtime_input(
                            audio=types.Blob(
                                data=data,
                                mime_type="audio/pcm;rate=16000"
                            )
                        )
                    except RuntimeError:
                        text_data = await client_ws.receive_text()
                        await gemini_session.send_realtime_input(text=text_data)
                        await client_ws.send_json({
                            "status": "acknowledged",
                            "echo": text_data
                        })
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.debug(f"send_to_gemini ended: {e}")

        async def receive_from_gemini():
            try:
                async for chunk in gemini_session.receive():
                    server_content = chunk.server_content

                    if server_content is not None:
                        if server_content.model_turn is not None:
                            for part in server_content.model_turn.parts:
                                if part.inline_data is not None:
                                    await client_ws.send_bytes(part.inline_data.data)

                        if server_content.output_transcription is not None:
                            await client_ws.send_json({
                                "type": "transcription",
                                "data": server_content.output_transcription.text
                            })
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.error(f"receive_from_gemini error: {e}")

        await asyncio.gather(send_to_gemini(), receive_from_gemini())