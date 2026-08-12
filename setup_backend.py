import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
VENV_DIR = ROOT_DIR / ".venv"
REQUIREMENTS_FILE = ROOT_DIR / "requirements.txt"
ENV_EXAMPLE_FILE = ROOT_DIR / ".env.example"
ENV_FILE = ROOT_DIR / ".env"


def run_command(command, cwd=None, check=True):
    print(f"> Running: {' '.join(command)}")
    subprocess.run(command, cwd=cwd or ROOT_DIR, check=check)


def create_virtualenv():
    if VENV_DIR.exists():
        print(f"Virtual environment already exists at {VENV_DIR}")
        return

    print("Creating virtual environment in .venv...")
    python_candidates = [sys.executable]
    if os.name == "nt":
        python_candidates.extend(["python", "py", "python3"])
    else:
        python_candidates.extend(["python3", "python"])

    for candidate in python_candidates:
        try:
            run_command([candidate, "-m", "venv", str(VENV_DIR)])
            print(f"Created virtual environment using: {candidate}")
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    raise RuntimeError(
        "Unable to create a virtual environment. Please install Python 3.11+ and ensure it is available on your PATH."
    )


def get_venv_python():
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def install_requirements():
    python_executable = get_venv_python()
    if not python_executable.exists():
        raise RuntimeError("Python executable not found inside virtual environment.")

    print("Upgrading pip inside the virtual environment...")
    run_command([str(python_executable), "-m", "pip", "install", "--upgrade", "pip"])

    print("Installing backend dependencies from requirements.txt...")
    if not REQUIREMENTS_FILE.exists():
        raise FileNotFoundError("requirements.txt not found in repository root.")
    run_command([str(python_executable), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)])


def ensure_env_file():
    if ENV_FILE.exists():
        print(f"Environment file already exists: {ENV_FILE}")
        return

    if not ENV_EXAMPLE_FILE.exists():
        raise FileNotFoundError(".env.example file is missing. Cannot generate .env automatically.")

    print("Copying .env.example to .env...")
    shutil.copy(ENV_EXAMPLE_FILE, ENV_FILE)
    print(
        "Created .env from .env.example.\n" 
        "Please open .env and configure GEMINI_API_KEY before running the backend."
    )


def run_backend():
    python_executable = get_venv_python()
    if not python_executable.exists():
        raise RuntimeError("Python executable not found inside virtual environment.")

    print("Starting FastAPI backend with Uvicorn...")
    run_command([
        str(python_executable),
        "-m",
        "uvicorn",
        "backend.main:app",
        "--reload",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ])


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bootstrap the backend for the Tamil ↔ Sinhala translator project."
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the backend after setup.",
    )
    parser.add_argument(
        "--no-env-copy",
        action="store_true",
        help="Do not copy .env.example to .env automatically.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    create_virtualenv()
    install_requirements()
    if not args.no_env_copy:
        ensure_env_file()

    print("\nBackend setup completed successfully.")
    print("To start the backend later, run: python setup_backend.py --run")

    if args.run:
        run_backend()


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(f"Command failed with exit code {error.returncode}: {error}")
        sys.exit(error.returncode)
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
