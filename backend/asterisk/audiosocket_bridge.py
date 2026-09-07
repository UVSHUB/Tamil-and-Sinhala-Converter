"""
Asterisk AudioSocket to FastAPI WebSocket Bridge Service.

This service implements the Asterisk AudioSocket binary protocol (TCP)
and bridges live telephony audio calls from Asterisk PBX to the
Tamil & Sinhala real-time voice translation backend.

Audio Processing:
- Inbound: Asterisk 8kHz 16-bit SLIN PCM -> Resampled to 16kHz PCM -> FastAPI /ws/translate-auto
- Outbound: Gemini 16kHz/24kHz PCM -> Resampled to 8kHz SLIN PCM -> Asterisk AudioSocket
"""

import os
import sys
import asyncio
import logging
import struct
import json
try:
    import websockets
except ImportError:
    websockets = None


try:
    import audioop
except ImportError:
    audioop = None  # Pure-python or scipy fallback if audioop is omitted in future Python versions

# Configure Logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("audiosocket_bridge")

# Environment & Settings
AUDIOSOCKET_HOST = os.getenv("AUDIOSOCKET_HOST", "0.0.0.0")
AUDIOSOCKET_PORT = int(os.getenv("AUDIOSOCKET_PORT", "9092"))
BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:8000/ws/translate-auto")

# AudioSocket Message Types
TYPE_UUID = 0x01
TYPE_ERROR = 0x02
TYPE_HANGUP = 0x03
TYPE_AUDIO = 0x10


def resample_pcm(data: bytes, from_rate: int, to_rate: int, sample_width: int = 2, channels: int = 1) -> bytes:
    """
    Resample 16-bit signed linear PCM audio bytes from from_rate to to_rate.
    """
    if from_rate == to_rate or not data:
        return data

    if audioop is not None:
        resampled, _ = audioop.ratecv(data, sample_width, channels, from_rate, to_rate, None)
        return resampled

    # Fallback linear interpolation if audioop is not present
    step = from_rate / to_rate
    num_input_samples = len(data) // sample_width
    num_output_samples = int(num_input_samples / step)

    input_samples = struct.unpack(f">{num_input_samples}h", data)
    output_samples = []
    for i in range(num_output_samples):
        idx = i * step
        low = int(idx)
        high = min(low + 1, num_input_samples - 1)
        weight = idx - low
        sample = int((1 - weight) * input_samples[low] + weight * input_samples[high])
        output_samples.append(sample)

    return struct.pack(f">{len(output_samples)}h", *output_samples)


class AudioSocketBridge:
    """
    Handles a single Asterisk call AudioSocket connection and bridges it
    with a FastAPI WebSocket session.
    """

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, ws_url: str):
        self.reader = reader
        self.writer = writer
        self.ws_url = ws_url
        self.channel_id = "unknown"
        self.peer_addr = writer.get_extra_info("peername")
        self.is_running = True
        self.ws = None

    async def run(self):
        logger.info(f"📞 Asterisk call connected from {self.peer_addr}")
        try:
            async with websockets.connect(self.ws_url) as ws:
                self.ws = ws
                logger.info(f"🔗 Connected to Translation Backend WS: {self.ws_url}")

                # Run Asterisk->WS and WS->Asterisk streams concurrently
                await asyncio.gather(
                    self._asterisk_to_backend(),
                    self._backend_to_asterisk(),
                    return_exceptions=True
                )
        except websockets.exceptions.WebSocketException as wse:
            logger.error(f"WebSocket error bridging to backend: {wse}")
        except Exception as e:
            logger.error(f"Unexpected error in AudioSocket bridge session: {e}", exc_info=True)
        finally:
            self.is_running = False
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
            logger.info(f"📵 Asterisk call session ended for {self.peer_addr}")

    async def _asterisk_to_backend(self):
        """Read AudioSocket packets from Asterisk and send PCM audio to WebSocket."""
        state = None
        while self.is_running:
            try:
                header = await self.reader.readexactly(3)
                if not header:
                    break

                msg_type, length = struct.unpack(">BH", header)
                payload = await self.reader.readexactly(length) if length > 0 else b""

                if msg_type == TYPE_UUID:
                    self.channel_id = payload.hex() if isinstance(payload, bytes) else str(payload)
                    logger.info(f"AudioSocket UUID received: {self.channel_id}")

                elif msg_type == TYPE_AUDIO:
                    # Asterisk sends 8kHz 16-bit Mono SLIN -> Resample to 16kHz PCM for Gemini
                    pcm_16k = resample_pcm(payload, from_rate=8000, to_rate=16000)
                    if self.ws and not self.ws.closed:
                        await self.ws.send(pcm_16k)

                elif msg_type == TYPE_HANGUP:
                    logger.info(f"Asterisk hangup signal received for channel {self.channel_id}")
                    self.is_running = False
                    break

                elif msg_type == TYPE_ERROR:
                    logger.error(f"Asterisk AudioSocket error received: {payload}")
                    self.is_running = False
                    break

            except asyncio.IncompleteReadError:
                logger.warning(f"Asterisk stream disconnected (IncompleteReadError)")
                break
            except Exception as e:
                logger.error(f"Error reading from Asterisk AudioSocket: {e}")
                break

    async def _backend_to_asterisk(self):
        """Read translated audio/messages from WebSocket and send AudioSocket audio to Asterisk."""
        while self.is_running and self.ws:
            try:
                message = await self.ws.recv()

                if isinstance(message, bytes):
                    # Gemini audio output (16kHz or 24kHz PCM) -> Resample to 8kHz SLIN for Asterisk
                    slin_8k = resample_pcm(message, from_rate=16000, to_rate=8000)

                    # Pack into AudioSocket frame header: TYPE_AUDIO (0x10), len(slin_8k)
                    header = struct.pack(">BH", TYPE_AUDIO, len(slin_8k))
                    self.writer.write(header + slin_8k)
                    await self.writer.drain()

                elif isinstance(message, str):
                    try:
                        data = json.loads(message)
                        event_type = data.get("type")
                        if event_type == "transcription":
                            text = data.get("payload", {}).get("text", "")
                            speaker = data.get("payload", {}).get("speaker", "")
                            logger.info(f"🗣️ [{speaker.upper()}] Transcription: {text}")
                        elif event_type == "lang_detected":
                            lang = data.get("payload", {})
                            logger.info(f"🌐 Language Switch Detected: {lang.get('source')} -> {lang.get('target')}")
                    except json.JSONDecodeError:
                        pass

            except websockets.exceptions.ConnectionClosed:
                logger.info("Backend WebSocket closed")
                self.is_running = False
                break
            except Exception as e:
                logger.error(f"Error processing backend message for Asterisk: {e}")
                break


async def start_audiosocket_server():
    """Starts the AudioSocket TCP server listening for Asterisk connections."""
    def factory(reader, writer):
        bridge = AudioSocketBridge(reader, writer, BACKEND_WS_URL)
        asyncio.create_task(bridge.run())

    server = await asyncio.start_server(factory, AUDIOSOCKET_HOST, AUDIOSOCKET_PORT)
    logger.info(f"🚀 Asterisk AudioSocket Bridge running on {AUDIOSOCKET_HOST}:{AUDIOSOCKET_PORT}")
    logger.info(f"   Target WebSocket URL: {BACKEND_WS_URL}")

    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(start_audiosocket_server())
    except KeyboardInterrupt:
        logger.info("Server shutting down.")
