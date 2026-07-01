import time
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_websocket_translation_latency():
    """
    Measures WebSocket translation response latency.
    """

    source = "Sinhala"
    target = "Tamil"
    ws_url = f"/ws/translate?source={source}&target={target}"

    with client.websocket_connect(ws_url) as websocket:

        start_time = time.time()

        # initial handshake
        websocket.receive_json()

        websocket.send_text("කොහොමද")
        websocket.send_bytes(b'\x00' * 1024)

        # wait for first meaningful response
        response = None
        for _ in range(5):
            try:
                response = websocket.receive_json()
                if response.get("type") in ["transcription", "translation"]:
                    break
            except Exception:
                break

        end_time = time.time()

        latency_ms = (end_time - start_time) * 1000

        print(f"\n[INFO] WebSocket latency: {latency_ms:.2f} ms")

        # Assert reasonable performance threshold
        assert latency_ms < 5000, "Latency too high (>5s)"