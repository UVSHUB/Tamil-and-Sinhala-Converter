# SinTam Client — How to Run

Command-line client for the Sinhala ↔ Tamil real-time translation backend.
It sends speech (or text) to the backend over WebSocket, prints the transcription
and translation, and saves the translated speech as a WAV file.

## 1. Setup (once)

Requires **Python 3.10+** and a Google Gemini API key.

```bash
cd "cl&docs"                       # quotes are needed because of the '&'
python -m venv .venv
.venv\Scripts\activate             # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r backend/requirements.txt
```

Create a file named `.env` in this folder containing your key:

```
GEMINI_API_KEY=your_key_here
```

(If this folder sits inside the full repository, the repository's `.env` is used automatically.)

## 2. Run

```bash
python run_all.py
```

This starts the backend, streams the bundled Sinhala speech sample (`sample_sinhala.pcm`),
prints the result, saves the Tamil speech to `output.wav`, and stops the backend. Expected output
(the transcription may vary slightly between runs):

```
Backend ready (Gemini configured: True).
  You said (Sinhala): ආයුබෝවන්
  Translation: வணக்கம்
  You said (Sinhala): මට මගේ ක්‍රෙඩිට් කාඩ් බිල්පත ගැන දැනගන්න ඕනේ.
  Translation: எனது கிரெடிட் கார்டு பில் பற்றி தெரிந்து கொள்ள வேண்டும்.
Saved       : output.wav (4.3s of translated speech)
Done.
```

### More examples

```bash
# Text translation, both directions
python run_all.py --text "ආයුබෝවන්, ඔබට කොහොමද?"
python run_all.py --text "வணக்கம்" --source Tamil --target Sinhala

# Your own recording (any 16-bit WAV, or raw 16 kHz mono .pcm); output in Sinhala
python run_all.py --audio my_speech.wav --target Sinhala

# Use a backend that is already running (e.g. started with: python -m uvicorn backend.main:app)
python cli.py --host 127.0.0.1 --port 8000

# All options
python cli.py --help
```

## Short example: client code accessing the backend

`client_example.py` is a ~100-line, commented example showing how any Python program can use the
backend: it connects over WebSocket, sends text and speech, and receives the translation and voice.

```bash
python -m uvicorn backend.main:app --port 8000   # terminal 1: start the backend and leave it running
python client_example.py                          # terminal 2: run the client
```

## Files

| File | Purpose |
|---|---|
| `run_all.py` | One command: start backend → run client → stop backend |
| `cli.py` | Client command line; `--run-backend` starts the backend itself |
| `translate_client.py` | WebSocket client logic (audio and text modes) |
| `client_example.py` | Short commented example of client code accessing the backend |
| `sample_sinhala.pcm` | 4.4 s Sinhala speech sample (16 kHz mono 16-bit PCM) |
| `backend/` | FastAPI backend (Gemini speech translation + speech synthesis) |

## Troubleshooting

- **"Backend exited during startup"** — the last lines of `backend.log` are printed; usually a missing
  package (`pip install -r backend/requirements.txt`).
- **"Server closed the connection (code 1008)"** — no API key: create `.env` as in step 1.
- **"No translation received"** — check `backend.log`; HTTP 429 means the Gemini quota is exhausted, wait and retry.
- **"Port 8000 is in use"** — use another port: `python run_all.py --port 8010`.
