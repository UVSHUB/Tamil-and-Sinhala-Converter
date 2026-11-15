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
import importlib.util
import json
import os
import subprocess
import sys
import wave

if importlib.util.find_spec("websockets") is None:
    print("Installing missing package 'websockets' ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "websockets>=12.0"], check=False)

import websockets
from translate_client import AUDIO_EXTENSIONS, load_audio, resolve_audio_path

# Check if first CLI argument is an audio file path (.mp3 / .wav / .m4a / .ogg / .pcm) or server host:port
_arg1 = sys.argv[1] if len(sys.argv) > 1 else ""
if _arg1.lower().endswith(AUDIO_EXTENSIONS) or os.path.isfile(resolve_audio_path(_arg1)):
    CUSTOM_AUDIO_FILE = resolve_audio_path(_arg1)
    SERVER = sys.argv[2] if len(sys.argv) > 2 else "localhost:8000"
else:
    CUSTOM_AUDIO_FILE = ""
    SERVER = _arg1 or "localhost:8000"

URL = f"ws://{SERVER}/ws/translate-auto"


async def translate_text(text: str, target: str = "Tamil") -> str:
    """Send a sentence to the backend and return the translated sentence."""
    async with websockets.connect(f"{URL}?target={target}") as ws:     # 1. connect to the backend
        await ws.send(text)                                             # 2. send the text
        async for message in ws:                                        # 3. read the replies
            if isinstance(message, str):
                reply = json.loads(message)
                if reply["type"] == "turn_complete":                    # 4. sentence finished
                    return reply["payload"].get("ai_text", "")
    return ""


async def translate_speech(audio_file: str, target: str = "Tamil", output_wav: str = "translated.wav") -> None:
    """Stream a .wav or .pcm speech recording to the backend; print the transcribed text,
    translated text, and save the translated voice as a WAV file."""
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
            await asyncio.wait_for(done_event.wait(), timeout=15.0)
            await asyncio.sleep(0.5)
        except asyncio.TimeoutError:
            pass
        listener.cancel()

    with wave.open(output_wav, "wb") as wav:                            # voice = 24 kHz mono 16-bit PCM
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(bytes(voice))
    print(f"  Translated voice saved to {output_wav} ({len(voice) / 48000:.1f} seconds)")


async def main():
    print(f"Backend: {URL}\n")

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


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # show Sinhala/Tamil on Windows
    except (AttributeError, ValueError):
        pass
    try:
        asyncio.run(main())
    except (ConnectionRefusedError, OSError):
        print(f"Could not connect to the backend at {SERVER}. Start it first:  python run_project.py")
