"""
SinTam WebSocket Client
Connects directly to the FastAPI backend WebSocket for real-time translation.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.parse
import wave
from dataclasses import dataclass, field
from typing import Callable, Optional, List, Dict, Any

try:
    import websockets
except ImportError:
    raise ImportError("websockets library is required. Install it using: pip install websockets")

logger = logging.getLogger("websocket_client")


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
        """Saves the received 24kHz PCM audio as a standard WAV file."""
        if not self.audio_bytes:
            raise ValueError("No audio bytes received in this turn.")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(self.sample_rate)
            wf.writeframes(self.audio_bytes)
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

    async def send_wav_file(self, wav_path: str, chunk_ms: int = 100) -> None:
        """
        Streams a WAV audio file to the backend in real time.
        Converts/reads to 16kHz 16-bit mono PCM.
        """
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"WAV file not found: {wav_path}")

        with wave.open(wav_path, "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()

            # We need 16kHz 16-bit mono
            chunk_frames = int(framerate * (chunk_ms / 1000.0))
            chunk_delay = chunk_ms / 1000.0

            while True:
                frames = wf.readframes(chunk_frames)
                if not frames:
                    break
                await self.send_audio_chunk(frames)
                await asyncio.sleep(chunk_delay * 0.9)  # Near real-time streaming

    async def translate_text(self, text: str, timeout: float = 15.0) -> TranslationResult:
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
        return await self.wait_for_turn(timeout=timeout)

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
                    self._current_audio_chunks.append(message)
                    if self.on_audio_chunk:
                        try:
                            self.on_audio_chunk(message)
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
                        self._current_user_text = text
                        if self.on_transcription:
                            self.on_transcription(text, delta)

                    elif msg_type == "translation":
                        text = payload.get("text", "")
                        delta = payload.get("delta", "")
                        self._current_ai_text = text
                        if self.on_translation:
                            self.on_translation(text, delta)

                    elif msg_type == "turn_complete":
                        final_user = payload.get("user_text", self._current_user_text)
                        final_ai = payload.get("ai_text", self._current_ai_text)
                        total_audio = b"".join(self._current_audio_chunks)

                        result = TranslationResult(
                            source_language=self._detected_source,
                            target_language=self._detected_target,
                            user_transcript=final_user,
                            translated_text=final_ai,
                            audio_bytes=total_audio,
                            sample_rate=24000,
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
