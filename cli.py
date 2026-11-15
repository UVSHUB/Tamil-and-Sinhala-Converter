"""
Command-line client for the SinTam (Sinhala <-> Tamil) translation backend.

Examples (run from this folder):
    python cli.py --run-backend                                  # translate the bundled Sinhala speech sample
    python cli.py --run-backend --audio my_speech.mp3 --target Tamil --play
    python cli.py --run-backend my_speech.mp3                    # pass .mp3 / .wav / .m4a / .ogg file path directly
    python cli.py --run-backend --mic --play                     # speak live into microphone ("normal voice")
    python cli.py --run-backend --text "ආයුබෝවන්, ඔබට කොහොමද?"
    python cli.py --run-backend --interactive                    # interactive prompt for .mp3/.wav file, 'mic', or text
    python cli.py --host 127.0.0.1 --port 8000 my_speech.mp3     # use a backend that is already running
"""

import argparse
import asyncio
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
GITHUB_ZIP_URL = "https://github.com/UVSHUB/Tamil-and-Sinhala-Converter/archive/refs/heads/main.zip"


def _ensure_project_files() -> str:
    """If cli.py is run standalone without backend/ or translate_client.py, download them from GitHub."""
    if os.path.isfile(os.path.join(HERE, "translate_client.py")) and os.path.isfile(os.path.join(HERE, "backend", "main.py")):
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        return HERE

    cache_root = os.path.join(os.path.expanduser("~"), ".sintam_project")
    project_dir = os.path.join(cache_root, "Tamil-and-Sinhala-Converter-main")
    if not os.path.isfile(os.path.join(project_dir, "backend", "main.py")):
        print("Downloading SinTam backend & client from GitHub (UVSHUB/Tamil-and-Sinhala-Converter) ...")
        os.makedirs(cache_root, exist_ok=True)
        with urllib.request.urlopen(GITHUB_ZIP_URL, timeout=60) as resp:
            zip_bytes = resp.read()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(cache_root)
        print(f"Downloaded project to: {project_dir}")
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    return project_dir


HERE = _ensure_project_files()
BACKEND_LOG = os.path.join(HERE, "backend.log")
REQUIRED_MODULES = ["websockets", "fastapi", "uvicorn", "google.genai", "pydantic_settings"]

# Sinhala / Tamil text must not crash the Windows console (cp1252)
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _ensure_dependencies() -> None:
    """Ensure required Python packages are installed before importing translate_client."""
    def _is_installed(mod: str) -> bool:
        try:
            return importlib.util.find_spec(mod) is not None
        except ModuleNotFoundError:
            return False

    missing = [m for m in REQUIRED_MODULES if not _is_installed(m)]
    if not missing:
        return
    req_file = os.path.join(HERE, "requirements.txt")
    if not os.path.isfile(req_file):
        req_file = os.path.join(HERE, "..", "requirements.txt")
    print(f"Installing missing Python packages ({', '.join(missing)}) ...")
    cmd = [sys.executable, "-m", "pip", "install", "-r", req_file] if os.path.isfile(req_file) else [
        sys.executable, "-m", "pip", "install", "websockets", "fastapi", "uvicorn[standard]", "google-genai", "pydantic-settings", "structlog"
    ]
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise RuntimeError(
            f"Package installation failed. Run manually:\n  {sys.executable} -m pip install -r requirements.txt"
        )


_ensure_dependencies()
import translate_client  # noqa: E402


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


