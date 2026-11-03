"""
SinTam — one command to run the whole project.

    python run_project.py

What it does, step by step:
  1. Checks Python (3.10+) and installs the Python packages if they are missing.
  2. Makes sure a Gemini API key is configured (asks for it once and saves it in .env).
  3. Builds the web app (needs Node.js) - only the first time, or after the frontend changes.
  4. Starts the backend server, which also serves the web app.
  5. Opens http://localhost:8000 in the browser. Press Ctrl+C to stop everything.

Options:
    python run_project.py --port 8010        use another port
    python run_project.py --no-browser       don't open the browser
    python run_project.py --rebuild          force a fresh web-app build
    python run_project.py --skip-frontend    backend only (API + WebSocket, no web page)
"""

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.join(ROOT, "frontend")
DIST_INDEX = os.path.join(FRONTEND, "dist", "index.html")
DIST_ASSETS = os.path.join(FRONTEND, "dist", "assets")
ENV_FILE = os.path.join(ROOT, ".env")
REQUIRED_MODULES = ["fastapi", "uvicorn", "websockets", "google.genai", "pydantic_settings"]

# Sinhala / Tamil text must not crash the Windows console
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def step(n: int, text: str) -> None:
    print(f"\n[{n}/5] {text}")


def fail(message: str) -> None:
    print(f"\nERROR: {message}")
    sys.exit(1)


# ── 1. Python and packages ────────────────────────────────────────────────────
def check_python_packages() -> None:
    if sys.version_info < (3, 10):
        fail(f"Python 3.10 or newer is required (you have {sys.version.split()[0]}). "
             "Download it from https://www.python.org/downloads/")
    def installed(module: str) -> bool:
        try:
            return importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:  # parent package (e.g. "google") missing
            return False

    missing = [m for m in REQUIRED_MODULES if not installed(m)]
    if not missing:
        print("      Python packages are installed.")
        return
    print(f"      Missing packages ({', '.join(missing)}) - installing from requirements.txt ...")
    result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", os.path.join(ROOT, "requirements.txt")])
    if result.returncode != 0:
        fail("Package installation failed. Run this command yourself to see the problem:\n"
             f"  {sys.executable} -m pip install -r requirements.txt")
    print("      Packages installed.")


# ── 2. Gemini API key ─────────────────────────────────────────────────────────
def read_env() -> dict:
    values = {}
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def ensure_api_key() -> None:
    key = os.environ.get("GEMINI_API_KEY") or read_env().get("GEMINI_API_KEY", "")
    if key and key != "your_gemini_api_key_here":
        print("      Gemini API key found.")
        return
    print("      No Gemini API key found.")
    print("      Get a free key at https://aistudio.google.com/apikey and paste it below.")
    try:
        key = input("      GEMINI_API_KEY = ").strip()
    except (EOFError, KeyboardInterrupt):
        key = ""
    if not key:
        fail("A Gemini API key is required. Put GEMINI_API_KEY=... in the .env file and run again.")
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if not l.strip().startswith("GEMINI_API_KEY=")]
    else:
        lines = []
    lines.insert(0, f"GEMINI_API_KEY={key}")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("      Saved to .env (keep this file private - never upload it).")


# ── 3. Web app build ──────────────────────────────────────────────────────────
def newest_source_change() -> float:
    newest = 0.0
    for folder in ("src",):
        for dirpath, _, files in os.walk(os.path.join(FRONTEND, folder)):
            for name in files:
                newest = max(newest, os.path.getmtime(os.path.join(dirpath, name)))
    for name in ("index.html", "package.json", "vite.config.ts", "tailwind.config.js"):
        path = os.path.join(FRONTEND, name)
        if os.path.isfile(path):
            newest = max(newest, os.path.getmtime(path))
    return newest


def build_frontend(force: bool) -> bool:
    """Build frontend/dist if needed. Returns True if a web app is available."""
    built = os.path.isfile(DIST_INDEX) and os.path.isdir(DIST_ASSETS)
    if built and not force and os.path.getmtime(DIST_INDEX) >= newest_source_change():
        print("      Web app is already built and up to date.")
        return True

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        if built:
            print("      Node.js not found - using the existing (older) web app build.")
            return True
        print("      Node.js is not installed, so the web app cannot be built.")
        print("      Install Node.js 20+ from https://nodejs.org and run again.")
        print("      Continuing with the backend only (the client code in cl&docs/ still works).")
        return False

    if not os.path.isdir(os.path.join(FRONTEND, "node_modules")):
        print("      Installing web app packages (npm install, first time only, ~1 minute) ...")
        if subprocess.run([npm, "install"], cwd=FRONTEND).returncode != 0:
            fail("npm install failed. Run 'npm install' inside the frontend folder to see why.")
    print("      Building the web app (npm run build, ~15 seconds) ...")
    if subprocess.run([npm, "run", "build"], cwd=FRONTEND).returncode != 0:
        fail("The web app build failed - see the messages above.")
    print("      Web app built.")
    return True


# ── 4. Backend server ─────────────────────────────────────────────────────────
def health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=2) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_backend(port: int) -> subprocess.Popen:
    if port_in_use(port):
        fail(f"Port {port} is already in use (maybe the project is already running in another window).\n"
             f"       Close it, or use another port:  python run_project.py --port {port + 10}")
    env = os.environ.copy()
    for key, value in read_env().items():
        env.setdefault(key, value)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            fail("The backend stopped during startup - see the error messages above.")
        info = health(port)
        if info:
            if not info.get("gemini_live_configured"):
                print("      WARNING: the backend did not pick up the Gemini API key.")
            return proc
        time.sleep(0.5)
    proc.terminate()
    fail("The backend did not start within 60 seconds.")


def stop_backend(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Run the whole SinTam project with one command.")
    parser.add_argument("--port", type=int, default=8000, help="Port for the server (default 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser")
    parser.add_argument("--rebuild", action="store_true", help="Force a fresh web-app build")
    parser.add_argument("--skip-frontend", action="store_true", help="Run the backend only")
    args = parser.parse_args()
    os.chdir(ROOT)

    print("=" * 62)
    print("   SinTam - Sinhala <-> Tamil Real-Time Voice Translator")
    print("=" * 62)

    step(1, "Checking Python and packages")
    check_python_packages()

    step(2, "Checking the Gemini API key")
    ensure_api_key()

    step(3, "Preparing the web app")
    has_ui = False if args.skip_frontend else build_frontend(args.rebuild)
    if args.skip_frontend:
        print("      Skipped (--skip-frontend).")

    step(4, f"Starting the server on port {args.port}")
    proc = start_backend(args.port)
    url = f"http://localhost:{args.port}"
    print("      Server is running.")

    step(5, "Ready!")
    if has_ui:
        print(f"      Open the translator:   {url}")
        print("      Click Start, allow the microphone, and speak Sinhala, Tamil or English.")
    print(f"      Health check:          {url}/api/v1/health")
    print(f"      WebSocket for clients: ws://localhost:{args.port}/ws/translate-auto")
    print(f"      Client code demo:      python run_all.py --port {args.port}   (in another terminal)")
    print("\n      Press Ctrl+C to stop.\n")
    if has_ui and not args.no_browser:
        webbrowser.open(url)

    try:
        while proc.poll() is None:
            time.sleep(0.5)
        print("\nThe server stopped unexpectedly - see the messages above.")
    except KeyboardInterrupt:
        print("\nStopping ...")
    finally:
        stop_backend(proc)
        print("Stopped. Goodbye!")


if __name__ == "__main__":
    main()
