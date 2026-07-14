# WebSocket Architecture Roadmap - Tamil & Sinhala Translator

## 📊 High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         WEBSOCKET ENDPOINTS                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  /ws/translate (Manual Mode)                                        │
│  ├─ User specifies source and target language                       │
│  ├─ Single Gemini session (for specified direction)                 │
│  ├─ Simple 1:1 translation                                          │
│                                                                     │
│  /ws/translate-auto (Auto-Detect Mode) ⭐ [Main Focus]              │
│  ├─ No language selection needed                                    │
│  ├─ Dual Gemini sessions running simultaneously                     │
│  ├─ Smart language detection & switching                            │
│  ├─ Room-based multi-device support                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 AUTO-DETECT MODE COMPLETE FLOW

### Phase 1: Client Connection & Initialization

```
CLIENT (Frontend)                                BACKEND
     │                                              │
     │──── WebSocket Connect ──────────────────────>│
     │     /ws/translate-auto                       │
     │     voice=Aoede                              │
     │     room=ABC123                              │
     │                                              │
     │                                              ├─ Create AI Client
     │                                              │  (Google Gemini API)
     │                                              │
     │                                              ├─ Initialize State:
     │                                              │  {
     │                                              │    "active": "ta",
     │                                              │    "last_notified": None
     │                                              │  }
     │                                              │
     │                                              ├─ Create Queues:
     │                                              │  ├─ queue_ta (Tamil)
     │                                              │  └─ queue_si (Sinhala)
     │                                              │
     │                                              ├─ Start 3 Concurrent Tasks:
     │                                              │  1. read_client_forever()
     │                                              │  2. run_session("ta", queue_ta)
     │                                              │  3. run_session("si", queue_si)
     │                                              │
     │<──── lang_detected (Sinhala->Tamil) ────────│
     │<──── status (Connected) ───────────────────│
```

### Phase 2: Dual Gemini Sessions Setup

```
┌──────────────────────────────────────────────────────────────────────┐
│                    TWO PARALLEL GEMINI SESSIONS                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  SESSION A (Tamil Output)                SESSION B (Sinhala Output)│
│  ├─ Config:                              ├─ Config:                │
│  │  target_language_code: "ta"           │  target_language_code: "si"
│  │  echo_target_language: True           │  echo_target_language: True
│  │  response_modalities: ["AUDIO"]       │  response_modalities: ["AUDIO"]
│  │  input_transcription: enabled         │  input_transcription: enabled
│  │  output_transcription: enabled        │  output_transcription: enabled
│  │  auto_activity_detection: 500ms       │  auto_activity_detection: 500ms
│  │                                        │
│  ├─ Purpose:                             ├─ Purpose:
│  │  If user speaks SINHALA               │  If user speaks TAMIL
│  │  → Translate to TAMIL                 │  → Translate to SINHALA
│  │  → Output Tamil speech                │  → Output Sinhala speech
│  │                                        │
│  ├─ Connected to: queue_ta               ├─ Connected to: queue_si
│  └─ Listens for audio input              └─ Listens for audio input
│                                                                      │
│  BOTH receive identical audio chunks from the client               │
│  But ONLY the ACTIVE one broadcasts its output                    │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Phase 3: Real-Time Audio Processing Flow

```
STEP-BY-STEP AUDIO PROCESSING CYCLE
═══════════════════════════════════════════════════════════════════════

1️⃣  CLIENT SENDS AUDIO
    ┌─────────────────────────────────────────┐
    │ User speaks into microphone              │
    │ Frontend Web Audio API captures audio    │
    │ Downsamples to 16kHz PCM                 │
    │ Chunks into binary packets               │
    │ Sends via WebSocket.send_bytes(chunk)    │
    └─────────────────────────────────────────┘
                          │
                          ▼
