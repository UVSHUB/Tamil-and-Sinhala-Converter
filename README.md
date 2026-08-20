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

## 🏬 Real-Time Voice Translator Application

A production-ready, low-latency, bidirectional real-time speech-to-speech translator application powered by the **Google Gemini Live API (Multimodal Bidirectional WebSocket)**.

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
