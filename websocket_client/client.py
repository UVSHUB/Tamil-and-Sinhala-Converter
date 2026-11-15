"""
SinTam WebSocket Client
Connects directly to the FastAPI backend WebSocket for real-time translation.
"""

import asyncio
import base64
import io
import json
import logging
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import wave
from dataclasses import dataclass, field
from typing import Callable, Optional, List, Dict, Any

try:
    import websockets
except ImportError:
    raise ImportError("websockets library is required. Install it using: pip install websockets")

logger = logging.getLogger("websocket_client")

IN_SAMPLE_RATE = 16000
OUT_SAMPLE_RATE = 24000
SAMPLE_WIDTH = 2  # 16-bit PCM

AUDIO_EXTENSIONS = (
    ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".oga",
    ".flac", ".webm", ".mp4", ".3gp", ".3gpp", ".amr", ".wma",
    ".aiff", ".aif", ".aifc", ".caf", ".pcm", ".raw",
)

MIME_BY_EXT = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
    ".3gp": "audio/3gpp",
    ".3gpp": "audio/3gpp",
    ".amr": "audio/amr",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".aifc": "audio/aiff",
    ".caf": "audio/x-caf",
    ".wma": "audio/x-ms-wma",
    ".pcm": "audio/pcm",
    ".raw": "audio/pcm",
}


def resolve_audio_path(path: str) -> str:
    """Normalizes a user-entered file path (strips quotes, expands ~, checks cwd & project root)."""
    cleaned = path.strip().strip('"').strip("'").strip()
    cleaned = os.path.expanduser(cleaned)
    if os.path.isfile(cleaned):
        return os.path.abspath(cleaned)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(project_root, cleaned)
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)
    return cleaned


def detect_audio_mime_type(path: str, raw: bytes = b"") -> str:
    """Detects the MIME type of an audio file from its extension or file header."""
    ext = os.path.splitext(path.lower())[1]
    if ext in MIME_BY_EXT:
        return MIME_BY_EXT[ext]
    if raw[:4] == b"RIFF":
        return "audio/wav"
    if raw[:3] == b"ID3" or (len(raw) >= 2 and raw[0] == 0xFF and (raw[1] & 0xE0) == 0xE0):
        return "audio/mp3"
    if raw[:4] == b"OggS":
        return "audio/ogg"
    if raw[:4] == b"fLaC":
        return "audio/flac"
    if len(raw) >= 8 and raw[4:8] == b"ftyp":
        return "audio/mp4"
    return "audio/wav"


def _convert_sample_width_to_16bit(frames: bytes, sampwidth: int) -> bytes:
    """Converts 8/16/24/32-bit PCM bytes into signed 16-bit little-endian PCM."""
    if sampwidth == 2:
        return frames
    if sampwidth == 1:
        out = [((b - 128) << 8) for b in frames]
        return struct.pack(f"<{len(out)}h", *out)
    if sampwidth == 3:
        n = len(frames) // 3
        raw16 = bytearray(n * 2)
        for i in range(n):
            raw16[i * 2: i * 2 + 2] = frames[i * 3 + 1: i * 3 + 3]
        return bytes(raw16)
    if sampwidth == 4:
        n = len(frames) // 4
        raw16 = bytearray(n * 2)
        for i in range(n):
            raw16[i * 2: i * 2 + 2] = frames[i * 4 + 2: i * 4 + 4]
        return bytes(raw16)
    raise ValueError(f"Unsupported WAV sample width: {sampwidth} bytes.")