2️⃣  BACKEND RECEIVES AUDIO
    ┌─────────────────────────────────────────┐
    │ read_client_forever() receives bytes     │
    │ Acquires speaker lock (prevents overlap) │
    │ Broadcasts "speaker: true" to room       │
    │ Adds chunk to BOTH queues:               │
    │  ├─ queue_ta.put_nowait(chunk)           │
    │  └─ queue_si.put_nowait(chunk)           │
    └─────────────────────────────────────────┘
                          │
                          ▼
3️⃣  GEMINI SESSIONS RECEIVE AUDIO
    ┌─────────────────────────────────────────┐
    │ forward_audio() tasks pull from queues   │
    │ Both Session A & B get same audio        │
    │ Send to Gemini via:                      │
    │  session.send_realtime_input(            │
    │    audio=Blob(                           │
    │      data=chunk,                         │
    │      mime_type="audio/pcm;rate=16000"    │
    │    )                                     │
    │  )                                       │
    └─────────────────────────────────────────┘
                          │
                          ▼
4️⃣  GEMINI PROCESSES & RESPONDS
    ┌─────────────────────────────────────────┐
    │ Session A (Tamil target):                │
    │  ├─ Transcribe: "Sinhala text"           │
    │  ├─ Translate: "Tamil text"              │
    │  ├─ Synthesize: "Tamil audio"            │
    │                                          │
    │ Session B (Sinhala target):              │
    │  ├─ Transcribe: "Tamil text"             │
    │  ├─ Translate: "Sinhala text"            │
    │  ├─ Synthesize: "Sinhala audio"          │
    └─────────────────────────────────────────┘
                          │
                          ▼
5️⃣  LANGUAGE DETECTION & STATE SWITCHING
    ┌─────────────────────────────────────────┐
    │ BOTH sessions provide input_transcription│
    │                                          │
    │ _detect_language() analyzes text:        │
    │  ├─ Count Sinhala Unicode chars          │
    │  ├─ Count Tamil Unicode chars            │
    │  ├─ Calculate percentage (60% threshold) │
    │  └─ Return "Sinhala" OR "Tamil"          │
    │                                          │
    │ IF detected matches source_lang:         │
    │   → state["active"] = target_code        │
    │                                          │
    │ IF detected matches target_lang:         │
    │   → state["active"] = opposite_code      │
    └─────────────────────────────────────────┘
                          │
                          ▼
6️⃣  BROADCAST LANGUAGE DETECTION
    ┌─────────────────────────────────────────┐
    │ IF language pair changed:                │
    │                                          │
    │ Send to CLIENT:                          │
    │  {                                       │
    │    "type": "lang_detected",              │
    │    "payload": {                          │
    │      "source": "Sinhala",                │
    │      "target": "Tamil"                   │
    │    }                                     │
    │  }                                       │
    │                                          │
    │ Broadcast to OTHER CLIENTS in room       │
    └─────────────────────────────────────────┘
                          │
                          ▼
