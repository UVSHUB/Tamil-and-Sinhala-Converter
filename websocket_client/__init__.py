"""
SinTam WebSocket Client Package
A standalone Python client to connect directly to the FastAPI backend WebSocket
for real-time Sinhala ↔ Tamil speech and text translation.
"""

from .client import SinTamWebSocketClient, TranslationResult

__all__ = ["SinTamWebSocketClient", "TranslationResult"]
