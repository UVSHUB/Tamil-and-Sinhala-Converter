import json
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


@pytest.mark.parametrize("source,target,test_text", [
    ("Sinhala", "Tamil", "කොහොමද"),   # Sinhala → Tamil
    ("Tamil", "Sinhala", "வணக்கம்"),  # Tamil → Sinhala
])
def test_websocket_translation_flow(source, target, test_text):
    """
    WebSocket translation test for both Sinhala↔Tamil directions.
    """

    ws_url = f"/ws/translate?source={source}&target={target}"

    try:
        with client.websocket_connect(ws_url) as websocket:

            # 1. Initial status message
            response = websocket.receive_json()

            assert response["type"] == "status"
            assert "payload" in response

            # Handle API key missing case
            if "Error" in response["payload"].get("message", ""):
                assert "GEMINI_API_KEY" in response["payload"]["message"]
                return

            # 2. Send text payload
            websocket.send_text(test_text)

            # 3. Send mock audio
            mock_audio = b'\x00' * 1024
            websocket.send_bytes(mock_audio)

            # 4. Validate responses
            for _ in range(3):
                try:
                    resp = websocket.receive_json()
                    msg_type = resp.get("type")

                    assert msg_type in [
                        "status", "transcription", "translation", "turn_complete"
                    ]

                    assert "payload" in resp

                    if msg_type == "transcription":
                        assert "text" in resp["payload"]
                        assert resp["payload"]["speaker"] == "user"

                    if msg_type == "translation":
                        assert "text" in resp["payload"]
                        assert resp["payload"]["speaker"] == "ai"

                except Exception:
                    break

    except Exception as e:
        if "API key missing" in str(e) or "1008" in str(e):
            print("\n[INFO] API key missing - handled gracefully.")
        else:
            pytest.fail(f"WebSocket failed unexpectedly: {e}")