7️⃣  BROADCAST TRANSCRIPTION (USER'S SPEECH)
    ┌─────────────────────────────────────────┐
    │ IF state["active"] == target_code:      │
    │ (Only from the active session)           │
    │                                          │
    │ Send to CLIENT:                          │
    │  {                                       │
    │    "type": "transcription",              │
    │    "payload": {                          │
    │      "speaker": "user",                  │
    │      "text": "Sinhala word spoken",      │
    │      "detected_lang": "Sinhala"          │
    │    }                                     │
    │  }                                       │
    │                                          │
    │ Broadcast to OTHER CLIENTS in room       │
    │ (Everyone sees what was said)            │
    └─────────────────────────────────────────┘
                          │
                          ▼
8️⃣  BROADCAST TRANSLATION TEXT
    ┌─────────────────────────────────────────┐
    │ IF output_transcription available:      │
    │ (Only from active session)               │
    │                                          │
    │ Send to CLIENT:                          │
    │  {                                       │
    │    "type": "translation",                │
    │    "payload": {                          │
    │      "speaker": "ai",                    │
    │      "text": "Tamil translation"         │
    │    }                                     │
    │  }                                       │
    │                                          │
    │ Broadcast to OTHER CLIENTS in room       │
    │ (Everyone sees the translation)          │
    └─────────────────────────────────────────┘
                          │
                          ▼
9️⃣  BROADCAST TRANSLATED AUDIO
    ┌─────────────────────────────────────────┐
    │ IF model_turn contains audio:            │
    │ (Synthesized speech in target language)  │
    │                                          │
    │ Check room size:                         │
    │                                          │
    │ IF room_size == 1:                       │
    │   Send audio to SPEAKER                  │
    │   (Solo mode: user hears translation)    │
    │                                          │
    │ IF room_size > 1:                        │
    │   Send audio to OTHER CLIENTS ONLY       │
    │   (Walkie-talkie mode: prevent feedback) │
    │                                          │
    │ Send: WebSocket.send_bytes(audio_data)   │
    └─────────────────────────────────────────┘
                          │
                          ▼
🔟  TURN COMPLETE SIGNAL
    ┌─────────────────────────────────────────┐
    │ IF server marks turn_complete:           │
    │                                          │
    │ Release speaker lock:                    │
    │  manager.release_lock(room_id, client)   │
    │                                          │
    │ Send to CLIENT:                          │
    │  {"type": "turn_complete", ...}          │
    │                                          │
    │ Broadcast to OTHERS:                     │
    │  {"type": "room_state", "speaker": false}│
    │                                          │
    │ (Now other clients can speak)            │
    └─────────────────────────────────────────┘
```

---

## 🏗️ State Management Architecture

```
CLIENT STATE (in real-time)
─────────────────────────────────────────────────────────────────────

{
  "active": "ta" or "si",           ← Which session is active
  "last_notified": "Sinhala->Tamil" ← Last language pair broadcast
}

LOGIC:
  Initial: active = "ta" (assuming user speaks Sinhala)

  When transcription arrives:
    1. Detect language using Unicode ranges
    2. IF detected == source_lang → active = target_code
    3. IF detected == target_lang → active = opposite_code
    4. Check if notification needed (changed from last_notified)
    5. If changed, broadcast language detection event
```

---

## 🔐 Room & Concurrency Management

```
ROOM LOCKING MECHANISM
─────────────────────────────────────────────────────────────────────

Problem: Multiple speakers overlapping creates chaos
Solution: Speaker lock prevents concurrent audio

Flow:
  1. Client sends audio → try_acquire_lock(room_id, client_ws)
  2. If lock acquired:
     ├─ Broadcast "speaker: true" to other clients
     ├─ Add audio to both queues
     └─ Hold lock during speaking

  3. When turn_complete:
     ├─ Call release_lock(room_id, client_ws)
     ├─ Broadcast "speaker: false" to other clients
     └─ Other clients can now send audio

ROOM DATA STRUCTURE:
  manager.rooms = {
    "room_ABC123": {
      <WebSocket Client A>,
      <WebSocket Client B>,
      <WebSocket Client C>
    },
    "room_XYZ789": {
      <WebSocket Client D>,
      <WebSocket Client E>
    }
  }
```

---

## 📨 WebSocket Message Types

### 1. **lang_detected** - Language pair changed

```json
{
  "type": "lang_detected",
  "payload": {
    "source": "Sinhala",
    "target": "Tamil"
  }
}
```

### 2. **transcription** - User's spoken words (transcribed)

```json
{
  "type": "transcription",
  "payload": {
    "speaker": "user",
    "text": "Spoken Sinhala text",
    "detected_lang": "Sinhala"
  }
}
```

### 3. **translation** - AI-translated text

```json
{
  "type": "translation",
  "payload": {
    "speaker": "ai",
    "text": "Tamil translation of the text"
  }
}
```

### 4. **turn_complete** - Speaking turn finished

```json
{
  "type": "turn_complete",
  "payload": {}
}
```

### 5. **room_state** - Speaker status in room

```json
{
  "type": "room_state",
  "payload": {
    "speaker": true // or false
  }
}
```

### 6. **status** - Connection status

```json
{
  "type": "status",
  "payload": {
    "message": "Connected to room 'ABC123'! Other devices..."
  }
}
```

### 7. **pong** - Keepalive response (received from frontend ping)

```json
{
  "type": "pong"
}
```

### 8. **audio (binary)** - Translated speech audio

```
Raw binary bytes (WebSocket.send_bytes())
Format: PCM 16kHz
```

---

## 🎯 Key Data Flows

### Audio Path (Client → Backend → Gemini → Client)

```
┌─────────────┐
│   CLIENT    │ Speaks into mic
└──────┬──────┘
       │ Web Audio API
       │ 16kHz PCM chunks
       ▼
┌─────────────┐
│  WEBSOCKET  │ Binary frames
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│ read_client_forever │ Receives & enqueues
└──────┬──────────────┘
       │
       ├─── queue_ta ───┐
       │                │
       └─── queue_si ───┤
                        │
              ┌─────────▼─────────┐
              │  forward_audio()  │ Both tasks
              │  (Session A & B)  │ pull same audio
              └────────┬──────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │   GEMINI API         │
            │ (Process & Translate)│
            └────────┬─────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
    Transcribe  Translate  Synthesize
    (Input)     (Process)   (Audio)
        │            │            │
        └────────────┼────────────┘
                     │
            ┌────────▼────────┐
            │ receive_responses│ Both sessions
            │ (Session A & B)  │ send responses
            └────────┬─────────┘
                     │
              ┌──────┴──────┐
              │             │
           Active    Inactive
            Session  Session
              │        (Skip)
              │
        ┌─────▼──────┐
        │ Broadcast  │ Text + Audio
        │ to Clients │
        └────────────┘
```

---

## ⚡ Key Algorithms

### 1. Language Detection Algorithm

```python
def _detect_language(text):
    si = ta = 0
    for char in text:
        code_point = ord(char)
        if 0x0D80 <= code_point <= 0x0DFF:  # Sinhala range
            si += 1
        elif 0x0B80 <= code_point <= 0x0BFF:  # Tamil range
            ta += 1

    total = si + ta
    if total == 0:
        return None

    if si / total >= 0.6:
        return "Sinhala"
    if ta / total >= 0.6:
        return "Tamil"
    return None
```

### 2. Session Selection Algorithm

```
When transcription arrives:

IF language_code == source_language:
  → This session is translating correctly
  → Mark this session as ACTIVE
  → Broadcast its output

ELIF language_code == target_language:
  → User switched languages
  → Deactivate current session
  → Switch to opposite session
  → Broadcast the opposite session's output

This enables automatic language switching!
```

### 3. Audio Broadcasting Algorithm

```
IF room_size == 1:
  → Solo mode (just speaker)
  → Send audio to SPEAKER themselves
  → User hears their own translation

ELIF room_size > 1:
  → Walkie-talkie mode (multiple devices)
  → Send audio to OTHER clients ONLY
  → Prevents feedback loop:
     Speaker talks → Translated audio → Microphone input (feedback)
```

---

## 🔄 Error Handling & Recovery

```
ERROR SCENARIO                      HANDLING
───────────────────────────────────────────────────────────────────

1. API Key Missing
   └─ Send error JSON message
   └─ Close connection (code 1008)
   └─ Return early

2. Client Disconnects
   └─ Catch WebSocketDisconnect
   └─ Log disconnection
   └─ Set client_disconnected event
   └─ Send sentinel (None) to queues
   └─ All tasks exit gracefully

3. Session Error (Gemini API fails)
   └─ Catch exception in run_session()
   └─ Log error
   └─ Wait 1 second
   └─ Attempt reconnection
   └─ Loop continues until client disconnects

4. Send Fails
   └─ Catch exception in safe_send_json()
   └─ Set client_disconnected event
   └─ Return False
   └─ Calling code handles gracefully

5. Queue Full
   └─ Check queue.full() before adding
   └─ Skip adding if full
   └─ Prevents memory buildup
```

---

## 🚀 Performance Optimizations

```
FEATURE                         BENEFIT
────────────────────────────────────────────────────────────────────

1. Dual Queue System            Process two language directions
   (queue_ta, queue_si)         simultaneously without blocking

2. Non-blocking Enqueue         put_nowait() instead of await put()
   (put_nowait)                 Prevents client reader from blocking

3. Timeout on Queue Get         asyncio.wait_for(timeout=0.3)
   (0.3 seconds)                Keep session alive if audio empty

4. Speaker Lock                 Prevent concurrent audio processing
   (try_acquire_lock)           Reduces confusion & overlaps

5. Async Context Manager        Proper resource cleanup
   (async with session)         Connection closed automatically

6. Task Cancellation            First-to-complete wins
   (FIRST_COMPLETED)            Stop unneeded tasks early

7. Concurrent Tasks             3 tasks run in parallel:
   (read, session_ta, session)  1. Client listener
   _si                          2. Tamil session
                                3. Sinhala session
```

---

## 📊 Complete State Diagram

```
                    ┌─── NO API KEY ───┐
                    │                  │
              CONNECT                  ▼
                │              SEND ERROR
                │              CLOSE (1008)
                ▼                    END
        ┌─────────────┐
        │  CONNECTED  │
        │  Initialize │
        │  Dual       │
        │  Sessions   │
        └──────┬──────┘
               │
        ┌──────▼──────────────┐
        │ DUAL SESSIONS READY │
        │ (Tamil & Sinhala)   │
        └──────┬──────────────┘
               │
        ┌──────▼─────────────────┐
        │ WAITING FOR AUDIO      │
        │ - Both queues ready    │
        │ - Both sessions listen │
        └──────┬─────────────────┘
               │
        ┌──────▼─────────────────┐
        │ AUDIO RECEIVED         │
        │ - Enqueue to both      │
        │ - Gemini processes     │
        └──────┬─────────────────┘
               │
        ┌──────▼─────────────────┐
        │ LANGUAGE DETECTED      │
        │ - Analyze transcription│
        │ - Switch active session│
        │ - Broadcast detection  │
        └──────┬─────────────────┘
               │
        ┌──────▼─────────────────┐
        │ BROADCAST OUTPUTS      │
        │ - Transcription (user) │
        │ - Translation (ai)     │
        │ - Audio (synthesized)  │
        └──────┬─────────────────┘
               │
        ┌──────▼─────────────────┐
        │ TURN COMPLETE          │
        │ - Release lock         │
        │ - Notify clients       │
        └──────┬─────────────────┘
               │
        ┌──────▼─────────────────┐
        │ READY FOR NEXT AUDIO   │
        └──────┬─────────────────┘
               │
              ┌┴─ CLIENT DISCONNECTS ──┐
              │                        │
              ▼                        ▼
        CLEANUP TASKS            CLEANUP TASKS
        CLOSE CONNECTIONS        CLOSE CONNECTIONS
        END                       END
```

---

## 🎓 Summary: The 5-Minute Overview

1. **Client connects** via WebSocket with room ID
2. **Backend creates 2 Gemini sessions** (one for each language direction)
3. **User speaks** → Audio sent to backend
4. **Both sessions process simultaneously** (dual translation)
5. **Language detection** analyzes the transcription
6. **Active session selected** based on detected language
7. **Only active session's output broadcast** (prevents noise)
8. **Text + Audio sent back** to all room clients
9. **Speaker lock released** → Next person can speak
10. **Loop continues** until client disconnects

### Key Innovation: **Automatic Language Switching**

- No need for user to say "switch language"
- System detects language automatically
- Switches active session on the fly
- Enables natural conversation flow
