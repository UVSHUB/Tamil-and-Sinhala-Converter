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
import base64
import ctypes
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import uuid
import wave
from dataclasses import dataclass, field

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))

# Supported audio / voice file extensions
AUDIO_EXTENSIONS = (
    ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".oga",
    ".flac", ".webm", ".mp4", ".3gp", ".3gpp", ".amr", ".wma",
    ".aiff", ".aif", ".aifc", ".caf", ".pcm", ".raw",
)

# Audio format the backend expects as input
IN_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit
CHUNK_MS = 100
CHUNK_BYTES = IN_RATE * SAMPLE_WIDTH * CHUNK_MS // 1000  # 3200 bytes per 100 ms
SILENCE_TAIL_CHUNKS = 6  # 600 ms of trailing silence so VAD / Live flushes immediately

# Audio format Gemini TTS / Live returns (raw PCM)
OUT_RATE = 24000

# How long to keep listening once a turn has completed / while waiting for the first reply
IDLE_AFTER_TURN = 3.0


@dataclass
class TranslationSession:
    """Everything received from the server during one run."""
    transcriptions: list = field(default_factory=list)
    translations: list = field(default_factory=list)
    detected: str = ""
    audio: bytearray = field(default_factory=bytearray)
    turns: int = 0
    closed_reason: str = ""
    output_wav_path: str = ""
    # The server sends each sentence as it grows; keep the latest version until the turn ends
    current_heard: str = ""
    current_lang: str = ""
    current_said: str = ""

    def finish_turn(self, payload: dict | None = None) -> None:
        """Print and store the finished sentence pair of the current turn."""
        if payload:
            if payload.get("user_text") and not self.current_heard:
                self.current_heard = payload["user_text"]
            if payload.get("ai_text") and not self.current_said:
                self.current_said = payload["ai_text"]
        if self.current_heard:
            self.transcriptions.append(self.current_heard)
            lang = f" ({self.current_lang})" if self.current_lang else ""
            print(f"  You said{lang}: {self.current_heard}")
        if self.current_said:
            self.translations.append(self.current_said)
            print(f"  Translation: {self.current_said}")
        self.current_heard = self.current_lang = self.current_said = ""

    @property
    def full_transcription(self) -> str:
        return " ".join(t.strip() for t in self.transcriptions if t.strip())

    @property
    def full_translation(self) -> str:
        return " ".join(t.strip() for t in self.translations if t.strip())


# ──────────────────────────────────────────────────────────────────────────────
# Audio helpers
# ──────────────────────────────────────────────────────────────────────────────

def resolve_audio_path(path: str) -> str:
    """Normalize a user-provided file path (strips quotes, expands ~, checks cwd & project root)."""
    cleaned = path.strip().strip('"').strip("'").strip()
    cleaned = os.path.expanduser(cleaned)
    if os.path.isfile(cleaned):
        return os.path.abspath(cleaned)
    candidate = os.path.join(HERE, cleaned)
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)
    return cleaned


def _convert_sample_width_to_16bit(frames: bytes, sampwidth: int) -> bytes:
    """Convert 8-bit, 16-bit, 24-bit, or 32-bit PCM bytes to signed 16-bit little-endian PCM."""
    if sampwidth == 2:
        return frames
    if sampwidth == 1:
        # 8-bit WAV is unsigned (0..255, center 128)
        out = [((b - 128) << 8) for b in frames]
        return struct.pack(f"<{len(out)}h", *out)
    if sampwidth == 3:
        # 24-bit signed little-endian: take the upper 2 bytes of each 3-byte sample
        n = len(frames) // 3
        raw16 = bytearray(n * 2)
        for i in range(n):
            raw16[i * 2: i * 2 + 2] = frames[i * 3 + 1: i * 3 + 3]
        return bytes(raw16)
    if sampwidth == 4:
        # 32-bit signed little-endian: take the upper 2 bytes of each 4-byte sample
        n = len(frames) // 4
        raw16 = bytearray(n * 2)
        for i in range(n):
            raw16[i * 2: i * 2 + 2] = frames[i * 4 + 2: i * 4 + 4]
        return bytes(raw16)
    raise ValueError(f"Unsupported WAV sample width: {sampwidth} bytes.")


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