def _resolve_port(host: str, requested_port: int) -> int:
    """Return `requested_port` if it is free; otherwise pick the next free port."""
    if not _port_in_use(host, requested_port):
        return requested_port
    for candidate in range(requested_port + 1, requested_port + 50):
        if not _port_in_use(host, candidate):
            print(f"Port {requested_port} is in use - automatically starting fresh backend on port {candidate}.")
            return candidate
    raise RuntimeError(f"Port {requested_port} is in use and no free port was found nearby.")


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
    if not env.get("GEMINI_API_KEY") or env.get("GEMINI_API_KEY") == "your_gemini_api_key_here":
        print("No GEMINI_API_KEY found in .env or environment.")
        print("Get a free key at https://aistudio.google.com/apikey and paste it below:")
        try:
            entered_key = input("GEMINI_API_KEY = ").strip()
        except (EOFError, KeyboardInterrupt):
            entered_key = ""
        if entered_key:
            env["GEMINI_API_KEY"] = entered_key
            env_path = os.path.join(HERE, ".env")
            existing_lines = []
            if os.path.isfile(env_path):
                with open(env_path, encoding="utf-8") as ef:
                    existing_lines = [l for l in ef.read().splitlines() if not l.strip().startswith("GEMINI_API_KEY=")]
            existing_lines.insert(0, f"GEMINI_API_KEY={entered_key}")
            with open(env_path, "w", encoding="utf-8") as ef:
                ef.write("\n".join(existing_lines) + "\n")
            print(f"Saved GEMINI_API_KEY to {env_path}")
        else:
            print("WARNING: GEMINI_API_KEY not provided - "
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

def _looks_like_audio_path(value: str) -> bool:
    """Return True if value looks like an audio file path (.mp3/.wav/.m4a/.ogg/.flac/.pcm/etc.) or exists on disk."""
    cleaned = value.strip().strip('"').strip("'").strip()
    if cleaned.lower().endswith(translate_client.AUDIO_EXTENSIONS):
        return True
    resolved = translate_client.resolve_audio_path(cleaned)
    return os.path.isfile(resolved)


def _parse_mic_command(raw: str) -> tuple[bool, float | None]:
    """Return (True, optional_seconds) if the user typed 'mic', 'voice', or 'record [seconds]'."""
    parts = raw.strip().split()
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Client for the Sinhala <-> Tamil real-time translation backend (supports MP3, WAV, M4A, OGG, FLAC, live microphone voice, and text).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("input", nargs="?", default=None,
                   help="Optional audio file path (.mp3, .wav, .m4a, .ogg, .flac, .pcm, etc.), 'mic', or text phrase to translate")
    p.add_argument("--host", default="127.0.0.1", help="Backend host")
    p.add_argument("--port", type=int, default=8000, help="Backend port")
    p.add_argument("--run-backend", action="store_true", help="Start the backend first and stop it afterwards")
    p.add_argument("--audio", "--wav", "--mp3", dest="audio", default=None,
                   help="Audio file to translate (.mp3, .wav, .m4a, .aac, .ogg, .opus, .flac, .webm, .pcm, etc.)")
    p.add_argument("--mic", "--voice-input", dest="mic", action="store_true",
                   help="Record live normal voice from the microphone and translate it")
    p.add_argument("--record-seconds", "--duration", dest="record_seconds", type=float, default=None,
                   help="Seconds to record from microphone when using --mic (omit to press Enter when done speaking)")
    p.add_argument("--text", default=None, help="Translate this text instead of an audio file")
    p.add_argument("--interactive", "-i", action="store_true",
                   help="Interactive terminal prompt: enter an audio file (.mp3/.wav/.m4a), 'mic' for live voice, or text")
    p.add_argument("--source", default="Sinhala", help="Source language (text mode; audio mode auto-detects)")
    p.add_argument("--target", default="Tamil", choices=["Tamil", "Sinhala"], help="Output language")
    p.add_argument("--voice", default="Aoede", choices=["Aoede", "Charon", "Kore", "Puck", "Fenrir"],
                   help="Voice for the translated speech")
    p.add_argument("--output", "-o", default="output.wav",
                   help="Where to save the translated speech (.wav, .mp3, .m4a, .flac, etc.)")
    p.add_argument("--play", action="store_true", help="Play the translated speech audio through speakers")
    p.add_argument("--api-key", default=os.environ.get("SINTAM_API_KEY", ""),
                   help="API key, needed only if the server has no GEMINI_API_KEY (env: SINTAM_API_KEY)")
    p.add_argument("--timeout", type=float, default=45.0, help="Seconds to wait for the server's reply")
    return p


def _run_interactive_loop(args) -> int:
    print("Interactive Mode:")
    print("  • Enter an audio file path (.mp3, .wav, .m4a, .ogg, .flac, .aac, .pcm, etc.)")
    print("  • Type 'mic' (or 'voice' / 'record 5') to speak live with your normal voice")
    print("  • Or type Sinhala/Tamil text directly")
    print("  • Type 'exit' or 'quit' to stop.\n")
    turn_idx = 0
    while True:
        try:
            raw = input("Enter audio file (.mp3/.wav), 'mic', or text > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        if raw.lower() in ("exit", "quit"):
            break

        turn_idx += 1
        base, ext = os.path.splitext(args.output)
        out_path = args.output if turn_idx == 1 else f"{base}_{turn_idx}{ext or '.wav'}"

        is_mic, mic_duration = _parse_mic_command(raw)
        if is_mic:
            rec_path = os.path.join(HERE, f"recorded_voice_{turn_idx}.wav")
            try:
                translate_client.record_microphone_audio(
                    duration=mic_duration if mic_duration is not None else args.record_seconds,
                    output_wav=rec_path,
                )
            except Exception as exc:
                print(f"Microphone recording error: {exc}\n")
                continue
            print("-" * 60)
            asyncio.run(translate_client.translate_audio(
                rec_path, output_path=out_path, host=args.host, port=args.port,
                target=args.target, voice=args.voice, api_key=args.api_key,
                timeout=args.timeout, play=args.play,
            ))
            print("-" * 60 + "\n")
        elif _looks_like_audio_path(raw):
            audio_path = translate_client.resolve_audio_path(raw)
            if not os.path.isfile(audio_path):
                print(f"Audio file not found: {raw}\n")
                continue
            print("-" * 60)
            asyncio.run(translate_client.translate_audio(
                audio_path, output_path=out_path, host=args.host, port=args.port,
                target=args.target, voice=args.voice, api_key=args.api_key,
                timeout=args.timeout, play=args.play,
            ))
            print("-" * 60 + "\n")
        else:
            print("-" * 60)
            asyncio.run(translate_client.translate_text(
                raw, host=args.host, port=args.port, source=args.source, target=args.target,
                voice=args.voice, api_key=args.api_key, timeout=args.timeout,
                output_path=out_path, play=args.play,
            ))
            print("-" * 60 + "\n")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # Resolve positional input if given
    if args.input and args.audio is None and args.text is None and not args.mic:
        is_mic, mic_secs = _parse_mic_command(args.input)
        if is_mic:
            args.mic = True
            if mic_secs is not None and args.record_seconds is None:
                args.record_seconds = mic_secs
        elif _looks_like_audio_path(args.input):
            args.audio = args.input
        else:
            args.text = args.input

    # Default to bundled sample_sinhala.wav / sample_sinhala.pcm when neither audio nor text nor mic nor interactive is given
    if args.audio is None and args.text is None and not args.mic and not args.interactive:
        default_wav = os.path.join(HERE, "sample_sinhala.wav")
        default_pcm = os.path.join(HERE, "sample_sinhala.pcm")
        args.audio = default_wav if os.path.isfile(default_wav) else default_pcm

    if not args.interactive and not args.mic:
        if args.text is None:
            resolved_audio = translate_client.resolve_audio_path(args.audio)
            if not os.path.isfile(resolved_audio):
                print(f"Audio file not found: {args.audio}")
                return 2
            args.audio = resolved_audio
        elif args.source.lower() == args.target.lower():
            print("--source and --target must be different languages.")
            return 2

    backend = None
    try:
        if args.run_backend:
            args.port = _resolve_port(args.host, args.port)
            backend = start_backend(args.host, args.port)
        elif not _health(args.host, args.port):
            if args.host in ("127.0.0.1", "localhost"):
                args.port = _resolve_port(args.host, args.port)
                backend = start_backend(args.host, args.port)
            else:
                print(f"No backend at http://{args.host}:{args.port}. Start one, or add --run-backend.")
                return 1

        if args.interactive:
            return _run_interactive_loop(args)

        if args.mic:
            rec_path = os.path.join(HERE, "recorded_voice.wav")
            translate_client.record_microphone_audio(duration=args.record_seconds, output_wav=rec_path)
            args.audio = rec_path

        print("-" * 60)
        if args.text is not None:
            session = asyncio.run(translate_client.translate_text(
                args.text, host=args.host, port=args.port, source=args.source, target=args.target,
                voice=args.voice, api_key=args.api_key, timeout=args.timeout,
                output_path=args.output, play=args.play,
            ))
        else:
            session = asyncio.run(translate_client.translate_audio(
                args.audio, output_path=args.output, host=args.host, port=args.port,
                target=args.target, voice=args.voice, api_key=args.api_key,
                timeout=args.timeout, play=args.play,
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
