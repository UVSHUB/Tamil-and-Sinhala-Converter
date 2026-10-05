# 🚀 AWS EC2 Deployment & Real-Time Voice Translation Guide

This guide covers how to deploy and operate the **Sinhala ↔ Tamil Real-Time Continuous Voice Translator** backend on an AWS EC2 instance, along with a lightweight Python client to connect directly from any machine or application.

---

## 🌟 Architecture & Features Implemented

1. **Continuous Rolling-Chunk Engine**:
   - Listens to incoming user microphone audio continuously without waiting for speech pauses.
   - Slices streaming PCM audio every **~4.5 seconds** (or upon a natural speech cadence).
   - Translates continuously so the conversation never gets blocked or delayed.

2. **Full Tri-Lingual Auto-Detection**:
   - Automatically detects whether the user is speaking **Sinhala**, **Tamil**, or **English** (including **Singlish** and **Tanglish** colloquialisms).

3. **Dynamic Target Language Switching**:
   - The caller or agent can switch the output language between **Tamil** and **Sinhala** on the fly without dropping the WebSocket connection (`{"type": "set_target", "target": "Sinhala"}`).

4. **Natural Speech Synthesis (TTS)**:
   - Synthesizes the translated text in real time using Google Gemini TTS and streams binary audio bytes directly back to the client.

5. **Verified Google Gemini Models**:
   - **Translation & Transcription**: `gemini-3.1-flash-lite-preview`
   - **Speech Synthesis (TTS)**: `gemini-3.8-flash-tts`
   - **Live Translation Stream**: `gemini-3.5-live-translate-preview`

---

## 🛠️ Step-by-Step AWS EC2 Deployment

### Step 1: Launch an AWS EC2 Instance
1. Open the [AWS EC2 Console](https://console.aws.amazon.com/ec2/).
2. Click **Launch instance**.
3. **OS**: Select **Ubuntu Server 24.04 LTS**.
4. **Instance Type**: Select **`t3.small`** (recommended) or **`t3.micro`** (free-tier eligible).
5. **Storage**: Set root volume to **`20 GiB`** gp3.
6. **Key Pair**: Select an existing key pair or create a new `.pem` key.

### Step 2: Configure Security Group (Firewall Rules)
Under **Network settings** > **Edit**, ensure the following inbound rules exist:

| Type | Protocol | Port Range | Source | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **SSH** | TCP | `22` | `0.0.0.0/0` | Server remote administration |
| **HTTP** | TCP | `80` | `0.0.0.0/0` | Nginx web interface |
| **HTTPS** | TCP | `443` | `0.0.0.0/0` | Secure SSL / Mic permissions |
| **Custom TCP** | TCP | `8000` | `0.0.0.0/0` | FastAPI Backend & WebSockets |

### Step 3: Automated Launch Script (User Data)
In the **Advanced details** section at the bottom, paste this into the **User data** box:

```bash
#!/bin/bash
# 1. Setup 2GB Swap Memory (prevents memory exhaustion on t3.micro)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab

# 2. Install Docker & Git
apt-get update
apt-get install -y ca-certificates curl git docker.io docker-compose-v2

# 3. Clone Repository
git clone https://github.com/UVSHUB/Tamil-and-Sinhala-Converter.git /home/ubuntu/Tamil-and-Sinhala-Converter
cd /home/ubuntu/Tamil-and-Sinhala-Converter

# 4. Configure .env with your Google Gemini Key
cat << 'EOF' > .env
GEMINI_API_KEY=YOUR_GOOGLE_GEMINI_KEY_HERE
TRANSLATE_MODEL=gemini-3.1-flash-lite-preview
TTS_MODEL=gemini-3.8-flash-tts
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
ALLOWED_ORIGINS=*
EOF

# 5. Build and launch all services
docker compose up -d --build
```

Click **Launch instance**. Within 3–5 minutes, your server will be up and running!

---

## 🌐 Verifying Your Deployment

Find your EC2 **Public IPv4 Address** (e.g. `16.171.141.51`):

- **Health Endpoint**:
  ```text
  http://<YOUR_EC2_PUBLIC_IP>:8000/api/v1/health
  ```
  Returns: `{"status":"healthy","service":"voice-translator-backend","gemini_live_configured":true}`

- **Web App**:
  ```text
  http://<YOUR_EC2_PUBLIC_IP>:8000
  ```

---

## 🐍 Lightweight Python Client Example

You can connect to your AWS backend from any Python script, local computer, or backend system using standard WebSockets.

### Installation
```bash
pip install websockets
```

### Python Code (`examples/aws_client_example.py`)
```python
import asyncio
import json
import websockets

# Replace with your EC2 Public IP or domain
SERVER_IP = "YOUR_EC2_PUBLIC_IP"
SERVER_PORT = 8000
TARGET_LANG = "Tamil"  # or "Sinhala"

WS_URL = f"ws://{SERVER_IP}:{SERVER_PORT}/ws/translate-auto?target={TARGET_LANG}"

async def run_client():
    print(f"Connecting to AWS Translator: {WS_URL} ...")
    async with websockets.connect(WS_URL) as ws:
        print("[CONNECTED] Real-time translation session is active!\n")

        # Task to listen for translated transcripts and audio from the server
        async def receive_messages():
            async for message in ws:
                if isinstance(message, bytes):
                    print(f"--> [AUDIO RECEIVED] Gemini TTS Audio: {len(message)} bytes")
                else:
                    data = json.loads(message)
                    mtype = data.get("type")
                    payload = data.get("payload", {})

                    if mtype == "status":
                        print(f"[STATUS] {payload.get('message')}")
                    elif mtype == "lang_detected":
                        print(f"[LANG] Detected: {payload.get('source')} -> Output: {payload.get('target')}")
                    elif mtype == "transcription":
                        print(f"[USER] ({payload.get('detected_lang')}): {payload.get('text')}")
                    elif mtype == "translation":
                        print(f"[AI] -> ({payload.get('target_lang')}): {payload.get('text')}")
                    elif mtype == "turn_complete":
                        print("[TURN] Complete.\n")

        recv_task = asyncio.create_task(receive_messages())

        # Switch target language on the fly without dropping connection
        await asyncio.sleep(2)
        print(">>> Switching target language to Sinhala...")
        await ws.send(json.dumps({"type": "set_target", "target": "Sinhala"}))

        await asyncio.sleep(2)
        print(">>> Switching target language back to Tamil...")
        await ws.send(json.dumps({"type": "set_target", "target": "Tamil"}))

        await recv_task

if __name__ == "__main__":
    asyncio.run(run_client())
```

---

## 🎤 Important: Browser Microphone Permissions over HTTP

Browsers (Chrome, Edge, Safari) strictly disable microphone access (`getUserMedia`) on raw HTTP IP addresses.

To use the microphone with the web app:

1. In Chrome, open a new tab and go to:
   ```text
   chrome://flags/#unsafely-treat-insecure-origin-as-secure
   ```
2. In the text box, paste your URL:
   ```text
   http://YOUR_EC2_PUBLIC_IP:8000
   ```
3. Set dropdown to **Enabled** and click **Relaunch**.

*For Production*: Connect a domain name to your EC2 IP using **Cloudflare** (with SSL enabled) to get instant free HTTPS (`https://your-domain.com`).
