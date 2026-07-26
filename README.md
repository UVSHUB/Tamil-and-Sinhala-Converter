# Real-time AI Sinhala ↔ Tamil Voice Translator

A production-ready, low-latency, bidirectional real-time speech-to-speech translator application. The platform converts live Sinhala speech into synthesized Tamil speech (and vice versa) utilizing the **Google Gemini Live API (Multimodal Bidirectional WebSocket)**.

---

## 🏬 Call-Center Problem & Business Case

* **Traditional Call Centers**: Require **500+ human translators** on payroll to support multi-lingual operations, costing millions of dollars annually.
* **Target Company Reality**: Employs only **2 to 3 human translators** while the majority of staff are **local Sinhala speakers** receiving high volumes of **Tamil customer calls**.
* **AI Solution**: Replaces massive human translator requirements by empowering local Sinhala staff to handle Tamil customer calls effortlessly in real time via an **AI-powered WebSocket translation pool**, saving immense labor costs while removing customer wait times.

---

## ⚡ Concurrent Socket Pool Architecture (10x Parallel Channels)

To ensure zero call blocking during high-volume periods, the backend implements a **10-Channel Concurrent WebSocket Pool**:
* **Channel Pool A (10 Sockets)**: Dedicated Sinhala $\rightarrow$ Tamil AI translation streams for local agent speech.
* **Channel Pool B (10 Sockets)**: Dedicated Tamil $\rightarrow$ Sinhala AI translation streams for incoming customer speech.
* **Total Capacity**: 20 parallel WebSockets per active call-center node handling 10 simultaneous multi-agent calls concurrently.

---

## 🛠️ Tech Stack & Protocols

### Frontend
*   **React 19 & TypeScript**: Component layer and type safety.
*   **Vite**: Fast, module-based application bundling.
*   **Tailwind CSS**: Modern UI styling and micro-animations.
*   **Web Audio API**: Client-side audio recording and playback interfaces.
*   **Web Workers**: Off-thread background execution for downsampling.
*   **WebSockets**: Bidirectional audio binary packet transport.

### Backend
*   **FastAPI & Python**: High-performance asynchronous REST and WebSocket API.
*   **Google GenAI SDK**: Interfaces directly with Google's low-latency Gemini Live API.
*   **asyncio**: Concurrency engine managing simultaneous client and AI audio streams.

### Deployment & DevOps
*   **Docker & Docker Compose**: Containerized multi-service runtime environment.
*   **Nginx**: High-performance reverse proxy for routing static assets and handling WebSocket protocol upgrades.
*   **GitHub Workflows**: Automated linting, testing, and continuous integration.

---

## 📁 Repository Folder Tree

The directory layout isolates client-side assets, background audio downsampling workers, server stream orchestrators, and Nginx proxy setups:

```text
.
├── .github/workflows/          # CI/CD pipelines
├── backend/
│   ├── api/                    # FastAPI REST routing
│   ├── audio/                  # Audio normalization handlers
│   ├── config/                 # Pydantic Settings loaders
│   ├── database/               # Database integration stubs
│   ├── gemini/                 # Gemini Live WebSocket Client
│   ├── logger/                 # Structured log generation
│   ├── middleware/             # CORS and rate-limiting scripts
│   ├── models/                 # DB models definitions
│   ├── schemas/                # JSON Pydantic data schemas
│   ├── services/               # Core business orchestration layers
│   ├── tests/                  # Pytest unit and integration files
│   ├── utils/                  # Server-side utility scripts
│   ├── websocket/              # Client socket managers
│   ├── Dockerfile              # Backend Multi-stage build
│   └── main.py                 # FastAPI Uvicorn starter
├── docker/
│   └── nginx/                  # Nginx proxy mapping
├── docs/                       # API and architectural designs
├── frontend/
│   ├── src/
│   │   ├── assets/             # Brand logos and styling icons
│   │   ├── audio/              # Downsampling scripts
│   │   ├── components/         # Reusable UI component directories
│   │   ├── context/            # React global translation state provider
│   │   ├── hooks/              # Audio/WS orchestration hooks
│   │   ├── layouts/            # General grid layouts structures
│   │   ├── pages/              # Main application panels (TranslatorPage)
│   │   ├── services/           # Fetch APIs utilities
│   │   ├── styles/             # Global Tailwind layers
│   │   ├── types/              # Type safety interfaces
│   │   ├── utils/              # Client math helper functions
│   │   ├── websocket/          # Reconnecting WebSocket client
│   │   └── workers/            # Downsampler Web Worker threads
│   ├── Dockerfile              # SPA hosting on Nginx base
│   ├── package.json            # Node modules profile
│   └── vite.config.ts          # Vite asset targets
├── scripts/                    # Development helper bash tools
├── .env.example                # Base local configuration rules
├── .gitignore                  # Git checkin ignores
├── docker-compose.yml          # Container stack configurer
└── requirements.txt            # Python environments setup lists
```

