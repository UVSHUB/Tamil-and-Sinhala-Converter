# SinTam Python WebSocket Client

A dedicated Python client for connecting to the SinTam FastAPI backend WebSocket gateway. It provides real-time, low-latency speech and text translation between **Sinhala**, **Tamil**, and **English** powered by Google Gemini Live.

---

## 🚀 Quickstart

### 1. Run the Interactive CLI
From the project root directory:
```bash
python -m websocket_client.cli
```

### 2. Translate a Single Phrase (One-Shot)
```bash
python -m websocket_client.cli --source Sinhala --target Tamil --text "සුබ උදෑසනක්" --play
```

### 3. Stream a WAV Audio File
```bash
python -m websocket_client.cli --source Sinhala --target Tamil --wav path/to/sample.wav --play
```

---

## ⚙️ Configurable Input Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `host` | `str` | `"127.0.0.1"` | Hostname or IP of the FastAPI backend. |
| `port` | `int` | `8000` | Port of the FastAPI backend. |
| `source` | `str` | `"Sinhala"` | Source language (`Sinhala`, `Tamil`, `English`). |
| `target` | `str` | `"Tamil"` | Target language (`Tamil`, `Sinhala`, `English`). |
| `voice` | `str` | `"Aoede"` | Gemini TTS voice (`Aoede`, `Charon`, `Kore`, `Puck`, `Fenrir`). |
| `room` | `str` | `"default"` | Channel / session room ID. |
| `auto_mode` | `bool` | `False` | When `True`, connects to `/ws/translate-auto` for automatic language detection. |
| `auto_play` | `bool` | `False` | When `True`, automatically plays received speech audio through speakers via `afplay`/`aplay`. |
| `save_audio_dir` | `str` | `None` | Optional directory to save output audio as `.wav` files. |

---

## 💻 Programmatic Python Usage

```python
import asyncio
from websocket_client import SinTamWebSocketClient

async def main():
    # 1. Initialize client with desired input parameters
    client = SinTamWebSocketClient(
        host="127.0.0.1",
        port=8000,
        source="Sinhala",
        target="Tamil",
        voice="Aoede",
        auto_play=True,  # Plays audio through speakers
    )

    # 2. Connect using async context manager
    async with client:
        # 3. Translate text
        result = await client.translate_text("ඔබට කොහොමද?")
        
        print("Translated Text:", result.translated_text)
        print(f"Received Audio : {len(result.audio_bytes)} bytes (24kHz PCM)")

        # 4. Optionally save audio to a WAV file
        result.save_wav("how_are_you_tamil.wav")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 📡 Callbacks for Streaming Applications

You can attach callbacks to listen to real-time events as they happen:

```python
def on_transcription(full_text: str, delta: str):
    print("User said:", delta)

def on_translation(full_text: str, delta: str):
    print("AI translated:", delta)

def on_audio_chunk(pcm_bytes: bytes):
    # Stream audio bytes to a custom audio device or network socket
    pass

def on_turn_complete(result):
    print("Turn complete:", result.translated_text)

client = SinTamWebSocketClient(
    source="Sinhala",
    target="Tamil",
    on_transcription=on_transcription,
    on_translation=on_translation,
    on_audio_chunk=on_audio_chunk,
    on_turn_complete=on_turn_complete,
)
```
