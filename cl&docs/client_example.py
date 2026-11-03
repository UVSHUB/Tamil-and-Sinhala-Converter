"""
CLIENT CODE EXAMPLE — accessing the SinTam backend from Python.

The backend (server) does the translation work with Gemini AI. This small program is a
CLIENT: it connects to the backend over a WebSocket, sends text or speech, and receives
the translation (text + translated voice). It does not need the web page, and it can run
on a different computer than the backend.

How to try it:
  1. Start the backend:     python run_project.py
  2. In a second terminal:  python client_example.py
     (backend on another computer or port:  python client_example.py 192.168.1.20:8000)

Only needs:  pip install websockets
"""

import asyncio
import json
import sys
import wave

import websockets

# Address of the backend. Default: this computer, port 8000.
SERVER = sys.argv[1] if len(sys.argv) > 1 else "localhost:8000"
URL = f"ws://{SERVER}/ws/translate-auto"


async def translate_text(text: str, target: str = "Tamil") -> str:
    """Send a sentence to the backend and return the translated sentence."""
    async with websockets.connect(f"{URL}?target={target}") as ws:     # 1. connect to the backend
        await ws.send(text)                                             # 2. send the text
        async for message in ws:                                        # 3. read the replies
            if isinstance(message, str):
                reply = json.loads(message)
                if reply["type"] == "turn_complete":                    # 4. sentence finished
                    return reply["payload"]["ai_text"]
    return ""


async def translate_speech(pcm_file: str, target: str = "Tamil", output_wav: str = "translated.wav") -> None:
    """Stream a speech recording to the backend; print the translation and save the translated voice.

    The recording must be raw 16 kHz, mono, 16-bit PCM (like sample_sinhala.pcm)."""
    speech = open(pcm_file, "rb").read()
    voice = bytearray()

    async with websockets.connect(f"{URL}?target={target}") as ws:

        async def listen():                                             # runs while we are sending
            async for message in ws:
                if isinstance(message, bytes):                          # binary = translated voice
                    voice.extend(message)
                else:                                                   # text = JSON message
                    reply = json.loads(message)
                    if reply["type"] == "turn_complete":
                        print("  You said   :", reply["payload"]["user_text"])
                        print("  Translation:", reply["payload"]["ai_text"])

        listener = asyncio.create_task(listen())
        for i in range(0, len(speech), 3200):                           # send 0.1 s pieces in real time,
            await ws.send(speech[i:i + 3200])                           # like a live microphone
            await asyncio.sleep(0.1)
        await asyncio.sleep(5)                                          # let the last sentence finish
        listener.cancel()

    with wave.open(output_wav, "wb") as wav:                            # voice = 24 kHz mono 16-bit PCM
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(bytes(voice))
    print(f"  Translated voice saved to {output_wav} ({len(voice) / 48000:.1f} seconds)")


async def main():
    print(f"Backend: {URL}\n")

    print("1) Text: Sinhala -> Tamil")
    print("  Translation:", await translate_text("ආයුබෝවන්, ඔබට කොහොමද?", target="Tamil"))

    print("\n2) Text: Tamil -> Sinhala")
    print("  Translation:", await translate_text("வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?", target="Sinhala"))

    print("\n3) Speech: Sinhala recording -> Tamil voice")
    await translate_speech("sample_sinhala.pcm", target="Tamil")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")      # show Sinhala/Tamil on Windows
    except (AttributeError, ValueError):
        pass
    try:
        asyncio.run(main())
    except (ConnectionRefusedError, OSError):
        print(f"Could not connect to the backend at {SERVER}. Start it first:  python run_project.py")