---

## 👥 Student & Role Responsibilities

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

### 1. Configure Local Environment variables
Copy the template variables file and add your Google Studio credentials:
```bash
cp .env.example .env
```
Open `.env` and fill in:
`GEMINI_API_KEY=AIzaSy...`

### 2. Standard Local Run (No Containerization)
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

### 3. Running with Docker Compose (Recommended)
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

## 🔒 WebSocket Data Exchange Protocols

All communication during a live translation session is executed over the single WebSocket endpoint: `ws://localhost/ws/translate`.

### 1. Client to Server (Inbound Frames)
*   **Binary stream (Audio Frame)**: Raw Int16 mono PCM audio chunks downsampled to 16kHz.
*   **JSON Command Frame**:
    ```json
    {
      "type": "update_config",
      "payload": {
        "source_language": "sinhala",
        "target_language": "tamil",
        "voice_synthesis_enabled": true
      }
    }
    ```

### 2. Server to Client (Outbound Responses)
*   **Binary stream (Audio Playback)**: Synthesized target language audio stream returned in linear PCM to the client speaker.
*   **JSON Transcription Frame**:
    ```json
    {
      "type": "transcription",
      "payload": {
        "speaker": "source",
        "language": "sinhala",
        "text": "ආයුබෝවන්"
      }
    }
    ```
*   **JSON Translation Frame**:
    ```json
    {
      "type": "translation",
      "payload": {
        "speaker": "ai",
        "language": "tamil",
        "text": "வணக்கம்"
      }
    }
    ```

---

## 📞 Asterisk PBX Telephony Integration

The platform includes built-in **Asterisk PBX integration**, allowing phone callers (from SIP softphones, IP desk phones, or PSTN landlines) to dial into the live translation system over standard telephony channels.

### Architecture & AudioSocket Bridge
- **Asterisk Container**: Exposes SIP port `5060/udp` and RTP media range `10000-10099/udp`.
- **AudioSocket Bridge**: An asynchronous TCP service ([audiosocket_bridge.py](file:///Users/uvs/SLT/Tamil-and-Sinhala-Converter/backend/asterisk/audiosocket_bridge.py)) listening on port `9092` that streams raw uncompressed SLIN PCM between Asterisk and the FastAPI `/ws/translate-auto` WebSocket endpoint.
- **Sample Rate Converter**: Converts between telephony 8kHz 16-bit PCM and Gemini 16kHz 16-bit PCM in real time.

### How to Test with a SIP Softphone (MicroSIP / Linphone / Zoiper)
1. **Start the Docker Stack**:
   ```bash
   docker-compose up --build
   ```
2. **Configure your SIP Softphone**:
   - **SIP Server**: `127.0.0.1:5060`
   - **User ID**: `1001` (or `1002`)
   - **Password**: `1001pass` (or `1002pass`)
3. **Dial Extension `8000`**:
   - The call connects to Asterisk and triggers the `AudioSocket` bridge.
   - Speak in Sinhala or Tamil into your microphone; hear the live translated speech in real time over the phone!

