"""
CLIENT CODE EXAMPLE — accessing the SinTam backend from Python.

The backend (server) does the translation work with Gemini AI. This small program is a
CLIENT: it connects to the backend over a WebSocket, sends text or speech (.wav / .pcm),
and receives the translation (text + translated voice). It does not need the web page,
and it can run on a different computer than the backend.

How to try it:
  1. Start the backend:     python run_project.py
  2. In a second terminal:  python client_example.py
     Or pass a WAV file:    python client_example.py path/to/my_speech.wav
     (backend on another computer or port:  python client_example.py 192.168.1.20:8000)

Only needs:  pip install websockets
"""

import asyncio
import base64
import importlib.util
import io
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import urllib.request
import wave
import zipfile

GITHUB_ZIP_URL = "https://github.com/UVSHUB/Tamil-and-Sinhala-Converter/archive/refs/heads/main.zip"


def _server_reachable(server: str) -> bool:
    try:
        with urllib.request.urlopen(f"http://{server}/api/v1/health", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _bootstrap_from_github_and_run() -> int:
    """If no local backend is running and backend/ files are not present locally,
    automatically download the full project from GitHub and run it in the terminal."""
    here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    local_cli = os.path.join(here, "cli.py")
    local_backend = os.path.join(here, "backend", "main.py")

    if os.path.isfile(local_cli) and os.path.isfile(local_backend):
        project_dir = here
    else:
        cache_root = os.path.join(os.path.expanduser("~"), ".sintam_project")
        project_dir = os.path.join(cache_root, "Tamil-and-Sinhala-Converter-main")
        try:
            print("Fetching latest SinTam backend & client from GitHub (UVSHUB/Tamil-and-Sinhala-Converter) ...")
            os.makedirs(cache_root, exist_ok=True)
            with urllib.request.urlopen(GITHUB_ZIP_URL, timeout=60) as resp:
                zip_bytes = resp.read()
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                zf.extractall(cache_root)
            print(f"Project ready at: {project_dir}")
        except Exception as exc:
            if not os.path.isfile(os.path.join(project_dir, "backend", "main.py")):
                raise RuntimeError(f"Could not download project from GitHub: {exc}") from exc

    cmd = [sys.executable, os.path.join(project_dir, "cli.py"), "--run-backend", "--play"]
    if len(sys.argv) > 1:
        cmd.extend(sys.argv[1:])
    else:
        cmd.append("--interactive")
    return subprocess.call(cmd)


# If the user runs this script with no running local backend, automatically bootstrap & start the backend!
_first_arg = sys.argv[1] if len(sys.argv) > 1 else ""
_looks_like_remote_host = ":" in _first_arg and not os.path.exists(_first_arg) and not _first_arg.lower().startswith(("localhost:", "127.0.0.1:"))
if not _looks_like_remote_host and not _server_reachable("127.0.0.1:8000"):
    sys.exit(_bootstrap_from_github_and_run())

if importlib.util.find_spec("websockets") is None:
    print("Installing missing package 'websockets' ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "websockets>=12.0"], check=False)

import websockets

try:
    from translate_client import (
        AUDIO_EXTENSIONS,
        load_audio,
        play_wav,
        record_microphone_audio,
        resolve_audio_path,
        save_wav,
    )
except ImportError:
    # Standalone fallbacks so client_example.py works even if copied as a single file to another computer
    AUDIO_EXTENSIONS = (
        ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".oga",
        ".flac", ".webm", ".mp4", ".3gp", ".amr", ".wma", ".aiff", ".caf", ".pcm", ".raw",
    )

    def resolve_audio_path(path: str) -> str:
        return os.path.abspath(os.path.expanduser(path.strip().strip('"').strip("'")))

    def load_audio(path: str) -> bytes:
        resolved = resolve_audio_path(path)
        with open(resolved, "rb") as f:
            raw = f.read()
        if resolved.lower().endswith(".wav") or raw[:4] == b"RIFF":
            with wave.open(io.BytesIO(raw), "rb") as wf:
                channels, rate, width = wf.getnchannels(), wf.getframerate(), wf.getsampwidth()
                frames = wf.readframes(wf.getnframes())
            if width == 1:
                frames = struct.pack(f"<{len(frames)}h", *[((b - 128) << 8) for b in frames])
            if channels > 1:
                n = len(frames) // 2
                s = struct.unpack(f"<{n}h", frames[: n * 2])
                mono = [sum(s[i:i + channels]) // channels for i in range(0, n - channels + 1, channels)]
                frames = struct.pack(f"<{len(mono)}h", *mono)
            if rate != 16000 and frames:
                n_in = len(frames) // 2
                s = struct.unpack(f"<{n_in}h", frames[: n_in * 2])
                n_out = int(n_in * 16000 / rate)
                step = rate / 16000
                out = [int(s[int(i * step)] * (1 - (i * step - int(i * step))) + s[min(int(i * step) + 1, n_in - 1)] * (i * step - int(i * step))) for i in range(n_out)]
                frames = struct.pack(f"<{len(out)}h", *out)
            return frames
        return raw

    def save_wav(pcm: bytes, path: str, rate: int = 24000) -> None:
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(pcm)

    def play_wav(path: str) -> bool:
        try:
            if sys.platform == "darwin":
                subprocess.run(["afplay", path], check=True)
            elif sys.platform == "win32":
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
            else:
                subprocess.run(["aplay", "-q", path], check=True)
            return True
        except Exception:
            return False

    def record_microphone_audio(duration=None, output_wav="recorded_voice.wav") -> str:
        raise RuntimeError("Copy translate_client.py alongside client_example.py or install sounddevice for mic input.")

# Check if first CLI argument is 'mic', an audio file path (.mp3 / .wav / .m4a / .ogg / .pcm), or server host:port
_arg1 = sys.argv[1] if len(sys.argv) > 1 else ""
if _arg1.lower() in ("mic", "voice", "record"):
    CUSTOM_AUDIO_FILE = "__MIC__"
    SERVER = sys.argv[2] if len(sys.argv) > 2 else "localhost:8000"
elif _arg1.lower().endswith(AUDIO_EXTENSIONS) or (_arg1 and os.path.isfile(resolve_audio_path(_arg1))):
    CUSTOM_AUDIO_FILE = resolve_audio_path(_arg1)
    SERVER = sys.argv[2] if len(sys.argv) > 2 else "localhost:8000"
else:
    CUSTOM_AUDIO_FILE = ""
    SERVER = _arg1 or "localhost:8000"

URL = f"ws://{SERVER}/ws/translate-auto"


async def translate_text(text: str, target: str = "Tamil", output_wav: str = "translated_text.wav") -> str:
    """Send a sentence to the backend, save & play the translated voice, and return the translated text."""
    voice = bytearray()
    translated = ""
    async with websockets.connect(f"{URL}?target={target}") as ws:     # 1. connect to the backend
        await ws.send(text)                                             # 2. send the text
        async for message in ws:                                        # 3. read the replies
            if isinstance(message, bytes):
                voice.extend(message)
            elif isinstance(message, str):
                reply = json.loads(message)
                if reply["type"] == "turn_complete":                    # 4. sentence finished
                    translated = reply["payload"].get("ai_text", "")
                    break
    if voice and output_wav:
        save_wav(bytes(voice), output_wav)
        print(f"  Translated voice saved to {output_wav} ({len(voice) / 48000:.1f} seconds)")
        play_wav(output_wav)
    return translated


async def translate_speech(audio_file: str, target: str = "Tamil", output_wav: str = "translated.wav") -> None:
    """Stream an audio recording (.mp3, .wav, .m4a, .ogg, .pcm) to the backend; print the transcribed text,
    translated text, and save + play the translated voice."""
    speech = load_audio(audio_file)
    voice = bytearray()
    done_event = asyncio.Event()

    async with websockets.connect(f"{URL}?target={target}") as ws:

        async def listen():                                             # runs while we are sending
            async for message in ws:
                if isinstance(message, bytes):                          # binary = translated voice
                    voice.extend(message)
                else:                                                   # text = JSON message
                    reply = json.loads(message)
                    if reply["type"] == "turn_complete":
                        print("  You said   :", reply["payload"].get("user_text", ""))
                        print("  Translation:", reply["payload"].get("ai_text", ""))
                        done_event.set()

        listener = asyncio.create_task(listen())
        for i in range(0, len(speech), 3200):                           # send 0.1 s pieces in real time,
            await ws.send(speech[i:i + 3200])                           # like a live microphone
            await asyncio.sleep(0.1)
        for _ in range(6):
            await ws.send(b"\x00" * 3200)
            await asyncio.sleep(0.03)
        await ws.send(json.dumps({"type": "audio_eof"}))
        try:
            await asyncio.wait_for(done_event.wait(), timeout=20.0)
            await asyncio.sleep(0.5)
        except asyncio.TimeoutError:
            pass
        listener.cancel()

    if voice:
        save_wav(bytes(voice), output_wav)                              # voice = 24 kHz mono 16-bit PCM
        print(f"  Translated voice saved to {output_wav} ({len(voice) / 48000:.1f} seconds)")
        play_wav(output_wav)


async def main():
    print(f"Backend: {URL}\n")

    if CUSTOM_AUDIO_FILE == "__MIC__":
        rec_file = record_microphone_audio(output_wav="recorded_voice.wav")
        print(f"Translating recorded microphone voice: {rec_file} -> Tamil (text + voice)")
        await translate_speech(rec_file, target="Tamil", output_wav="translated.wav")
        return

    if CUSTOM_AUDIO_FILE:
        print(f"Translating audio file: {CUSTOM_AUDIO_FILE} -> Tamil (text + voice)")
        await translate_speech(CUSTOM_AUDIO_FILE, target="Tamil", output_wav="translated.wav")
        return

    print("1) Text: Sinhala -> Tamil")
    print("  Translation:", await translate_text("ආයුබෝවන්, ඔබට කොහොමද?", target="Tamil"))

    print("\n2) Text: Tamil -> Sinhala")
    print("  Translation:", await translate_text("வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?", target="Sinhala"))

    default_audio = "sample_sinhala.wav" if os.path.isfile("sample_sinhala.wav") else "sample_sinhala.pcm"
    print(f"\n3) Speech ({default_audio}): Sinhala recording -> Tamil text + voice")
    await translate_speech(default_audio, target="Tamil")

    if sys.stdin.isatty():
        print("\n" + "-" * 60)
        print("Interactive Client Mode: Enter an audio file (.mp3/.wav), 'mic', or text ('exit' to quit)")
        while True:
            try:
                user_in = input("\nEnter .mp3/.wav path, 'mic', or text > ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user_in or user_in.lower() in ("exit", "quit"):
                break
            if user_in.lower() in ("mic", "voice", "record"):
                rec_file = record_microphone_audio(output_wav="recorded_voice.wav")
                await translate_speech(rec_file, target="Tamil", output_wav="translated.wav")
            elif user_in.lower().endswith(AUDIO_EXTENSIONS) or os.path.isfile(resolve_audio_path(user_in)):
                await translate_speech(resolve_audio_path(user_in), target="Tamil", output_wav="translated.wav")
            else:
                print("  Translation:", await translate_text(user_in, target="Tamil"))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # show Sinhala/Tamil on Windows
    except (AttributeError, ValueError):
        pass
    try:
        asyncio.run(main())
    except (ConnectionRefusedError, OSError):
        print(f"Could not connect to the backend at {SERVER}. Start it first:  python run_project.py")