def _resample_pcm(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
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


def _decode_with_system_tools(resolved_path: str) -> Optional[bytes]:
    """Use macOS `afconvert` or `ffmpeg` to decode MP3/M4A/AAC/OGG/FLAC/WEBM/WAV into 16kHz 16-bit mono PCM."""
    tmp_wav = None
    try:
        fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        if sys.platform == "darwin" and shutil.which("afconvert"):
            proc = subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", f"LEI16@{IN_SAMPLE_RATE}", "-c", "1", resolved_path, tmp_wav],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if proc.returncode == 0 and os.path.isfile(tmp_wav) and os.path.getsize(tmp_wav) > 44:
                with wave.open(tmp_wav, "rb") as wf:
                    return wf.readframes(wf.getnframes())

        if shutil.which("ffmpeg"):
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error", "-i", resolved_path,
                    "-ac", "1", "-ar", str(IN_SAMPLE_RATE), "-f", "s16le", "pipe:1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
    finally:
        if tmp_wav and os.path.exists(tmp_wav):
            try:
                os.remove(tmp_wav)
            except OSError:
                pass
    return None


def load_audio_as_pcm16_16k(path: str) -> bytes:
    """Loads any audio file (.mp3, .m4a, .aac, .ogg, .opus, .flac, .webm, .wav, .pcm, etc.)
    and converts it to 16 kHz, 16-bit mono PCM."""
    resolved = resolve_audio_path(path)
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"Audio file not found: {path}")

    with open(resolved, "rb") as f:
        raw = f.read()

    ext = os.path.splitext(resolved.lower())[1]
    if ext in (".pcm", ".raw") and raw[:4] != b"RIFF":
        return raw

    if ext == ".wav" or raw[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(raw), "rb") as wf:
                sampwidth = wf.getsampwidth()
                channels = wf.getnchannels()
                rate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
            frames = _convert_sample_width_to_16bit(frames, sampwidth)
            if channels > 1:
                n = len(frames) // 2
                s = struct.unpack(f"<{n}h", frames[: n * 2])
                mono = [sum(s[i:i + channels]) // channels for i in range(0, n - channels + 1, channels)]
                frames = struct.pack(f"<{len(mono)}h", *mono)
            return _resample_pcm(frames, rate, IN_SAMPLE_RATE)
        except wave.Error:
            pass

    decoded = _decode_with_system_tools(resolved)
    if decoded is not None:
        return decoded

    raise ValueError(
        f"Could not decode '{path}' to PCM locally (install ffmpeg or use macOS afconvert)."
    )


def record_microphone_audio(duration: Optional[float] = None, output_wav: Optional[str] = None) -> str:
    """Record live normal voice from the default microphone and save to a 16kHz 16-bit mono WAV file."""
    if output_wav is None:
        fd, output_wav = tempfile.mkstemp(prefix="sintam_mic_", suffix=".wav")
        os.close(fd)
    output_wav = os.path.abspath(output_wav)

    # 1. Try sounddevice if installed
    try:
        import sounddevice as sd  # type: ignore
        secs = duration or 5.0
        print(f"🎤 Recording live voice from microphone for {secs:.1f}s ... Speak now!")
        recording = sd.rec(int(secs * IN_SAMPLE_RATE), samplerate=IN_SAMPLE_RATE, channels=1, dtype="int16")
        sd.wait()
        with wave.open(output_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(IN_SAMPLE_RATE)
            wf.writeframes(recording.tobytes())
        print(f"✓ Recorded voice saved to {output_wav}")
        return output_wav
    except ImportError:
        pass

    # 2. On macOS, use native AVFoundation (AVAudioRecorder) via ctypes - zero extra dependencies
    if sys.platform == "darwin":
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AVFoundation.framework/AVFoundation")

        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        def msg(obj, sel_name, *args, restype=ctypes.c_void_p, argtypes=None):
            sel = objc.sel_registerName(sel_name.encode("utf-8"))
            fn = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *(argtypes or []))(("objc_msgSend", objc))
            return fn(obj, sel, *args)

        def nsstr(s: str) -> ctypes.c_void_p:
            return msg(objc.objc_getClass(b"NSString"), "stringWithUTF8String:", s.encode("utf-8"), argtypes=[ctypes.c_char_p])

        NSNumber = objc.objc_getClass(b"NSNumber")
        NSMutableDictionary = objc.objc_getClass(b"NSMutableDictionary")
        NSURL = objc.objc_getClass(b"NSURL")
        AVAudioRecorder = objc.objc_getClass(b"AVAudioRecorder")

        settings = msg(NSMutableDictionary, "dictionary")
        for key, val in [
            ("AVFormatIDKey", msg(NSNumber, "numberWithInt:", 1819304813, argtypes=[ctypes.c_int])),  # kAudioFormatLinearPCM
            ("AVSampleRateKey", msg(NSNumber, "numberWithDouble:", float(IN_SAMPLE_RATE), argtypes=[ctypes.c_double])),
            ("AVNumberOfChannelsKey", msg(NSNumber, "numberWithInt:", 1, argtypes=[ctypes.c_int])),
            ("AVLinearPCMBitDepthKey", msg(NSNumber, "numberWithInt:", 16, argtypes=[ctypes.c_int])),
            ("AVLinearPCMIsBigEndianKey", msg(NSNumber, "numberWithBool:", False, argtypes=[ctypes.c_bool])),
            ("AVLinearPCMIsFloatKey", msg(NSNumber, "numberWithBool:", False, argtypes=[ctypes.c_bool])),
        ]:
            msg(settings, "setObject:forKey:", val, nsstr(key), argtypes=[ctypes.c_void_p, ctypes.c_void_p])

        url = msg(NSURL, "fileURLWithPath:", nsstr(output_wav), argtypes=[ctypes.c_void_p])
        err = ctypes.c_void_p(0)
        rec_alloc = msg(AVAudioRecorder, "alloc")
        recorder = msg(
            rec_alloc,
            "initWithURL:settings:error:",
            url,
            settings,
            ctypes.byref(err),
            argtypes=[ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
        )
        if not recorder:
            raise RuntimeError("Could not initialize macOS AVAudioRecorder for microphone input.")

        msg(recorder, "prepareToRecord", restype=ctypes.c_bool)
        started = msg(recorder, "record", restype=ctypes.c_bool)
        if not started:
            raise RuntimeError(
                "Microphone recording could not start. Please ensure Terminal/IDE has Microphone permission in macOS System Settings -> Privacy & Security -> Microphone."
            )

        if duration and duration > 0:
            print(f"🎤 Recording live voice from microphone for {duration:.1f}s ... Speak now!")
            time.sleep(duration)
        else:
            try:
                input("🎤 Recording live voice from microphone... Speak now and press [Enter] when finished > ")
            except EOFError:
                time.sleep(4.0)

        msg(recorder, "stop", restype=None)
        print(f"✓ Recorded voice saved to {output_wav}")
        return output_wav

    # 3. Try ffmpeg / arecord on Linux/Windows
    if shutil.which("arecord"):
        secs = int(duration or 5)
        print(f"🎤 Recording live voice from microphone for {secs}s ... Speak now!")
        subprocess.run(
            ["arecord", "-f", "S16_LE", "-r", str(IN_SAMPLE_RATE), "-c", "1", "-d", str(secs), output_wav],
            check=True,
        )
        return output_wav

    raise RuntimeError(
        "No microphone recorder found. Install 'sounddevice' (pip install sounddevice) or pass an audio file (.mp3/.wav/.m4a)."
    )


def _unwrap_server_audio(message: bytes) -> bytes:
    """Extracts raw 24 kHz 16-bit mono PCM from binary server frames."""
    if message[:4] == b"RIFF":
        with wave.open(io.BytesIO(message), "rb") as wf:
            frames = _convert_sample_width_to_16bit(wf.readframes(wf.getnframes()), wf.getsampwidth())
            return _resample_pcm(frames, wf.getframerate(), OUT_SAMPLE_RATE)
    return message


@dataclass
class TranslationResult:
    """Represents the translated output of a single speech/text turn."""
    source_language: str
    target_language: str
    user_transcript: str
    translated_text: str
    audio_bytes: bytes = b""
    sample_rate: int = 24000
    wav_path: Optional[str] = None

    def save_wav(self, output_path: str) -> str:
        """Saves the received 24kHz PCM audio as a WAV file (or converts to .mp3/.m4a/.flac if requested)."""
        if not self.audio_bytes:
            raise ValueError("No audio bytes received in this turn.")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        ext = os.path.splitext(output_path.lower())[1]
        if ext in ("", ".wav"):
            with wave.open(output_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit PCM
                wf.setframerate(self.sample_rate)
                wf.writeframes(self.audio_bytes)
            self.wav_path = output_path
            return output_path

        fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            with wave.open(tmp_wav, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(self.audio_bytes)
            if shutil.which("ffmpeg"):
                proc = subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-i", tmp_wav, output_path],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                if proc.returncode == 0 and os.path.isfile(output_path):
                    self.wav_path = output_path
                    return output_path
            if sys.platform == "darwin" and shutil.which("afconvert"):
                fmt_map = {
                    ".m4a": ("m4af", "aac"),
                    ".mp4": ("mp4f", "aac"),
                    ".aac": ("adts", "aac"),
                    ".caf": ("caff", "LEI16"),
                    ".aiff": ("AIFF", "BEI16"),
                    ".flac": ("flac", "flac"),
                }
                if ext in fmt_map:
                    file_fmt, data_fmt = fmt_map[ext]
                    proc = subprocess.run(
                        ["afconvert", "-f", file_fmt, "-d", data_fmt, tmp_wav, output_path],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    )
                    if proc.returncode == 0 and os.path.isfile(output_path):
                        self.wav_path = output_path
                        return output_path
            shutil.copyfile(tmp_wav, output_path)
        finally:
            if os.path.exists(tmp_wav):
                try:
                    os.remove(tmp_wav)
                except OSError:
                    pass
        self.wav_path = output_path
        return output_path

    def play(self) -> bool:
        """Plays the synthesized audio through laptop speakers (macOS/Linux)."""
        if not self.audio_bytes:
            return False
        
        path = self.wav_path
        tmp_file = None
        if not path or not os.path.exists(path):
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_file = tmp.name
            tmp.close()
            self.save_wav(tmp_file)
            path = tmp_file

        try:
            if sys.platform == "darwin":
                subprocess.run(["afplay", path], check=True)
                return True
            elif sys.platform.startswith("linux"):
                subprocess.run(["aplay", "-q", path], check=True)
                return True
            elif sys.platform == "win32":
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
                return True
        except Exception as ex:
            logger.warning(f"Audio playback error: {ex}")
        finally:
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass
        return False


class SinTamWebSocketClient:
    """
    Python client that connects directly to the SinTam FastAPI backend WebSocket.
    
    Parameters:
        host: Hostname or IP of the FastAPI backend (default: '127.0.0.1')
        port: Port number of the FastAPI backend (default: 8000)
        source: Source language (e.g., 'Sinhala', 'Tamil', 'English')
        target: Target language (e.g., 'Tamil', 'Sinhala', 'English')
        voice: Gemini TTS voice ('Aoede', 'Charon', 'Kore', 'Puck', 'Fenrir')
        room: Room ID for isolation (default: 'default')
        auto_mode: If True, uses the bidirectional auto-detect endpoint (/ws/translate-auto)
        auto_play: If True, automatically plays received audio through speakers
        save_audio_dir: Optional folder path to save audio files from each turn
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        source: str = "Sinhala",
        target: str = "Tamil",
        voice: str = "Aoede",
        room: str = "default",
        auto_mode: bool = False,
        auto_play: bool = False,
        save_audio_dir: Optional[str] = None,
        on_transcription: Optional[Callable[[str, str], None]] = None,
        on_translation: Optional[Callable[[str, str], None]] = None,
        on_audio_chunk: Optional[Callable[[bytes], None]] = None,
        on_turn_complete: Optional[Callable[[TranslationResult], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ):
        self.host = host
        self.port = port
        self.source = source
        self.target = target
        self.voice = voice
        self.room = room
        self.auto_mode = auto_mode
        self.auto_play = auto_play
        self.save_audio_dir = save_audio_dir

        # Event callbacks
        self.on_transcription = on_transcription
        self.on_translation = on_translation
        self.on_audio_chunk = on_audio_chunk
        self.on_turn_complete = on_turn_complete
        self.on_status = on_status

        # Internal connection state
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._is_connected = False
        self._listen_task: Optional[asyncio.Task] = None
        self._turn_queue: asyncio.Queue = asyncio.Queue()

        # Turn state
        self._current_user_text = ""
        self._current_ai_text = ""
        self._current_audio_chunks: List[bytes] = []
        self._detected_source = source
        self._detected_target = target

    @property
    def ws_url(self) -> str:
        """Constructs the WebSocket URL based on parameters."""
        base = f"ws://{self.host}:{self.port}"
        if self.auto_mode:
            query = urllib.parse.urlencode({
                "voice": self.voice,
                "room": self.room,
            })
            return f"{base}/ws/translate-auto?{query}"
        else:
            query = urllib.parse.urlencode({
                "source": self.source,
                "target": self.target,
                "voice": self.voice,
                "room": self.room,
            })
            return f"{base}/ws/translate?{query}"

    async def connect(self) -> None:
        """Establishes the WebSocket connection to the backend."""
        if self._is_connected and self._ws:
            return

        url = self.ws_url
        logger.info(f"Connecting to WebSocket: {url}")
        self._ws = await websockets.connect(url, max_size=10 * 1024 * 1024)
        self._is_connected = True
        self._listen_task = asyncio.create_task(self._reader_loop())
        logger.info(f"Connected to SinTam backend at {url}")

    async def disconnect(self) -> None:
        """Closes the WebSocket connection."""
        self._is_connected = False
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        logger.info("Disconnected from backend.")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def send_text(self, text: str) -> None:
        """Sends a text phrase to be translated and spoken by Gemini."""
        if not self._is_connected or not self._ws:
            await self.connect()
        logger.debug(f"Sending text: {text}")
        await self._ws.send(text)

    async def send_audio_chunk(self, pcm_bytes: bytes) -> None:
        """
        Sends a chunk of raw linear PCM audio (16kHz, 16-bit mono).
        """
        if not self._is_connected or not self._ws:
            await self.connect()
        await self._ws.send(pcm_bytes)

    async def send_wav_file(self, wav_path: str, chunk_ms: int = 100) -> float:
        """
        Streams a WAV or PCM audio file to the backend in real time.
        Automatically converts any WAV format (mono/stereo, any sample rate, 8/16/24/32-bit)
        to 16kHz 16-bit mono PCM and appends trailing silence + audio_eof so the backend
        flushes the turn immediately. Returns the duration of the audio in seconds.
        """
        pcm = load_audio_as_pcm16_16k(wav_path)
        chunk_bytes = int(IN_SAMPLE_RATE * SAMPLE_WIDTH * (chunk_ms / 1000.0))
        chunk_delay = chunk_ms / 1000.0
        duration_s = len(pcm) / float(IN_SAMPLE_RATE * SAMPLE_WIDTH)

        for offset in range(0, len(pcm), chunk_bytes):
            await self.send_audio_chunk(pcm[offset: offset + chunk_bytes])
            await asyncio.sleep(chunk_delay * 0.9)

        # Send a short silence tail and audio_eof so the backend completes the turn promptly
        silence_chunk = b"\x00" * chunk_bytes
        for _ in range(6):
            await self.send_audio_chunk(silence_chunk)
            await asyncio.sleep(0.03)
        if self._is_connected and self._ws:
            await self._ws.send(json.dumps({"type": "audio_eof"}))

        return duration_s

    async def translate_audio_file(
        self,
        audio_path: str,
        output_wav: Optional[str] = None,
        timeout: float = 45.0,
    ) -> TranslationResult:
        """
        Loads any audio file (.mp3, .wav, .m4a, .ogg, .flac, .aac, .pcm, etc.) from `audio_path`,
        streams it to the backend (or sends encoded audio directly if local PCM decode is unavailable),
        collects the transcribed text, translated text, and synthesized voice audio,
        and saves the translated voice output.
        """
        if not self._is_connected:
            await self.connect()

        while not self._turn_queue.empty():
            self._turn_queue.get_nowait()

        resolved = resolve_audio_path(audio_path)
        pcm: Optional[bytes] = None
        try:
            pcm = load_audio_as_pcm16_16k(resolved)
            duration_s = len(pcm) / float(IN_SAMPLE_RATE * SAMPLE_WIDTH)
        except ValueError:
            duration_s = 5.0

        # Temporarily suppress per-turn auto_play if we are combining multiple turns
        orig_auto_play = self.auto_play
        self.auto_play = False
        try:
            if pcm is not None:
                send_task = asyncio.create_task(self.send_wav_file(resolved))
            else:
                with open(resolved, "rb") as f:
                    raw_bytes = f.read()
                mime_type = detect_audio_mime_type(resolved, raw_bytes)

                async def _send_encoded() -> float:
                    if self._is_connected and self._ws:
                        await self._ws.send(json.dumps({
                            "type": "audio_file",
                            "mime_type": mime_type,
                            "data_b64": base64.b64encode(raw_bytes).decode("ascii"),
                        }))
                    return 5.0

                send_task = asyncio.create_task(_send_encoded())

            turns: List[TranslationResult] = []
            deadline = asyncio.get_event_loop().time() + timeout + duration_s

            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    break
                wait_time = 2.5 if (send_task.done() and turns) else remaining
                try:
                    turn_res = await asyncio.wait_for(self._turn_queue.get(), timeout=wait_time)
                    if turn_res.user_transcript or turn_res.translated_text or turn_res.audio_bytes:
                        turns.append(turn_res)
                except asyncio.TimeoutError:
                    if send_task.done():
                        break

            await send_task
        finally:
            self.auto_play = orig_auto_play

        if not turns:
            raise TimeoutError(f"No translation received from backend within {timeout:.0f}s for {audio_path}")

        combined_user = " ".join(t.user_transcript.strip() for t in turns if t.user_transcript.strip())
        combined_ai = " ".join(t.translated_text.strip() for t in turns if t.translated_text.strip())
        combined_audio = b"".join(t.audio_bytes for t in turns if t.audio_bytes)

        final_result = TranslationResult(
            source_language=turns[-1].source_language,
            target_language=turns[-1].target_language,
            user_transcript=combined_user,
            translated_text=combined_ai,
            audio_bytes=combined_audio,
            sample_rate=OUT_SAMPLE_RATE,
            wav_path=turns[-1].wav_path,
        )

        if output_wav and combined_audio:
            final_result.save_wav(output_wav)

        if self.auto_play and combined_audio:
            final_result.play()

        return final_result

    async def translate_text(
        self,
        text: str,
        timeout: float = 20.0,
        output_wav: Optional[str] = None,
    ) -> TranslationResult:
        """
        Convenience method: sends text and waits until the complete translation
        and synthesized voice are received.
        """
        if not self._is_connected:
            await self.connect()

        # Clear any stale queue results
        while not self._turn_queue.empty():
            self._turn_queue.get_nowait()

        await self.send_text(text)
        result = await self.wait_for_turn(timeout=timeout)
        if output_wav and result.audio_bytes:
            result.save_wav(output_wav)
        return result

    async def wait_for_turn(self, timeout: float = 15.0) -> TranslationResult:
        """Waits for the next complete translation turn from the server."""
        try:
            result = await asyncio.wait_for(self._turn_queue.get(), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out waiting for turn completion after {timeout} seconds.")

    async def _reader_loop(self) -> None:
        """Background loop to read frames from WebSocket and dispatch events."""
        try:
            while self._is_connected and self._ws:
                message = await self._ws.recv()

                # Binary frames: 24kHz synthesized audio PCM from Gemini
                if isinstance(message, bytes):
                    pcm_chunk = _unwrap_server_audio(message)
                    self._current_audio_chunks.append(pcm_chunk)
                    if self.on_audio_chunk:
                        try:
                            self.on_audio_chunk(pcm_chunk)
                        except Exception as cb_err:
                            logger.error(f"Error in on_audio_chunk callback: {cb_err}")

                # Text frames: JSON protocol messages
                elif isinstance(message, str):
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        logger.warning(f"Received non-JSON text message: {message}")
                        continue

                    msg_type = data.get("type")
                    payload = data.get("payload", {})

                    if msg_type == "status":
                        msg = payload.get("message", "")
                        logger.info(f"[Server Status] {msg}")
                        if self.on_status:
                            self.on_status(msg)

                    elif msg_type == "lang_detected":
                        self._detected_source = payload.get("source", self.source)
                        self._detected_target = payload.get("target", self.target)
                        logger.info(f"Language detected: {self._detected_source} -> {self._detected_target}")

                    elif msg_type == "transcription":
                        text = payload.get("text", "")
                        delta = payload.get("delta", "")
                        if text:
                            self._current_user_text = text
                        if payload.get("detected_lang"):
                            self._detected_source = payload["detected_lang"]
                        if self.on_transcription:
                            self.on_transcription(text, delta)

                    elif msg_type == "translation":
                        text = payload.get("text", "")
                        delta = payload.get("delta", "")
                        if text:
                            self._current_ai_text = text
                        if payload.get("target_lang"):
                            self._detected_target = payload["target_lang"]
                        if self.on_translation:
                            self.on_translation(text, delta)

                    elif msg_type == "turn_complete":
                        final_user = payload.get("user_text") or self._current_user_text
                        final_ai = payload.get("ai_text") or self._current_ai_text
                        total_audio = b"".join(self._current_audio_chunks)

                        result = TranslationResult(
                            source_language=self._detected_source,
                            target_language=self._detected_target,
                            user_transcript=final_user,
                            translated_text=final_ai,
                            audio_bytes=total_audio,
                            sample_rate=OUT_SAMPLE_RATE,
                        )

                        # Optionally save audio
                        if self.save_audio_dir and total_audio:
                            os.makedirs(self.save_audio_dir, exist_ok=True)
                            fname = f"turn_{int(asyncio.get_event_loop().time() * 1000)}.wav"
                            fpath = os.path.join(self.save_audio_dir, fname)
                            result.save_wav(fpath)

                        # Optionally play audio automatically
                        if self.auto_play and total_audio:
                            result.play()

                        if self.on_turn_complete:
                            try:
                                self.on_turn_complete(result)
                            except Exception as cb_err:
                                logger.error(f"Error in on_turn_complete callback: {cb_err}")

                        await self._turn_queue.put(result)

                        # Reset turn state
                        self._current_user_text = ""
                        self._current_ai_text = ""
                        self._current_audio_chunks = []

        except (websockets.ConnectionClosed, asyncio.CancelledError):
            pass
        except Exception as ex:
            logger.error(f"WebSocket read error: {ex}")
        finally:
            self._is_connected = False
