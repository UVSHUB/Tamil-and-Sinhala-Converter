"""
SinTam translation client.

Talks to the FastAPI backend over WebSocket and supports two modes:

* Audio mode  -> /ws/translate-auto
  Streams a speech file (16 kHz mono PCM or any WAV) in real time, prints the
  transcription / translation the server sends back, and saves the translated
  speech to a playable WAV file.

* Text mode   -> /ws/translate
  Sends a phrase and prints the translated text.

Only needs the `websockets` package (pip install websockets).
"""

import asyncio
import json
import struct
import time
import urllib.parse
import uuid
import wave
from dataclasses import dataclass, field

import websockets

# Audio format the backend expects as input
IN_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit
CHUNK_MS = 100
CHUNK_BYTES = IN_RATE * SAMPLE_WIDTH * CHUNK_MS // 1000  # 3200 bytes per 100 ms

# Audio format Gemini TTS / Live returns (raw PCM)
OUT_RATE = 24000

# How long to keep listening once a turn has completed / while waiting for the first reply
IDLE_AFTER_TURN = 4.0


@dataclass
class TranslationSession:
    """Everything received from the server during one run."""
    transcriptions: list = field(default_factory=list)
    translations: list = field(default_factory=list)
    detected: str = ""
    audio: bytearray = field(default_factory=bytearray)
    turns: int = 0
    closed_reason: str = ""
    # The server sends each sentence as it grows; keep the latest version until the turn ends
    current_heard: str = ""
    current_lang: str = ""
    current_said: str = ""

    def finish_turn(self) -> None:
        """Print and store the finished sentence pair of the current turn."""
        if self.current_heard:
            self.transcriptions.append(self.current_heard)
            lang = f" ({self.current_lang})" if self.current_lang else ""
            print(f"  You said{lang}: {self.current_heard}")
        if self.current_said:
            self.translations.append(self.current_said)
            print(f"  Translation: {self.current_said}")
        self.current_heard = self.current_lang = self.current_said = ""


# ──────────────────────────────────────────────────────────────────────────────
# Audio helpers
# ──────────────────────────────────────────────────────────────────────────────