def detect_audio_mime_type(path: str, raw: bytes = b"") -> str:
    """Return the MIME type for an audio file path or header bytes."""
    ext = os.path.splitext(path.lower())[1]
    mime_map = {
        ".wav": "audio/wav",
        ".mp3": "audio/mp3",
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".opus": "audio/ogg",
        ".oga": "audio/ogg",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
        ".aiff": "audio/aiff",
        ".aif": "audio/aiff",
        ".aifc": "audio/aiff",
        ".3gp": "audio/3gpp",
        ".3gpp": "audio/3gpp",
        ".amr": "audio/amr",
        ".wma": "audio/x-ms-wma",
        ".caf": "audio/x-caf",
    }
    if ext in mime_map:
        return mime_map[ext]
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


def _decode_with_system_tools(resolved_path: str) -> bytes | None:
    """Decode any audio file (.mp3, .m4a, .aac, .ogg, .opus, .flac, .webm, .mp4, .caf, .wav)
    to 16 kHz 16-bit mono PCM using macOS `afconvert` or cross-platform `ffmpeg`."""
    # 1. Try macOS built-in afconvert
    afconvert_bin = shutil.which("afconvert") or ("/usr/bin/afconvert" if os.path.isfile("/usr/bin/afconvert") else None)
    if afconvert_bin:
        tmp_fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(tmp_fd)
        try:
            res = subprocess.run(
                [afconvert_bin, "-f", "WAVE", "-d", f"LEI16@{IN_RATE}", "-c", "1", resolved_path, tmp_wav],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if res.returncode == 0 and os.path.isfile(tmp_wav) and os.path.getsize(tmp_wav) > 44:
                with wave.open(tmp_wav, "rb") as wf:
                    return wf.readframes(wf.getnframes())
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_wav):
                try:
                    os.remove(tmp_wav)
                except OSError:
                    pass

    # 2. Try ffmpeg (macOS / Linux / Windows)
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        try:
            res = subprocess.run(
                [ffmpeg_bin, "-y", "-v", "error", "-i", resolved_path, "-ar", str(IN_RATE), "-ac", "1", "-f", "s16le", "pipe:1"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            if res.returncode == 0 and res.stdout:
                return res.stdout
        except Exception:
            pass

    return None


def load_audio(path: str) -> bytes:
    """Load any supported audio/voice file (.wav, .mp3, .m4a, .aac, .ogg, .opus, .flac,
    .webm, .mp4, .caf, .aiff, or raw 16 kHz mono .pcm) and return 16 kHz mono 16-bit PCM."""
    resolved = resolve_audio_path(path)
    if not os.path.isfile(resolved):
        raise FileNotFoundError(f"Audio file not found: {path}")

    with open(resolved, "rb") as f:
        raw = f.read()

    ext = os.path.splitext(resolved.lower())[1]

    # Standard RIFF WAV
    if ext == ".wav" or raw[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(raw), "rb") as wf:
                sampwidth = wf.getsampwidth()
                channels, rate = wf.getnchannels(), wf.getframerate()
                frames = wf.readframes(wf.getnframes())
            frames = _convert_sample_width_to_16bit(frames, sampwidth)
            if channels > 1:  # downmix to mono
                n = len(frames) // 2
                s = struct.unpack(f"<{n}h", frames[: n * 2])
                mono = [sum(s[i:i + channels]) // channels for i in range(0, n - channels + 1, channels)]
                frames = struct.pack(f"<{len(mono)}h", *mono)
            return _resample(frames, rate, IN_RATE)
        except Exception:
            # Compressed WAV (e.g. MP3/float/ADPCM inside WAV container) -> decode with system tools
            decoded = _decode_with_system_tools(resolved)
            if decoded is not None:
                return decoded
            raise

    # Raw 16kHz 16-bit mono PCM
    if ext in (".pcm", ".raw") and raw[:3] != b"ID3" and raw[:4] not in (b"OggS", b"fLaC") and raw[4:8] != b"ftyp":
        return raw

    # Compressed audio / voice formats (.mp3, .m4a, .aac, .ogg, .opus, .flac, .webm, .mp4, .caf, .aiff, etc.)
    decoded = _decode_with_system_tools(resolved)
    if decoded is not None:
        return decoded

    raise ValueError(
        f"Could not decode '{path}' to PCM locally (install ffmpeg for this format, or use direct backend upload)."
    )


def record_microphone_audio(duration: float | None = None, output_wav: str | None = None) -> str:
    """Record live normal voice from the microphone into a 16 kHz 16-bit mono WAV file.
    If `duration` is None, records until the user presses Enter."""
    if not output_wav:
        tmp_fd, output_wav = tempfile.mkstemp(prefix="sintam_mic_", suffix=".wav")
        os.close(tmp_fd)

    # 1. Try sounddevice if installed
    try:
        import sounddevice as sd
        import numpy as np
        if duration:
            print(f"🎙️  Recording from microphone for {duration:.1f}s ... Speak now!")
            audio = sd.rec(int(duration * IN_RATE), samplerate=IN_RATE, channels=1, dtype="int16")
            sd.wait()
            pcm_bytes = audio.tobytes()
        else:
            chunks = []
            def _cb(indata, frames, time_info, status):
                chunks.append(bytes(indata))
            print("🎙️  Recording from microphone... Speak now, and press Enter when finished!")
            with sd.RawInputStream(samplerate=IN_RATE, channels=1, dtype="int16", callback=_cb):
                input()
            pcm_bytes = b"".join(chunks)
        save_wav(pcm_bytes, output_wav, rate=IN_RATE)
        return output_wav
    except ImportError:
        pass

    # 2. macOS built-in AVAudioRecorder via ctypes (zero third-party packages required)
    if sys.platform == "darwin":
        try:
            objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
            ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
            ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AVFoundation.framework/AVFoundation")

            objc.objc_getClass.restype = ctypes.c_void_p
            objc.objc_getClass.argtypes = [ctypes.c_char_p]
            objc.sel_registerName.restype = ctypes.c_void_p
            objc.sel_registerName.argtypes = [ctypes.c_char_p]

            msg_ptr = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))
            msg_ptr_cstr = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p)(("objc_msgSend", objc))
            msg_ptr_ptr = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))
            msg_ptr_int = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int)(("objc_msgSend", objc))
            msg_ptr_dbl = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double)(("objc_msgSend", objc))
            msg_void = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))
            msg_init_rec = ctypes.CFUNCTYPE(
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
            )(("objc_msgSend", objc))
            msg_bool = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(("objc_msgSend", objc))

            def _sel(n: bytes):
                return objc.sel_registerName(n)

            def _cls(n: bytes):
                return objc.objc_getClass(n)

            def _nsstr(s: str):
                return msg_ptr_cstr(_cls(b"NSString"), _sel(b"stringWithUTF8String:"), s.encode("utf-8"))

            abs_out = os.path.abspath(output_wav)
            url_ns = msg_ptr_ptr(_cls(b"NSURL"), _sel(b"fileURLWithPath:"), _nsstr(abs_out))
            dict_ns = msg_ptr(_cls(b"NSMutableDictionary"), _sel(b"dictionary"))
            # 1819304813 == 'lpcm' (kAudioFormatLinearPCM)
            msg_void(dict_ns, _sel(b"setObject:forKey:"), msg_ptr_int(_cls(b"NSNumber"), _sel(b"numberWithInt:"), 1819304813), _nsstr("AVFormatIDKey"))
            msg_void(dict_ns, _sel(b"setObject:forKey:"), msg_ptr_dbl(_cls(b"NSNumber"), _sel(b"numberWithDouble:"), float(IN_RATE)), _nsstr("AVSampleRateKey"))
            msg_void(dict_ns, _sel(b"setObject:forKey:"), msg_ptr_int(_cls(b"NSNumber"), _sel(b"numberWithInt:"), 1), _nsstr("AVNumberOfChannelsKey"))
            msg_void(dict_ns, _sel(b"setObject:forKey:"), msg_ptr_int(_cls(b"NSNumber"), _sel(b"numberWithInt:"), 16), _nsstr("AVLinearPCMBitDepthKey"))

            err = ctypes.c_void_p(0)
            rec_alloc = msg_ptr(_cls(b"AVAudioRecorder"), _sel(b"alloc"))
            rec = msg_init_rec(rec_alloc, _sel(b"initWithURL:settings:error:"), url_ns, dict_ns, ctypes.byref(err))
            if rec and msg_bool(rec, _sel(b"prepareToRecord")) and msg_bool(rec, _sel(b"record")):
                if duration:
                    print(f"🎙️  Recording from microphone for {duration:.1f}s ... Speak now!")
                    time.sleep(duration)
                else:
                    print("🎙️  Recording from microphone... Speak now, and press Enter when finished!")
                    input()
                msg_ptr(rec, _sel(b"stop"))
                time.sleep(0.15)
                if os.path.isfile(abs_out) and os.path.getsize(abs_out) > 44:
                    return abs_out
        except Exception as mac_err:
            print(f"  [warning] macOS microphone recording error: {mac_err}")

    # 3. Windows built-in winmm.dll MCI recorder via ctypes (zero third-party packages required)
    if sys.platform == "win32":
        try:
            winmm = ctypes.windll.winmm
            mci = winmm.mciSendStringW
            abs_out = os.path.abspath(output_wav)
            mci("close sintam_rec", None, 0, 0)
            mci("open new type waveaudio alias sintam_rec", None, 0, 0)
            mci(f"set sintam_rec time format ms bitspersample 16 channels 1 samplespersec {IN_RATE}", None, 0, 0)
            mci("record sintam_rec", None, 0, 0)
            if duration:
                print(f"🎙️  Recording from microphone for {duration:.1f}s ... Speak now!")
                time.sleep(duration)
            else:
                print("🎙️  Recording from microphone... Speak now, and press Enter when finished!")
                input()
            mci("stop sintam_rec", None, 0, 0)
            mci(f'save sintam_rec "{abs_out}"', None, 0, 0)
            mci("close sintam_rec", None, 0, 0)
            if os.path.isfile(abs_out) and os.path.getsize(abs_out) > 44:
                return abs_out
        except Exception as win_err:
            print(f"  [warning] Windows microphone recording error: {win_err}")

    # 4. Linux `arecord` or cross-platform `sox` / `ffmpeg`
    arecord_bin = shutil.which("arecord")
    if arecord_bin:
        cmd = [arecord_bin, "-q", "-f", "S16_LE", "-r", str(IN_RATE), "-c", "1"]
        if duration:
            cmd += ["-d", str(int(max(1, duration)))]
        cmd.append(output_wav)
        if duration:
            print(f"🎙️  Recording from microphone for {duration:.1f}s ... Speak now!")
            subprocess.run(cmd, check=False)
        else:
            print("🎙️  Recording from microphone... Speak now, and press Enter when finished!")
            proc = subprocess.Popen(cmd)
            try:
                input()
            finally:
                proc.terminate()
                proc.wait(timeout=3)
        if os.path.isfile(output_wav) and os.path.getsize(output_wav) > 44:
            return output_wav

    raise RuntimeError(
        "Microphone recording requires microphone permission (macOS) or `pip install sounddevice numpy`."
    )


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
        with wave.open(io.BytesIO(message), "rb") as wf:
            frames = _convert_sample_width_to_16bit(wf.readframes(wf.getnframes()), wf.getsampwidth())
            return _resample(frames, wf.getframerate(), OUT_RATE)
    return message


