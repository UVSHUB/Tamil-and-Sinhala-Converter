"""
Command-line client for the SinTam (Sinhala <-> Tamil) translation backend.

Examples (run from this folder):
    python cli.py --run-backend                                  # translate the bundled Sinhala speech sample
    python cli.py --run-backend --audio my_speech.wav --target Sinhala
    python cli.py --run-backend --text "ආයුබෝවන්, ඔබට කොහොමද?"
    python cli.py --host 127.0.0.1 --port 8000                   # use a backend that is already running
"""

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import translate_client

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_LOG = os.path.join(HERE, "backend.log")

# Sinhala / Tamil text must not crash the Windows console (cp1252)
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Backend process management
# ──────────────────────────────────────────────────────────────────────────────

def _read_env_file() -> dict:
    """Read KEY=VALUE pairs from .env in this folder, or the repository root above it."""
    for path in (os.path.join(HERE, ".env"), os.path.join(HERE, "..", ".env")):
        if os.path.isfile(path):
            values = {}
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        values[key.strip()] = value.strip().strip('"').strip("'")
            return values
    return {}


def _health(host: str, port: int) -> dict | None:
    """Return the backend health JSON, or None if it is not reachable."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/v1/health", timeout=2) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def _log_tail(lines: int = 15) -> str:
    try:
        with open(BACKEND_LOG, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-lines:])
    except OSError:
        return ""


def start_backend(host: str, port: int, wait: float = 60.0):
    """Start the FastAPI backend on host:port and wait until /api/v1/health answers.

    Returns the Popen object, or None if a backend was already running there."""
    if _health(host, port):
        print(f"A backend is already running at http://{host}:{port} - using it.")
        return None
    if _port_in_use(host, port):
        raise RuntimeError(f"Port {port} is in use by another program. Pick another one with --port.")

    env = os.environ.copy()
    for key, value in _read_env_file().items():
        env.setdefault(key, value)  # real environment variables take precedence
    if not env.get("GEMINI_API_KEY"):
        print("WARNING: GEMINI_API_KEY not found in the environment or a .env file - "
              "the backend will reject connections unless you pass --api-key.")

    print(f"Starting backend on http://{host}:{port} (log: {BACKEND_LOG}) ...")
    log = open(BACKEND_LOG, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", host, "--port", str(port)],
        cwd=HERE,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    proc.log_file = log

    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            log.close()
            raise RuntimeError(f"Backend exited during startup (code {proc.returncode}):\n{_log_tail()}")
        health = _health(host, port)
        if health:
            print(f"Backend ready (Gemini configured: {health.get('gemini_live_configured')}).")
            return proc
        time.sleep(0.5)

    stop_backend(proc)
    raise RuntimeError(f"Backend did not become ready within {wait:.0f}s:\n{_log_tail()}")


def stop_backend(proc) -> None:
    """Terminate the backend subprocess started by start_backend()."""
    if proc is None:
        return
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    if getattr(proc, "log_file", None):
        proc.log_file.close()


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Client for the Sinhala <-> Tamil real-time translation backend.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--host", default="127.0.0.1", help="Backend host")
    p.add_argument("--port", type=int, default=8000, help="Backend port")
    p.add_argument("--run-backend", action="store_true", help="Start the backend first and stop it afterwards")
    p.add_argument("--audio", default=os.path.join(HERE, "sample_sinhala.pcm"),
                   help="Speech file to translate: .wav, or raw .pcm (16 kHz mono 16-bit)")
    p.add_argument("--text", default=None, help="Translate this text instead of an audio file")
    p.add_argument("--source", default="Sinhala", help="Source language (text mode; audio mode auto-detects)")
    p.add_argument("--target", default="Tamil", choices=["Tamil", "Sinhala"], help="Output language")
    p.add_argument("--voice", default="Aoede", choices=["Aoede", "Charon", "Kore", "Puck", "Fenrir"],
                   help="Voice for the translated speech")
    p.add_argument("--output", default="output.wav", help="Where to save the translated speech (WAV)")
    p.add_argument("--api-key", default=os.environ.get("SINTAM_API_KEY", ""),
                   help="API key, needed only if the server has no GEMINI_API_KEY (env: SINTAM_API_KEY)")
    p.add_argument("--timeout", type=float, default=45.0, help="Seconds to wait for the server's reply")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.text is None and not os.path.isfile(args.audio):
        print(f"Audio file not found: {args.audio}")
        return 2
    if args.text is not None and args.source.lower() == args.target.lower():
        print("--source and --target must be different languages.")
        return 2

    backend = None
    try:
        if args.run_backend:
            backend = start_backend(args.host, args.port)
        elif not _health(args.host, args.port):
            print(f"No backend at http://{args.host}:{args.port}. Start one, or add --run-backend.")
            return 1

        print("-" * 60)
        if args.text is not None:
            session = asyncio.run(translate_client.translate_text(
                args.text, host=args.host, port=args.port, source=args.source, target=args.target,
                voice=args.voice, api_key=args.api_key, timeout=args.timeout, output_path=args.output,
            ))
        else:
            session = asyncio.run(translate_client.translate_audio(
                args.audio, output_path=args.output, host=args.host, port=args.port,
                target=args.target, voice=args.voice, api_key=args.api_key, timeout=args.timeout,
            ))
        print("-" * 60)

        if session.closed_reason and not session.translations:
            print(f"Server closed the connection ({session.closed_reason}).")
            if "1008" in session.closed_reason:
                print("This means the API key was rejected: set GEMINI_API_KEY in .env or pass --api-key.")
            return 1
        if not session.translations:
            print(f"No translation received within {args.timeout:.0f}s. "
                  f"Check {BACKEND_LOG if args.run_backend else 'the backend log'} for errors.")
            return 1
        print("Done.")
        return 0

    except RuntimeError as err:
        print(f"ERROR: {err}")
        return 1
    except (ConnectionRefusedError, OSError) as err:
        print(f"ERROR: could not connect to the backend: {err}")
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    finally:
        if backend is not None:
            print("Stopping backend ...")
            stop_backend(backend)


if __name__ == "__main__":
    sys.exit(main())