def _resample(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
    """Linear-interpolation resampler for 16-bit little-endian mono PCM."""
    if from_rate == to_rate or not pcm:
        return pcm
    n_in = len(pcm) // 2
    samples = struct.unpack(f"<{n_in}h", pcm[: n_in * 2])
    n_out = int(n_in * to_rate / from_rate)
    step = from_rate / to_rate
    out = []
    for i in range(n_out):
        pos = i * step
        lo = int(pos)
        hi = min(lo + 1, n_in - 1)
        frac = pos - lo
        out.append(int(samples[lo] * (1 - frac) + samples[hi] * frac))
    return struct.pack(f"<{len(out)}h", *out)


def load_audio(path: str) -> bytes:
    """Load a .wav (any rate, mono/stereo, 16-bit) or raw .pcm (16 kHz mono 16-bit)
    file and return 16 kHz mono 16-bit PCM."""
    if path.lower().endswith(".wav"):
        with wave.open(path, "rb") as wf:
            if wf.getsampwidth() != 2:
                raise ValueError("WAV file must be 16-bit PCM.")
            channels, rate = wf.getnchannels(), wf.getframerate()
            frames = wf.readframes(wf.getnframes())
        if channels > 1:  # downmix to mono
            n = len(frames) // 2
            s = struct.unpack(f"<{n}h", frames)
            mono = [sum(s[i:i + channels]) // channels for i in range(0, n, channels)]
            frames = struct.pack(f"<{len(mono)}h", *mono)
        return _resample(frames, rate, IN_RATE)
    with open(path, "rb") as f:
        return f.read()


def rms_level(pcm: bytes) -> float:
    """Normalised RMS loudness (0.0 = silence)."""
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    s = struct.unpack(f"<{n}h", pcm[: n * 2])
    return (sum(x * x for x in s) / n) ** 0.5 / 32768.0


def _audio_frames(message: bytes) -> bytes:
    """Return raw 24 kHz PCM from a binary server message (raw PCM or a WAV container)."""
    if message[:4] == b"RIFF":
        import io
        with wave.open(io.BytesIO(message), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            return _resample(frames, wf.getframerate(), OUT_RATE)
    return message


def save_wav(pcm: bytes, path: str, rate: int = OUT_RATE) -> None:
    """Write raw 16-bit mono PCM to a valid WAV file."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(rate)
        wf.writeframes(pcm)


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket protocol
# ──────────────────────────────────────────────────────────────────────────────

def build_url(host: str, port: int, path: str, **params) -> str:
    params = {k: v for k, v in params.items() if v}
    # Private room so this run never receives other users' audio / transcripts
    params.setdefault("room", f"cli-{uuid.uuid4().hex[:8]}")
    return f"ws://{host}:{port}{path}?{urllib.parse.urlencode(params)}"


def _handle_text(raw: str, session: TranslationSession, verbose: bool = True) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return
    kind, payload = msg.get("type"), msg.get("payload", {})
    if kind == "status":
        if verbose:
            print(f"  [server] {payload.get('message', '')}")
    elif kind == "lang_detected":
        session.detected = f"{payload.get('source')} -> {payload.get('target')}"
    elif kind == "transcription":
        session.current_heard = payload.get("text", "")
        session.current_lang = payload.get("detected_lang") or session.current_lang
    elif kind == "translation":
        session.current_said = payload.get("text", "")
    elif kind == "turn_complete":
        session.finish_turn()
        session.turns += 1


async def _receive_until_idle(ws, session: TranslationSession, timeout: float) -> None:
    """Read server messages until the conversation goes quiet.

    Waits up to `timeout` seconds for the first reply; once a turn has completed,
    stops after IDLE_AFTER_TURN seconds with no new messages."""
    deadline = time.monotonic() + timeout
    try:
        await _receive_loop(ws, session, deadline)
    finally:
        session.finish_turn()  # print anything received after the last turn_complete


async def _receive_loop(ws, session: TranslationSession, deadline: float) -> None:
    while True:
        wait = IDLE_AFTER_TURN if session.turns else deadline - time.monotonic()
        if wait <= 0:
            return
        try:
            message = await asyncio.wait_for(ws.recv(), timeout=wait)
        except asyncio.TimeoutError:
            return
        except websockets.ConnectionClosed as closed:
            session.closed_reason = f"code {closed.code} {closed.reason or ''}".strip()
            return
        if isinstance(message, bytes):
            session.audio.extend(_audio_frames(message))
        else:
            _handle_text(message, session)


async def translate_audio(
    audio_path: str,
    output_path: str = "output.wav",
    host: str = "127.0.0.1",
    port: int = 8000,
    target: str = "Tamil",
    voice: str = "Aoede",
    api_key: str = "",
    timeout: float = 45.0,
) -> TranslationSession:
    """Stream a speech file to /ws/translate-auto and save the translated speech."""
    pcm = load_audio(audio_path)
    seconds = len(pcm) / (IN_RATE * SAMPLE_WIDTH)
    print(f"Input audio : {audio_path} ({seconds:.1f}s)")
    if rms_level(pcm) < 0.005:
        print("WARNING: the input audio is (nearly) silent - the server ignores silence, "
              "so no translation will come back. Use a real speech recording.")

    url = build_url(host, port, "/ws/translate-auto", target=target, voice=voice, api_key=api_key)
    session = TranslationSession()
    async with websockets.connect(url, max_size=20 * 1024 * 1024) as ws:
        print(f"Connected   : {url.split('?')[0]} (target: {target})")
        receiver = asyncio.create_task(_receive_until_idle(ws, session, timeout + seconds))

        # Stream in real time - the server slices speech by timing, like a live microphone
        for i in range(0, len(pcm), CHUNK_BYTES):
            if receiver.done():
                break
            await ws.send(pcm[i:i + CHUNK_BYTES])
            await asyncio.sleep(CHUNK_MS / 1000)

        await receiver

    if session.audio:
        save_wav(bytes(session.audio), output_path)
        print(f"Saved       : {output_path} ({len(session.audio) / (OUT_RATE * 2):.1f}s of translated speech)")
    return session


async def translate_text(
    text: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    source: str = "Sinhala",
    target: str = "Tamil",
    voice: str = "Aoede",
    api_key: str = "",
    timeout: float = 30.0,
    output_path: str = "",
) -> TranslationSession:
    """Send a phrase to /ws/translate and print the translation."""
    url = build_url(host, port, "/ws/translate", source=source, target=target, voice=voice, api_key=api_key)
    session = TranslationSession()
    async with websockets.connect(url, max_size=20 * 1024 * 1024) as ws:
        print(f"Connected   : {url.split('?')[0]} ({source} -> {target})")
        # Wait for the "Connected ... Start speaking!" status before sending
        try:
            first = await asyncio.wait_for(ws.recv(), timeout=timeout)
            if isinstance(first, str):
                _handle_text(first, session)
        except websockets.ConnectionClosed as closed:
            session.closed_reason = f"code {closed.code} {closed.reason or ''}".strip()
            return session
        print(f"  Sending: {text}")
        await ws.send(text)
        await _receive_until_idle(ws, session, timeout)

    if session.audio and output_path:
        save_wav(bytes(session.audio), output_path)
        print(f"Saved       : {output_path}")
    return session
