"""
Command-line interface for the SinTam WebSocket Client.
Run with:
    python -m websocket_client.cli
    python -m websocket_client.cli --source Sinhala --target Tamil --text "සුබ උදෑසනක්" --play
"""

import argparse
import asyncio
import sys
from .client import SinTamWebSocketClient, TranslationResult


async def async_main():
    parser = argparse.ArgumentParser(
        description="SinTam Real-Time WebSocket Translation Client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1", help="Backend WebSocket server hostname")
    parser.add_argument("--port", type=int, default=8000, help="Backend WebSocket server port")
    parser.add_argument("--source", default="Sinhala", help="Source language (e.g. Sinhala, Tamil, English)")
    parser.add_argument("--target", default="Tamil", help="Target language (e.g. Tamil, Sinhala, English)")
    parser.add_argument("--voice", default="Aoede", choices=["Aoede", "Charon", "Kore", "Puck", "Fenrir"], help="Gemini TTS voice")
    parser.add_argument("--room", default="default", help="Room ID for isolation")
    parser.add_argument("--auto", action="store_true", help="Use bidirectional auto-detection mode")
    parser.add_argument("--play", action="store_true", help="Automatically play synthesized voice through speakers")
    parser.add_argument("--save-dir", default=None, help="Directory to save output WAV files")
    parser.add_argument("--text", default=None, help="Translate a single phrase and exit")
    parser.add_argument("--wav", default=None, help="Stream a WAV file (16kHz 16-bit mono) to the translator")

    args = parser.parse_args()

    print("=" * 60)
    print("SinTam WebSocket Translation Client")
    print(f"Backend Target: ws://{args.host}:{args.port}")
    print(f"Direction     : {args.source} -> {args.target}" if not args.auto else "Direction: Auto-Detect (Sinhala <-> Tamil)")
    print(f"TTS Voice     : {args.voice}")
    print(f"Speaker Play  : {'Enabled' if args.play else 'Disabled'}")
    if args.save_dir:
        print(f"Save Directory: {args.save_dir}")
    print("=" * 60)

    client = SinTamWebSocketClient(
        host=args.host,
        port=args.port,
        source=args.source,
        target=args.target,
        voice=args.voice,
        room=args.room,
        auto_mode=args.auto,
        auto_play=args.play,
        save_audio_dir=args.save_dir,
    )

    try:
        print("Connecting to backend WebSocket...")
        await client.connect()
        print("✓ Connected successfully!\n")

        # Mode 1: One-shot text translation
        if args.text:
            print(f">> Translating: {args.text}")
            result = await client.translate_text(args.text)
            print("-" * 40)
            print(f"Translation   : {result.translated_text}")
            print(f"Audio Received: {len(result.audio_bytes):,} bytes (24kHz PCM)")
            if result.wav_path:
                print(f"Audio Saved To: {result.wav_path}")
            print("-" * 40)
            return

        # Mode 2: One-shot WAV file streaming
        if args.wav:
            print(f">> Streaming WAV file: {args.wav}")
            await client.send_wav_file(args.wav)
            result = await client.wait_for_turn(timeout=20.0)
            print("-" * 40)
            print(f"User Spoke    : {result.user_transcript}")
            print(f"Translation   : {result.translated_text}")
            print(f"Audio Received: {len(result.audio_bytes):,} bytes")
            print("-" * 40)
            return

        # Mode 3: Interactive CLI session
        print("Interactive Session Started. Type any phrase and press Enter.")
        print("Type 'exit' or 'quit' to terminate.\n")

        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, input, "Input phrase > ")
            except (EOFError, KeyboardInterrupt):
                break

            text = line.strip()
            if not text:
                continue
            if text.lower() in ("exit", "quit"):
                break

            print("Translating...")
            try:
                result = await client.translate_text(text, timeout=20.0)
                print(f"✓ Translation: {result.translated_text}")
                print(f"  Audio: {len(result.audio_bytes):,} bytes (24kHz)")
                if result.wav_path:
                    print(f"  WAV saved: {result.wav_path}")
                print()
            except Exception as err:
                print(f"✕ Error: {err}\n")

    finally:
        print("\nDisconnecting...")
        await client.disconnect()
        print("Goodbye!")


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