def save_wav(pcm: bytes, path: str, rate: int = OUT_RATE) -> str:
    """Write raw 16-bit mono PCM to a WAV (or .m4a / .mp3 / .flac) file and return its path."""
    out_dir = os.path.dirname(os.path.abspath(path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    ext = os.path.splitext(path.lower())[1]
    if ext in ("", ".wav"):
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(rate)
            wf.writeframes(pcm)
        return path

    # Write temporary WAV first, then convert to requested format (.m4a, .mp3, .aac, .flac, etc.)
    tmp_fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
    os.close(tmp_fd)
    try:
        with wave.open(tmp_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(rate)
            wf.writeframes(pcm)
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            res = subprocess.run([ffmpeg_bin, "-y", "-v", "error", "-i", tmp_wav, path])
            if res.returncode == 0 and os.path.isfile(path):
                return path
        afconvert_bin = shutil.which("afconvert") or ("/usr/bin/afconvert" if os.path.isfile("/usr/bin/afconvert") else None)
        if afconvert_bin and ext in (".m4a", ".mp4", ".aac", ".caf", ".aiff", ".flac"):
            fmt_map = {
                ".m4a": ("m4af", "aac"),
                ".mp4": ("mp4f", "aac"),
                ".aac": ("adts", "aac"),
                ".caf": ("caff", "LEI16"),
                ".aiff": ("AIFF", "BEI16"),
                ".flac": ("flac", "flac"),
            }
            ffmt, dfmt = fmt_map[ext]
            res = subprocess.run([afconvert_bin, "-f", ffmt, "-d", dfmt, tmp_wav, path],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0 and os.path.isfile(path):
                return path
        # Fallback: copy as WAV
        shutil.copy(tmp_wav, path)
        return path
    finally:
        if os.path.exists(tmp_wav):
            try:
                os.remove(tmp_wav)
            except OSError:
                pass


def play_wav(path: str) -> bool:
    """Play a WAV file through the system speakers (macOS / Linux / Windows)."""
    if not path or not os.path.isfile(path):
        return False
    try:
        if sys.platform == "darwin":
            subprocess.run(["afplay", path], check=True)
            return True
        if sys.platform.startswith("linux"):
            subprocess.run(["aplay", "-q", path], check=True)
            return True
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return True
    except Exception as exc:
        print(f"  [warning] Could not play audio automatically: {exc}")
    return False


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
        status_msg = payload.get("message", "")
        if verbose:
            print(f"  [server] {status_msg}")
        lower_msg = status_msg.lower()
        if (
            status_msg.startswith("ERROR:")
            or "credits are depleted" in lower_msg
            or "quota exceeded" in lower_msg
            or "translator unavailable" in lower_msg
            or "api key is invalid" in lower_msg
            or "api_key_invalid" in lower_msg
        ):
            session.closed_reason = status_msg
    elif kind == "lang_detected":
        session.detected = f"{payload.get('source')} -> {payload.get('target')}"
    elif kind == "transcription":
        text = payload.get("text", "")
        if text:
            session.current_heard = text
        session.current_lang = payload.get("detected_lang") or session.current_lang
    elif kind == "translation":
        text = payload.get("text", "")
        if text:
            session.current_said = text
    elif kind == "turn_complete":
        session.finish_turn(payload)
        session.turns += 1


async def _receive_until_idle(
    ws,
    session: TranslationSession,
    timeout: float,
    sending_done: asyncio.Event | None = None,
) -> None:
    """Read server messages until the conversation goes quiet.

    Waits up to `timeout` seconds for the first reply after sending completes;
    once a turn has completed (and all input has been sent), stops after
    IDLE_AFTER_TURN seconds with no new messages."""
    deadline = time.monotonic() + timeout
    try:
        await _receive_loop(ws, session, deadline, sending_done)
    finally:
        session.finish_turn()  # print anything received after the last turn_complete


async def _receive_loop(
    ws,
    session: TranslationSession,
    deadline: float,
    sending_done: asyncio.Event | None = None,
) -> None:
    while True:
        all_sent = sending_done is None or sending_done.is_set()
        if all_sent and session.turns > 0:
            wait = IDLE_AFTER_TURN
        else:
            wait = deadline - time.monotonic()
        if wait <= 0:
            return
        try:
            message = await asyncio.wait_for(ws.recv(), timeout=wait)
        except asyncio.TimeoutError:
            if all_sent:
                return
            continue
        except websockets.ConnectionClosed as closed:
            session.closed_reason = f"code {closed.code} {closed.reason or ''}".strip()
            return
        if isinstance(message, bytes):
            session.audio.extend(_audio_frames(message))
        else:
            _handle_text(message, session)
            if session.closed_reason:
                return


async def translate_audio(
    audio_path: str,
    output_path: str = "output.wav",
    host: str = "127.0.0.1",
    port: int = 8000,
    target: str = "Tamil",
    voice: str = "Aoede",
    api_key: str = "",
    timeout: float = 45.0,
    play: bool = False,
) -> TranslationSession:
    """Stream any speech/voice file (.wav, .mp3, .m4a, .ogg, .flac, .aac, .pcm, etc.)
    to /ws/translate-auto, print text, and save translated speech."""
    resolved_path = resolve_audio_path(audio_path)
    if not os.path.isfile(resolved_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    pcm = None
    seconds = 0.0
    try:
        pcm = load_audio(resolved_path)
        seconds = len(pcm) / (IN_RATE * SAMPLE_WIDTH)
        print(f"Input audio : {resolved_path} ({seconds:.1f}s)")
        if rms_level(pcm) < 0.005:
            print("WARNING: the input audio is (nearly) silent - the server ignores silence, "
                  "so no translation will come back. Use a real speech recording.")
    except ValueError:
        print(f"Input audio : {resolved_path} (sending encoded audio directly to backend)")

    url = build_url(host, port, "/ws/translate-auto", target=target, voice=voice, api_key=api_key)
    session = TranslationSession()
    sending_done = asyncio.Event()
    async with websockets.connect(url, max_size=20 * 1024 * 1024) as ws:
        print(f"Connected   : {url.split('?')[0]} (target: {target})")
        receiver = asyncio.create_task(_receive_until_idle(ws, session, timeout + seconds, sending_done))

        try:
            if pcm is not None:
                # Stream in real time - the server slices speech by timing, like a live microphone
                for i in range(0, len(pcm), CHUNK_BYTES):
                    if receiver.done():
                        break
                    await ws.send(pcm[i:i + CHUNK_BYTES])
                    await asyncio.sleep(CHUNK_MS / 1000)

                # Send trailing silence and audio_eof so the backend flushes the turn immediately
                if not receiver.done():
                    silence_chunk = b"\x00" * CHUNK_BYTES
                    for _ in range(SILENCE_TAIL_CHUNKS):
                        await ws.send(silence_chunk)
                        await asyncio.sleep(0.03)
                    await ws.send(json.dumps({"type": "audio_eof"}))
            else:
                with open(resolved_path, "rb") as f:
                    raw_bytes = f.read()
                mime_type = detect_audio_mime_type(resolved_path, raw_bytes)
                await ws.send(json.dumps({
                    "type": "audio_file",
                    "mime_type": mime_type,
                    "data_b64": base64.b64encode(raw_bytes).decode("ascii"),
                }))
        except websockets.ConnectionClosed:
            pass
        finally:
            sending_done.set()

        await receiver

    if session.full_transcription:
        print(f"Transcribed : {session.full_transcription}")
    if session.full_translation:
        print(f"Translated  : {session.full_translation}")
    if session.audio and output_path:
        save_wav(bytes(session.audio), output_path)
        session.output_wav_path = output_path
        print(f"Saved Voice : {output_path} ({len(session.audio) / (OUT_RATE * 2):.1f}s of translated speech)")
        if play:
            print("Playing translated voice...")
            play_wav(output_path)
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
    output_path: str = "output.wav",
    play: bool = False,
) -> TranslationSession:
    """Send a phrase to /ws/translate-auto and print the translation + save voice audio."""
    url = build_url(host, port, "/ws/translate-auto", target=target, voice=voice, api_key=api_key)
    session = TranslationSession()
    sending_done = asyncio.Event()
    async with websockets.connect(url, max_size=20 * 1024 * 1024) as ws:
        print(f"Connected   : {url.split('?')[0]} ({source} -> {target})")
        try:
            first = await asyncio.wait_for(ws.recv(), timeout=timeout)
            if isinstance(first, str):
                _handle_text(first, session)
        except websockets.ConnectionClosed as closed:
            session.closed_reason = f"code {closed.code} {closed.reason or ''}".strip()
            return session
        print(f"  Sending: {text}")
        await ws.send(text)
        sending_done.set()
        await _receive_until_idle(ws, session, timeout, sending_done)

    if session.full_translation:
        print(f"Translated  : {session.full_translation}")
    if session.audio and output_path:
        save_wav(bytes(session.audio), output_path)
        session.output_wav_path = output_path
        print(f"Saved Voice : {output_path} ({len(session.audio) / (OUT_RATE * 2):.1f}s of translated speech)")
        if play:
            print("Playing translated voice...")
            play_wav(output_path)
    return session
