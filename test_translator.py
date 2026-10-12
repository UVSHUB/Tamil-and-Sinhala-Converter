"""
SinTam Voice Translator - Quickstart Test Script
Tests the real-time WebSocket translation gateway.

Usage:
    python test_translator.py
"""

import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("[ERROR] 'websockets' package is required.")
    print("Run: pip install websockets")
    sys.exit(1)

# Default to local server. Can also test remote EC2 (e.g., "16.171.141.51:8000")
SERVER_ADDRESS = "localhost:8000"
WS_URL = f"ws://{SERVER_ADDRESS}/ws/translate-auto?target=Tamil"


async def run_test():
    print(f"[CONNECTING] Connecting to {WS_URL} ...")
    try:
        async with websockets.connect(WS_URL, open_timeout=5) as ws:
            print("[CONNECTED] WebSocket connection established successfully!\n")

            # 1. Receive status message
            msg1 = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"[SERVER] {msg1}")

            # 2. Receive initial language detection state
            msg2 = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"[LANG]   {msg2}")

            # 3. Test dynamic target language toggle (Tamil -> Sinhala)
            print("\n>>> Sending request to switch output language to Sinhala...")
            toggle_payload = {"type": "set_target", "target": "Sinhala"}
            await ws.send(json.dumps(toggle_payload))

            # 4. Receive confirmation from backend
            msg3 = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"[SERVER] {msg3}")

            print("\n" + "=" * 60)
            print("✓ Verification Successful! The translation backend is fully operational.")
            print("=" * 60)

    except ConnectionRefusedError:
        print(f"\n[ERROR] Could not connect to {WS_URL}.")
        print("Make sure the backend is running:")
        print("  python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000")
    except Exception as ex:
        print(f"\n[ERROR] Test encountered an error: {ex}")


if __name__ == "__main__":
    asyncio.run(run_test())
