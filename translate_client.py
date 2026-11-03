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

async def _stream_audio(ws, audio_path):
    """Stream PCM audio file to the WebSocket in 1024‑byte chunks."""
    with open(audio_path, "rb") as f:
        while chunk := f.read(1024):
            await ws.send(chunk)
    # Signal end of audio
    await ws.send(b"")

async def _collect_tts(ws, output_path):
    """Collect binary TTS frames from the WebSocket and write to a WAV file."""
    tts_data = bytearray()
    try:
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            if isinstance(msg, bytes):
                tts_data.extend(msg)
            else:
                continue
    except asyncio.TimeoutError:
        pass
    pathlib.Path(output_path).write_bytes(tts_data)
    print(f"TTS audio saved to {output_path}")

async def translate_file(host="localhost", port=8000, target="Tamil"):
    ws_url = f"ws://{host}:{port}/ws/translate-auto?target={target}"
    async with websockets.connect(ws_url) as ws:
        # receive initial status
        print("Server:", await ws.recv())

        # stream audio
        await _stream_audio(ws, AUDIO_PCM)

        # collect TTS
        await _collect_tts(ws, OUTPUT_WAV)

# Run the translate_file function when this script is executed directly
if __name__ == "__main__":
    asyncio.run(translate_file())
