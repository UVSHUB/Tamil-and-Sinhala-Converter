import asyncio, websockets, json, pathlib

# Simple translation client that connects to the translate-auto WebSocket endpoint
async def translate(host="localhost", port=8000, target="Tamil"):
    ws_url = f"ws://{host}:{port}/ws/translate-auto?target={target}"
    async with websockets.connect(ws_url) as ws:
        # Receive the connection confirmation/status
        print("Server:", await ws.recv())
        # Example: switch output language on‑the‑fly
        await ws.send(json.dumps({"type": "set_target", "target": "Sinhala"}))
        print("Switched:", await ws.recv())
        # Close the connection (or send audio bytes here)
        await ws.close()

# Backend‑only voice test (no frontend)
# Sends a pre‑recorded PCM audio file to the /ws/translate-auto endpoint,
# receives synthesized TTS audio bytes, and writes them to output.wav.
AUDIO_PCM = "sample.pcm"   # 16 kHz, mono, 16‑bit little‑endian PCM
OUTPUT_WAV = "output.wav"

async def translate_file(host="localhost", port=8000, target="Tamil"):
    ws_url = f"ws://{host}:{port}/ws/translate-auto?target={target}"
    async with websockets.connect(ws_url) as ws:
        # receive initial status
        print("Server:", await ws.recv())

        # stream the PCM file in chunks (e.g., 1024‑byte frames)
        with open(AUDIO_PCM, "rb") as f:
            while chunk := f.read(1024):
                await ws.send(chunk)

        # signal end of audio (optional – backend will close on client disconnect)
        await ws.send(b"")

        # collect TTS audio bytes (binary frames)
        tts_data = bytearray()
        try:
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                if isinstance(msg, bytes):
                    tts_data.extend(msg)
                else:
                    # ignore JSON status messages
                    continue
        except asyncio.TimeoutError:
            pass

        # write WAV file (the backend already returns a valid WAV container)
        pathlib.Path(OUTPUT_WAV).write_bytes(tts_data)
        print(f"TTS audio saved to {OUTPUT_WAV}")

# Run the translate_file function when this script is executed directly
if __name__ == "__main__":
    asyncio.run(translate_file())
