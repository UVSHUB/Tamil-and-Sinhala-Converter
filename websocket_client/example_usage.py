"""
SinTam WebSocket Client - Programmatic Usage Examples
Demonstrates how to import and use SinTamWebSocketClient in Python code.
"""

import asyncio
import os
import sys

# Ensure parent directory is on sys.path for direct execution
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from websocket_client import SinTamWebSocketClient


async def example_1_simple_translation():
    """Example 1: Send text over WebSocket and receive translated text and voice."""
    print("\n--- Example 1: Simple One-Shot Translation ---")
    
    # Initialize client with input parameters
    client = SinTamWebSocketClient(
        host="127.0.0.1",
        port=8000,
        source="Sinhala",
        target="Tamil",
        voice="Aoede",
        auto_play=False,  # Set to True to play audio through speakers
    )

    async with client:
        phrase = "ඔබට සුභ දවසක් වේවා"
        print(f"Original Sinhala: {phrase}")
        
        result = await client.translate_text(phrase)
        
        print(f"Translated Tamil: {result.translated_text}")
        print(f"Audio received  : {len(result.audio_bytes):,} bytes (24kHz PCM)")

        # Save to WAV
        saved_file = result.save_wav("output_sample.wav")
        print(f"Saved audio to  : {saved_file}")


async def example_2_streaming_callbacks():
    """Example 2: Using real-time callbacks for streaming speech delta tokens."""
    print("\n--- Example 2: Streaming Callbacks ---")

    def on_transcription(full_text: str, delta: str):
        print(f"[User Live] {delta}", end="", flush=True)

    def on_translation(full_text: str, delta: str):
        print(f"[AI Live] {delta}", end="", flush=True)

    def on_turn_complete(result):
        print(f"\n[Turn Complete] Finished with {len(result.audio_bytes)} audio bytes.")

    client = SinTamWebSocketClient(
        host="127.0.0.1",
        port=8000,
        source="Sinhala",
        target="Tamil",
        voice="Charon",
        on_transcription=on_transcription,
        on_translation=on_translation,
        on_turn_complete=on_turn_complete,
    )

    async with client:
        print("Sending phrase...")
        await client.send_text("මම කොළඹ යනවා")
        result = await client.wait_for_turn(timeout=15.0)
        print(f"Final Result: {result.translated_text}")


async def main():
    await example_1_simple_translation()
    await example_2_streaming_callbacks()


if __name__ == "__main__":
    asyncio.run(main())
