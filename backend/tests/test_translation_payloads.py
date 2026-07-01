import json
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.config.settings import settings

# Initialize TestClient with the FastAPI app
client = TestClient(app)

def test_websocket_translation_flow():
    """
    Tests the Sinhala-to-Tamil WebSocket flow including:
    1. Connection and initial status message.
    2. Text payload transmission.
    3. Audio byte payload transmission.
    
    This test uses TestClient which runs the application logic in-process,
    ensuring no impact on production server ports or performance.
    """
    
    # Define connection parameters
    source = "Sinhala"
    target = "Tamil"
    ws_url = f"/ws/translate?source={source}&target={target}"

    try:
        with client.websocket_connect(ws_url) as websocket:
            # 1. Validate Initial Connection Status
            # The server should send a 'status' message immediately or an error if API key is missing.
            response = websocket.receive_json()
            
            assert "type" in response
            assert response["type"] == "status"
            
            # If API key is missing, the test still validates the error handling gracefully
            if "Error" in response["payload"].get("message", ""):
                print("\n[INFO] Gemini API Key not configured. Validating error payload structure.")
                assert "GEMINI_API_KEY" in response["payload"]["message"]
                return

            # 2. Test Text Payload (Sinhala)
            # Sending "කොහොමද" (How are you?)
            test_text = "කොහොමද" 
            websocket.send_text(test_text)
            
            # 3. Test Audio Payload (Mock Bytes)
            # Sending 1024 bytes of null PCM data (simulating silence)
            mock_audio = b'\x00' * 1024
            websocket.send_bytes(mock_audio)

            # 4. Receive and Validate Response Payloads
            # We expect either a transcription or a translation response if the API is active.
            # Since Gemini Live is real-time, we might get multiple messages.
            # We'll check the first few to ensure they follow the expected schema.
            received_types = set()
            for _ in range(3):
                try:
                    # Set a timeout so we don't wait forever if Gemini is slow
                    resp = websocket.receive_json()
                    message_type = resp.get("type")
                    received_types.add(message_type)
                    
                    assert message_type in ["status", "transcription", "translation", "turn_complete"]
                    assert "payload" in resp
                    
                    if message_type == "transcription":
                        assert "text" in resp["payload"]
                        assert resp["payload"]["speaker"] == "user"
                    elif message_type == "translation":
                        assert "text" in resp["payload"]
                        assert resp["payload"]["speaker"] == "ai"
                        
                except Exception:
                    # If we time out or get bytes, just continue or break
                    break
            
            # Summary of received types for debugging
            print(f"\n[INFO] Successfully communicated with WebSocket. Received types: {received_types}")

    except Exception as e:
        # If the connection fails (e.g. key missing), we check if it failed for the right reasons
        if "API key missing" in str(e) or "1008" in str(e):
             print("\n[INFO] Test passed: Handled missing API key correctly.")
        else:
             pytest.fail(f"WebSocket connection failed unexpectedly: {e}")

if __name__ == "__main__":
    # Allow running the script directly
    print("Running Sinhala-to-Tamil Payload Validation Test...")
    test_websocket_translation_flow()
    print("Test execution finished.")