import asyncio
from fastapi import WebSocket, WebSocketDisconnect

async def handle_voice_translation_stream(client_ws: WebSocket):
 
    await client_ws.accept()
    print("🚀 [Day 1 Server] Client successfully handshake-connected over WebSocket!")

    try:
        
        while True:
            
            try:
               
                data = await client_ws.receive_bytes()
                chunk_size = len(data)
                print(f" Received raw audio chunk packet. Size: {chunk_size} bytes.")
                
                
                await client_ws.send_json({
                    "status": "received", 
                    "bytes": chunk_size,
                    "message": "Local backend pipeline alive. Ready for Gemini API injection."
                })
                
            except RuntimeError:
                
                text_data = await client_ws.receive_text()
                print(f"💬 Received text configuration command: {text_data}")
                await client_ws.send_json({"status": "acknowledged", "echo": text_data})

    except WebSocketDisconnect:
        print(" [Day 1 Server] Client browser tab closed or network dropped.")
    except Exception as e:
        print(f" Structural error inside stream_handler worker: {e}")
    finally:
        print(" Cleaning up stream connection context threads.")