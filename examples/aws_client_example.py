"""
Lightweight Python Client for Sinhala <-> Tamil Real-Time Voice Translator
Connects to your AWS EC2 instance or local backend via WebSocket.

Requirements:
    pip install websockets
"""

import asyncio
import json
import websockets
import sys

# Replace with your EC2 Public IP or localhost
SERVER_HOST = "16.171.141.51"  # or "localhost"
SERVER_PORT = 8000
TARGET_LANGUAGE = "Tamil"  # "Tamil" or "Sinhala"

WS_URL = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws/translate-auto?target={TARGET_LANGUAGE}"


async def listen_to_translator(ws):
    """Listens for translations, transcriptions, and synthesized audio from the backend."""
    try:
        async for message in ws:
            if isinstance(message, bytes):
                # Binary audio bytes returned by Gemini TTS
                print(f"[AUDIO RECEIVED] Synthesized speech chunk: {len(message)} bytes")
            else:
                data = json.loads(message)
                msg_type = data.get("type")
                payload = data.get("payload", {})

                if msg_type == "status":
                    print(f"[STATUS] {payload.get('message')}")
                elif msg_type == "lang_detected":
                    print(f"[LANGUAGE] Detected: {payload.get('source')} -> Output: {payload.get('target')}")
                elif msg_type == "transcription":
                    print(f"[TRANSCRIPTION] ({payload.get('detected_lang')}): {payload.get('text')}")
                elif msg_type == "translation":
                    print(f"[TRANSLATION] -> ({payload.get('target_lang')}): {payload.get('text')}")
                elif msg_type == "turn_complete":
                    print("[TURN COMPLETE] Finished processing turn.\n")
    except websockets.exceptions.ConnectionClosed:
        print("[DISCONNECTED] Server closed the connection.")


async def main():
    print(f"Connecting to: {WS_URL} ...")
    try:
        async with websockets.connect(WS_URL) as ws:
            print("[CONNECTED] Real-time translation session is active!\n")

            # Start listening in background
            listener_task = asyncio.create_task(listen_to_translator(ws))

            # Demo 1: Switch target language on the fly without reconnecting
            await asyncio.sleep(2)
            print("\n>>> Switching target language to Sinhala on the fly...")
            await ws.send(json.dumps({"type": "set_target", "target": "Sinhala"}))

            await asyncio.sleep(2)
            print("\n>>> Switching target language back to Tamil...")
            await ws.send(json.dumps({"type": "set_target", "target": "Tamil"}))

            # Keep connection open to receive incoming audio & transcripts
            print("\nListening for server responses... (Press Ctrl+C to stop)")
            await listener_task

    except Exception as e:
        print(f"[ERROR] Could not connect to {WS_URL}: {e}")
        print("Tip: Make sure port 8000 is open in your AWS EC2 Security Group.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSession ended by user.")
