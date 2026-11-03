import argparse
import asyncio
import os
import subprocess
import sys
import time
from translate_client import translate_file
import translate_client

def start_backend():
    """Start the FastAPI backend as a subprocess.
    Returns the subprocess.Popen object.
    """
    cmd = [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Give the server a moment to start
    time.sleep(3)
    return proc

def stop_backend(proc):
    """Terminate the backend subprocess gracefully."""
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

def main():
    parser = argparse.ArgumentParser(description="CLI for Tamil/Sinhala translation client")
    parser.add_argument("--host", default="localhost", help="Server host (default: localhost)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--target", default="Tamil", help="Target language (default: Tamil)")
    parser.add_argument("--audio", default="sample.pcm", help="Path to PCM audio file (default: sample.pcm)")
    parser.add_argument("--output", default="output.wav", help="Path to save TTS WAV file (default: output.wav)")
    parser.add_argument("--run-backend", action="store_true", help="Start the backend server before running the client")
    parser.add_argument("--no-dummy", action="store_true", help="Do not create a dummy PCM file if missing")
    args = parser.parse_args()

    # Ensure the audio file exists – create a short silent PCM if missing (unless disabled)
    if not args.no_dummy and not os.path.isfile(args.audio):
        print(f"Audio file '{args.audio}' not found. Creating a dummy 1‑second silent PCM.")
        # 16 kHz, mono, 16‑bit PCM => 16000 samples * 2 bytes = 32000 bytes of zeros
        with open(args.audio, "wb") as dummy:
            dummy.write(b"\x00" * 32000)
        print(f"Dummy audio file '{args.audio}' created.")

    backend_proc = None
    if args.run_backend:
        print("Starting backend server...")
        backend_proc = start_backend()
        print("Backend started.")

    # Override constants in translate_client so translate_file uses the provided paths
    translate_client.AUDIO_PCM = args.audio
    translate_client.OUTPUT_WAV = args.output

    try:
        asyncio.run(translate_file(host=args.host, port=args.port, target=args.target))
    finally:
        if backend_proc:
            print("Shutting down backend server...")
            stop_backend(backend_proc)
            print("Backend stopped.")

if __name__ == "__main__":
    main()
