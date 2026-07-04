from fastapi import APIRouter, Request, Response
from backend.config.settings import settings

router = APIRouter()

@router.post("/voice")
async def twilio_voice_webhook(
    request: Request,
    source: str = "Sinhala",
    target: str = "Tamil"
):
    """
    HTTP POST Webhook endpoint for Twilio Voice calls.
    Returns TwiML instructing Twilio to:
    1. Stream call audio over WebSockets to our translator.
    2. Bridge/Dial the target forwarding number if configured, or translate 1-on-1.
    """
    host = request.url.netloc
    # Route over secure WebSocket (wss) if request was over HTTPS, else fallback to ws
    is_secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    protocol = "wss" if is_secure else "ws"
    
    stream_url = f"{protocol}://{host}/ws/twilio?source={source}&amp;target={target}"
    
    # Check if a target forwarding number is configured in settings
    forward_number = settings.TWILIO_FORWARD_NUMBER.strip()
    
    if forward_number:
        # Bridged 2-way call translation mode (using <Start><Stream> + <Dial>)
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Connecting your call with Sinhala and Tamil real-time translation.</Say>
    <Start>
        <Stream url="{stream_url}" track="both_tracks" />
    </Start>
    <Dial>{forward_number}</Dial>
</Response>"""
    else:
        # 1-on-1 translation mode (using <Connect><Stream>)
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Welcome to the Sinhala and Tamil voice translator. Please start speaking.</Say>
    <Connect>
        <Stream url="{stream_url}" />
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")
