# Sinhala ↔ Tamil Translation & Conversion Suite

A production-grade, modular toolkit for **Sinhala ↔ Tamil** bidirectional translation. This repository provides:
1. **`sinhala-tamil-converter` Python Package**: A clean, modular library that developers can install and import into their own Python applications in 2–3 lines.
2. **Real-time AI Voice Translator**: FastAPI + React 19 + Gemini Live WebSocket streaming platform.
3. **Asterisk Telephony AudioSocket Bridge**: Real-time SIP telephony speech-to-speech translation gateway.

---

## 📦 Python Package (`sinhala-tamil-converter`)

The modular package is located under `src/sinhala_tamil_converter/` and can be installed into any Python environment.

### Installation

```bash
# Install directly in editable development mode
pip install -e .

# Or install with development and testing dependencies
pip install -e ".[dev]"
```

### ⚡ 2–3 Line Quickstart Usage

#### 1. Convenience Translation Functions
```python
from sinhala_tamil_converter import translate_sinhala_to_tamil, translate_tamil_to_sinhala

# Translate Sinhala to Tamil
tamil_text = translate_sinhala_to_tamil("ආයුබෝවන්, ඔබට කොහොමද?")
print(tamil_text)  # வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?

# Translate Tamil to Sinhala
sinhala_text = translate_tamil_to_sinhala("வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?")
print(sinhala_text)  # ආයුබෝවන්, ඔබට කොහොමද?
```

#### 2. Auto-Detection & Translation
```python
from sinhala_tamil_converter import auto_translate

result = auto_translate("සුභ උදෑසනක්")
print(f"[{result.source_language} -> {result.target_language}]: {result.text}")
# [sinhala -> tamil]: காலை வணக்கம்
```

#### 3. Object-Oriented Client (Custom API Key / Async / Batch)
```python
import asyncio
from sinhala_tamil_converter import SinhalaTamilConverter

async def main():
    converter = SinhalaTamilConverter(api_key="YOUR_GEMINI_API_KEY")
    results = await converter.batch_translate_async(
        ["ස්තූතියි", "සුභ රාත්‍රියක්"],
        source="sinhala",
        target="tamil"
    )
    for res in results:
        print(res.text)

asyncio.run(main())
```

#### 4. Command-Line Interface (CLI)
Once installed, use `st-convert` directly in your terminal:
```bash
st-convert "ආයුබෝවන්" --target tamil
st-convert "வணக்கம்" --target sinhala
```

---

## 📁 Repository Folder Tree

```text
.
├── pyproject.toml                  # PEP 621 Python package & build metadata
├── setup.py                        # Fallback setup configuration
├── requirements.txt                # Core backend & library dependencies
├── requirements-dev.txt            # Dev/testing dependencies (pytest, ruff)
├── src/
│   └── sinhala_tamil_converter/     # 📦 Modular Python Library
│       ├── __init__.py             # Exports: translate_sinhala_to_tamil, auto_translate, etc.
│       ├── converter.py            # Core SinhalaTamilConverter class
│       ├── models.py               # Language enum & TranslationResult model
│       ├── exceptions.py           # Custom exception hierarchy
│       ├── cli.py                  # CLI runner (st-convert)
│       └── backends/               # Translation backend providers
│           ├── base.py             # Abstract Base Backend interface
│           └── gemini.py           # Google GenAI / Gemini backend
├── tests/                          # Package unit test suite
│   └── test_converter.py           # Tests for translation, detection, batch & async
├── examples/                       # Quickstart Python example scripts
│   └── quickstart.py
├── backend/                        # FastAPI WebSocket & REST Server
│   ├── asterisk/                   # Asterisk AudioSocket bridge
│   ├── config/                     # Settings & environment loaders
│   ├── websocket/                  # Stream & Auto-stream WebSocket handlers
│   └── main.py                     # FastAPI entry point
├── frontend/                       # React 19 + Vite + Tailwind Frontend
├── docker/                         # Docker & Asterisk PBX configurations
└── docker-compose.yml
```

---

## 🧪 Running Unit Tests

```bash
# Run all package and backend test suites
pytest
```

---

## 👥 Architecture & Team Distribution

To ensure efficient workspace distribution, responsibilities are divided into three areas:

### 1. **Student A (Frontend & Audio Specialist)**
*   **Scope**: Frontend folder (`frontend/src/`) and visual packages.
*   **Key Deliverables**:
    *   Web Audio mic capture using `Recorder` and Web Workers for background conversion.
    *   Audio downsampling (`frontend/src/audio/downsampler.ts`) to produce 16kHz PCM data.
    *   WebSocket reconnect driver (`frontend/src/websocket/client.ts`).
    *   React state synchronization inside `TranslationContext.tsx`.

