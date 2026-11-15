"""
Command-line interface for the SinTam WebSocket Client.
Run with:
    python -m websocket_client.cli
    python -m websocket_client.cli --audio path/to/sound.mp3 --target Tamil --output output.wav --play
    python -m websocket_client.cli --mic --target Tamil --play
    python -m websocket_client.cli --source Sinhala --target Tamil --text "සුබ උදෑසනක්" --play
"""

import argparse
import asyncio
import importlib.util
import os
import subprocess
import sys
from typing import Optional, Tuple

if importlib.util.find_spec("websockets") is None:
    print("Installing missing package 'websockets' ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "websockets>=12.0"], check=False)

from .client import (
    AUDIO_EXTENSIONS,
    SinTamWebSocketClient,
    TranslationResult,
    record_microphone_audio,
    resolve_audio_path,
)


def _parse_mic_command(user_input: str) -> Tuple[bool, Optional[float]]:
    """Return (True, optional_seconds) if user typed 'mic', 'voice', 'record', or 'speak'."""
    parts = user_input.strip().split()
    if not parts:
        return False, None
    cmd = parts[0].lower().rstrip(":")
    if cmd in ("mic", "voice", "record", "speak"):
        if len(parts) > 1:
            try:
                return True, float(parts[1])
            except ValueError:
                return False, None
        return True, None
    return False, None


def _extract_audio_path(user_input: str) -> Optional[str]:
    """
    If `user_input` represents an audio file path (e.g. ends with .mp3/.wav/.m4a/.ogg/.flac/.pcm,
    starts with 'mp3:'/'wav:'/'audio:'/'file:', or is an existing file on disk),
    return the normalized path string. Otherwise return None.
    """
    raw = user_input.strip()
    for prefix in ("mp3:", "wav:", "m4a:", "ogg:", "audio:", "file:", "mp3 ", "wav ", "audio ", "file "):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix):].strip()
            return raw

    cleaned = raw.strip('"').strip("'").strip()
    if cleaned.lower().endswith(AUDIO_EXTENSIONS):
        return cleaned

    resolved = resolve_audio_path(cleaned)
    if os.path.isfile(resolved):
        return resolved

    return None


def _print_result(result: TranslationResult, is_audio_input: bool = False) -> None:
    print("-" * 50)
    if is_audio_input or result.user_transcript:
        print(f"Transcribed Text ({result.source_language}): {result.user_transcript or '(none)'}")
    print(f"Translated Text  ({result.target_language}): {result.translated_text or '(none)'}")
    if result.audio_bytes:
        duration_s = len(result.audio_bytes) / (result.sample_rate * 2)
        print(f"Voice Audio Size : {len(result.audio_bytes):,} bytes ({duration_s:.1f}s @ {result.sample_rate}Hz)")
    if result.wav_path:
        print(f"Translated Voice : {result.wav_path}")
    print("-" * 50)


