import subprocess
import sys
import time
import os

def start_backend():
    """Start the FastAPI backend as a subprocess."""
    cmd = [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Wait a few seconds for the server to be ready
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

def run_client():
    """Run the CLI client (cli.py) which will handle dummy audio creation etc."""
    cmd = [sys.executable, "cli.py"]
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    print("Starting backend server...")
    backend_proc = start_backend()
    print("Backend started.")
    try:
        run_client()
    finally:
        print("Shutting down backend server...")
        stop_backend(backend_proc)
        print("Backend stopped.")