### 2. **Student B (Backend & AI Specialist)**
*   **Scope**: Backend folder (`backend/`) and Gemini API connections.
*   **Key Deliverables**:
    *   FastAPI websocket route handling.
    *   Bidirectional audio streams inside `backend/websocket/stream_handler.py`.
    *   Gemini Live client logic inside `backend/gemini/client.py` using system instructions.
    *   Pydantic configurations setup inside `backend/config/settings.py`.

### 3. **Student C (DevOps & Infrastructure Lead)**
*   **Scope**: Configuration, proxy networks, Docker, shell scripts, and workflows.
*   **Key Deliverables**:
    *   Root setup scripts (`scripts/setup.sh`) and container mappings (`docker-compose.yml`).
    *   Reverse proxy setups at `docker/nginx/nginx.conf` supporting WebSocket connections.
    *   CI/CD pipelines inside `.github/workflows/`.
    *   Comprehensive tests execution setup in `backend/tests/`.

---

## 🚀 Quick Start Guide

### 1. 1-Click Automated Launch (Windows Non-Technical Users)
For users without terminal experience, we have provided an automated startup script. Just double-click **`start_app.bat`** at the project root. It will automatically check dependencies, set up environments, and launch both the backend and frontend servers in the background. *(See `Non-Technical-Setup-Guide.md` for more details).*

### 2. One-step Backend Bootstrap
A new contributor can set up the backend using only Python from the repository root:
```bash
python setup_backend.py
```
This will:
- create a `.venv` virtual environment,
- install backend dependencies from `requirements.txt`,
- copy `.env.example` to `.env` if no `.env` exists.

To install and immediately run the backend:
```bash
python setup_backend.py --run
```

> After first setup, open `.env` and set `GEMINI_API_KEY` before starting the backend.

### 2. Configure Local Environment variables
Copy the template variables file and add your Google Studio credentials:
```bash
cp .env.example .env
```
Open `.env` and fill in:
`GEMINI_API_KEY=AIzaSy...`

### 3. Standard Local Run (No Containerization)
Ensure Python 3.11+ and Node 20+ are installed locally.

**Start the Backend**:
```bash
# Installs dependencies and launches FastAPI on port 8000
npm run dev:backend
```

**Start the Frontend**:
```bash
# Install NPM packages
cd frontend && npm install
# Start local Vite development server
npm run dev
```
Open browser to `http://localhost:5173`.

### 4. Running with Docker Compose (Recommended)
Run the entire production stack (FastAPI Backend, React Nginx Frontend, and Nginx proxy balancer) with a single command:
```bash
npm run docker:up
```
Open browser to `http://localhost`. The Nginx reverse proxy routes REST requests to the backend container and static pages to the frontend container automatically.

To stop the containers:
```bash
npm run docker:down
```

---

## 🏬 Real-Time Voice Translator Application

A production-ready, low-latency, bidirectional real-time speech-to-speech translator application powered by the **Google Gemini Live API (Multimodal Bidirectional WebSocket)**.

### ✨ New Features
*   **Fine-Tuned AI Persona:** Custom system prompts give Gemini a strict Sri Lankan call-center persona, with explicit rules for gracefully translating **Singlish (Sinhala+English)** and Tanglish loanwords.
*   **Active Noise Gate (DSP):** Built-in WebRTC AudioWorklet noise suppression prevents ambient room static from accidentally triggering AI translation sessions.
*   **Smart Speech Visualizer:** The UI waveform intelligently detects the human voice frequency floor, remaining in a smooth idle state until active speech is recognized.

### Universal Package Install (Run Anywhere)
If you want to run the application on any PC with Python installed without using Docker, you can install the entire application (Frontend + Backend bundled) as a global CLI command:
```bash
pip install git+https://github.com/UVSHUB/Tamil-and-Sinhala-Converter.git
sintam
```
This will automatically download the dependencies, start the backend server, and serve the React application on `http://localhost:8000`.

### Local Development Run

Ensure Python 3.11+ and Node 20+ are installed.

1. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   # Edit .env and set GEMINI_API_KEY
   ```

2. **Start Backend & Frontend**:
   ```bash
   # Backend (Port 8000)
   npm run dev:backend

   # Frontend (Port 5173)
   cd frontend && npm install && npm run dev
   ```

3. **Running with Docker Compose**:
   ```bash
   npm run docker:up
   ```

---

## 📞 Asterisk PBX Telephony Integration

The platform includes built-in **Asterisk PBX integration**, allowing phone callers (SIP softphones or IP desk phones) to dial extension `8000` to translate live speech between Sinhala and Tamil in real time.