async def async_main():
    parser = argparse.ArgumentParser(
        description="SinTam Real-Time WebSocket Translation Client (Text, MP3/WAV/M4A/OGG Audio & Live Microphone Voice)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", nargs="?", default=None,
                        help="Optional audio file path (.mp3, .wav, .m4a, .ogg, .flac, .pcm), 'mic', or text phrase")
    parser.add_argument("--host", default="127.0.0.1", help="Backend WebSocket server hostname")
    parser.add_argument("--port", type=int, default=8000, help="Backend WebSocket server port")
    parser.add_argument("--source", default="Sinhala", help="Source language (e.g. Sinhala, Tamil, English)")
    parser.add_argument("--target", default="Tamil", help="Target language (e.g. Tamil, Sinhala, English)")
    parser.add_argument("--voice", default="Aoede", choices=["Aoede", "Charon", "Kore", "Puck", "Fenrir"], help="Gemini TTS voice")
    parser.add_argument("--room", default="default", help="Room ID for isolation")
    parser.add_argument("--auto", action="store_true", help="Use bidirectional auto-detection mode (/ws/translate-auto)")
    parser.add_argument("--play", action="store_true", help="Automatically play synthesized voice through speakers")
    parser.add_argument("--save-dir", default=None, help="Directory to save output audio files")
    parser.add_argument("--output", "-o", default="output.wav", help="Output audio file path for translated voice (.wav, .mp3, .m4a)")
    parser.add_argument("--text", default=None, help="Translate a single phrase and exit")
    parser.add_argument("--wav", "--audio", "--mp3", dest="wav", default=None,
                        help="Stream an audio sound file (.mp3, .wav, .m4a, .aac, .ogg, .flac, .pcm, etc.) to the translator")
    parser.add_argument("--mic", "--voice-input", dest="mic", action="store_true",
                        help="Record live normal voice from the microphone and translate it")
    parser.add_argument("--record-seconds", "--duration", dest="record_seconds", type=float, default=None,
                        help="Seconds to record from microphone when using --mic (omit to press Enter when done)")
    parser.add_argument("--timeout", type=float, default=45.0, help="Seconds to wait for server response")

    args = parser.parse_args()

    # Resolve positional argument if given
    if args.input and not args.wav and not args.text and not args.mic:
        is_mic, mic_secs = _parse_mic_command(args.input)
        if is_mic:
            args.mic = True
            if mic_secs is not None and args.record_seconds is None:
                args.record_seconds = mic_secs
        else:
            audio_candidate = _extract_audio_path(args.input)
            if audio_candidate:
                args.wav = audio_candidate
            else:
                args.text = args.input

    print("=" * 60)
    print("SinTam WebSocket Translation Client")
    print(f"Backend Target: ws://{args.host}:{args.port}")
    print(f"Direction     : {args.source} -> {args.target}" if not args.auto else "Direction: Auto-Detect (Sinhala <-> Tamil)")
    print(f"TTS Voice     : {args.voice}")
    print(f"Speaker Play  : {'Enabled' if args.play else 'Disabled'}")
    print(f"Output Audio  : {args.output}")
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

        # Mode 0: One-shot live microphone voice recording
        if args.mic:
            rec_path = os.path.abspath("recorded_voice.wav")
            record_microphone_audio(duration=args.record_seconds, output_wav=rec_path)
            print(f">> Streaming recorded voice: {rec_path}")
            result = await client.translate_audio_file(
                rec_path, output_wav=args.output, timeout=args.timeout
            )
            _print_result(result, is_audio_input=True)
            return

        # Mode 1: One-shot text translation
        if args.text:
            print(f">> Translating text: {args.text}")
            result = await client.translate_text(args.text, timeout=args.timeout, output_wav=args.output)
            _print_result(result, is_audio_input=False)
            return

        # Mode 2: One-shot MP3/WAV/M4A/OGG/PCM file streaming
        if args.wav:
            resolved_wav = resolve_audio_path(args.wav)
            if not os.path.isfile(resolved_wav):
                print(f"✕ Error: Audio file not found: {args.wav}")
                return
            print(f">> Streaming sound file: {resolved_wav}")
            result = await client.translate_audio_file(
                resolved_wav, output_wav=args.output, timeout=args.timeout
            )
            _print_result(result, is_audio_input=True)
            return

        # Mode 3: Interactive CLI session (supports text, .mp3/.wav/.m4a/.ogg files, AND live microphone voice!)
        print("Interactive Session Started.")
        print("  • Enter an audio file path (.mp3, .wav, .m4a, .ogg, .flac, .aac, .pcm, etc.) to transcribe & translate audio + voice")
        print("  • Type 'mic' (or 'voice' / 'record 5') to speak live into your microphone")
        print("  • Or type any Sinhala/Tamil phrase (e.g. ආයුබෝවන්) to translate text + voice")
        print("  • Type 'exit' or 'quit' to terminate.\n")

        turn_count = 0
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, input, "Input (text, .mp3/.wav file path, or 'mic') > "
                )
            except (EOFError, KeyboardInterrupt):
                break

            user_input = line.strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit"):
                break

            turn_count += 1
            base, ext = os.path.splitext(args.output)
            out_wav = args.output if turn_count == 1 else f"{base}_{turn_count}{ext or '.wav'}"

            is_mic, mic_secs = _parse_mic_command(user_input)
            if is_mic:
                rec_path = os.path.abspath(f"recorded_voice_{turn_count}.wav")
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        record_microphone_audio,
                        mic_secs if mic_secs is not None else args.record_seconds,
                        rec_path,
                    )
                    print(f">> Streaming recorded voice: {rec_path} ...")
                    result = await client.translate_audio_file(
                        rec_path, output_wav=out_wav, timeout=args.timeout
                    )
                    _print_result(result, is_audio_input=True)
                    print()
                except Exception as err:
                    print(f"✕ Error recording/translating microphone voice: {err}\n")
                continue

            audio_candidate = _extract_audio_path(user_input)
            if audio_candidate is not None:
                resolved_wav = resolve_audio_path(audio_candidate)
                if not os.path.isfile(resolved_wav):
                    print(f"✕ Audio file not found: {audio_candidate}\n")
                    continue
                print(f">> Accessing & streaming audio file: {resolved_wav} ...")
                try:
                    result = await client.translate_audio_file(
                        resolved_wav, output_wav=out_wav, timeout=args.timeout
                    )
                    _print_result(result, is_audio_input=True)
                    print()
                except Exception as err:
                    print(f"✕ Error processing audio file: {err}\n")
            else:
                print(">> Translating text...")
                try:
                    result = await client.translate_text(
                        user_input, timeout=args.timeout, output_wav=out_wav
                    )
                    _print_result(result, is_audio_input=False)
                    print()
                except Exception as err:
                    print(f"✕ Error: {err}\n")

    finally:
        print("\nDisconnecting...")
        await client.disconnect()
        print("Goodbye!")


def main():
    try:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
