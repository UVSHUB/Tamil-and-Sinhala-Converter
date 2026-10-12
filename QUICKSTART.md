# Getting Started With SinTam Voice Translator

A beginner-friendly quickstart guide to get the **Sinhala ↔ Tamil Real-Time Voice Translator** up and running on your own machine in under 3 minutes.

---

## 📋 Prerequisites

Before getting started, make sure you have:
- **Python 3.10** or newer installed ([python.org](https://www.python.org/downloads/))
- **Node.js 18+** (Optional, only needed if modifying frontend code)
- A free **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com/)

---

## 🛠️ Setting Up Your Project

Clone the repository and install the backend dependencies in an isolated virtual environment:

```bash
# 1. Clone the repository
git clone https://github.com/UVSHUB/Tamil-and-Sinhala-Converter.git
cd Tamil-and-Sinhala-Converter

# 2. Create and activate a Python virtual environment
# On Windows:
python -m venv .venv
call .venv\Scripts\activate.bat

# On macOS / Linux:
# python3 -m venv .venv
# source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## ⚙️ Environment Configuration

Create a `.env` file in the project root directory (same folder as `requirements.txt`):

```ini
# Google Gemini API Key (Required)
GEMINI_API_KEY=your_actual_gemini_api_key_here

# Fast, verified models
TRANSLATE_MODEL=gemini-3.5-flash-lite
TTS_MODEL=gemini-3.8-flash-lite-tts
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
ALLOWED_ORIGINS=*
```

---

## 🚀 Running the Application

### Option A: 1-Click Launch (Windows)
Double-click **`start_app.bat`** in the project folder.  
It automatically starts the backend and frontend servers, and opens the app in your default browser at `http://localhost:8000`.

### Option B: Terminal Command (All Platforms)
Start the FastAPI WebSocket server directly:

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see:
```text
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## 🧪 Testing with `test_translator.py`

You can verify the backend programmatically without opening a browser using the included test script:

```bash
python test_translator.py
```

### What `test_translator.py` does:
1. Connects to `ws://localhost:8000/ws/translate-auto?target=Tamil`.
2. Validates the WebSocket handshake and engine status.
3. Tests dynamic runtime language switching (toggling target output to Sinhala).
4. Confirms ready state.

### Expected Output:
```text
[CONNECTING] Connecting to ws://localhost:8000/ws/translate-auto?target=Tamil...
[CONNECTED] WebSocket connection established successfully!

[SERVER] {"type":"status","payload":{"message":"Continuous Stream Engine Active! Target: Tamil. Listening non-stop; translates every ~3.0s continuously."}}
[LANG]   {"type":"lang_detected","payload":{"source":"Auto-Detect","target":"Tamil"}}

>>> Sending request to switch output language to Sinhala...
[SERVER] {"type":"status","payload":{"message":"Output language switched to Sinhala"}}

✓ Verification Successful! The translation backend is fully operational.
```

---

## 🌐 Using the Web Interface

1. Open **[http://localhost:8000](http://localhost:8000)** in your browser.
2. Select your desired output language (**Tamil** or **Sinhala**).
3. Click the **Start** button and speak into your microphone in Sinhala, Tamil, or English.
4. The system will detect your input language, display the translation, and speak it aloud automatically!
