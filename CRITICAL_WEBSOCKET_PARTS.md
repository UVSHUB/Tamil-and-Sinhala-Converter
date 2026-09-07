# 🎯 CRITICAL PARTS OF WEBSOCKET CODE

## 1️⃣ LANGUAGE DETECTION - The Brain of Auto-Switching

**Location:** Lines 45-79 in `auto_stream_handler.py`

```python
def _detect_language(text: str) -> str | None:
    si = ta = 0
    for ch in text:
        cp = ord(ch)
        if 0x0D80 <= cp <= 0x0DFF:      # Sinhala Unicode range
            si += 1
        elif 0x0B80 <= cp <= 0x0BFF:    # Tamil Unicode range
            ta += 1
    
    total = si + ta
    if si / total >= 0.6:               # 60% threshold
        return "Sinhala"
    if ta / total >= 0.6:
        return "Tamil"
    return None
```

### 🔑 Why It's Critical:
- **Automatic language detection** without user input
- **Unicode ranges** are the key:
  - Sinhala: `0x0D80` to `0x0DFF`
  - Tamil: `0x0B80` to `0x0BFF`
- **60% threshold** prevents false positives with mixed text
- **Enables automatic session switching** - the app's superpower!

### How It Works:
```
User speaks: "Hallo, Sinhala katha karanawa"
                ↓
Gemini transcribes it
                ↓
Count Sinhala chars: 18, Tamil chars: 2
                ↓
Total: 20 chars → Sinhala: 18/20 = 90% ✓
                ↓
Result: SINHALA DETECTED → Switch to Tamil output session
```

---

## 2️⃣ DUAL GEMINI SESSION ARCHITECTURE - The Core Engine

**Location:** Lines 250-450 in `async def run_session()`

```python
async def run_session(target_code: str, in_queue: asyncio.Queue):
    source_lang = _CODE_LANG[_OPPOSITE[target_code]]  # e.g., "Sinhala"
    target_lang = _CODE_LANG[target_code]              # e.g., "Tamil"
    config = _make_config(target_code)
    
    while not client_disconnected.is_set():
        try:
            async with ai_client.aio.live.connect(
                model=model, config=config
            ) as session:
                # Two concurrent tasks run in parallel
                fwd = asyncio.create_task(forward_audio())      # Send audio to Gemini
                rcv = asyncio.create_task(receive_responses())  # Receive from Gemini
                
                await asyncio.wait([fwd, rcv], 
                    return_when=asyncio.FIRST_COMPLETED)
```

### 🔑 Why It's Critical:
- **TWO sessions run simultaneously** (not sequentially)
  - Session A: Sinhala input → Tamil output
  - Session B: Tamil input → Sinhala output
- **Both receive identical audio chunks**
- **Smart state switching**: Only active session broadcasts output
- **Error recovery**: Auto-reconnect if session fails

### Visual Flow:
```
┌─────────────────────────┐
│   Audio from client     │
└────────────┬────────────┘
             │
      ┌──────┴──────┐
      │             │
      ▼             ▼
  Queue TA      Queue SI
  (Tamil)       (Sinhala)
      │             │
      ▼             ▼
Session A         Session B
Sinha→Tamil      Tamil→Sinha
      │             │
      ├─ Check: Is this session active?
      │   └─ If NO: skip broadcasting
      │   └─ If YES: broadcast output ✓
      │
      ▼
   Broadcast to room
```

---

## 3️⃣ SMART STATE SWITCHING - The Intelligent Selector

**Location:** Lines 310-360 in `receive_responses()` function

```python
if sc.input_transcription and sc.input_transcription.text:
    transcript = sc.input_transcription.text
    detected = _detect_language(transcript)
    
    if detected is not None:
        # 🎯 CRITICAL LOGIC: Auto-detect which session should be active
        if detected == source_lang:
            if state["active"] != target_code:
                state["active"] = target_code  # ← Activate THIS session
                logger.info(f"Lang switch: {detected} -> active={target_code}")
        
        elif detected == target_lang:
            if state["active"] == target_code:
                state["active"] = _OPPOSITE[target_code]  # ← Switch to OTHER session
                logger.info(f"Detected {detected}, switching to {state['active']}")
```

### 🔑 Why It's Critical:
- **Real-time language switching without user action**
- **Prevents confusion** from running both sessions' outputs
- **Example**:
  ```
  Scenario: User starts speaking Sinhala
  └─ Detected = "Sinhala"
  └─ Source language of Session A = "Sinhala" ✓
  └─ state["active"] = "ta" (Tamil) → Activate Session A
  └─ Session A broadcasts Tamil translation
  
  Scenario: User switches to Tamil mid-conversation
  └─ Detected = "Tamil"
  └─ Target language of Session A = "Tamil" (user speaking output language!)
  └─ state["active"] = "si" (Sinhala) → Switch to Session B
  └─ Session B now translates Tamil → Sinhala
  ```

---

## 4️⃣ DUAL QUEUE SYSTEM - The Data Pipeline

**Location:** Lines 130-135 & 155-210 in `handle_auto_translation_stream()`

```python
# TWO queues: one per language direction
queue_ta: asyncio.Queue = asyncio.Queue(maxsize=300)
queue_si: asyncio.Queue = asyncio.Queue(maxsize=300)

# In read_client_forever():
if "bytes" in msg and msg["bytes"]:
    chunk = msg["bytes"]
    if manager.try_acquire_lock(room_id, client_ws):
        if not queue_ta.full():
            queue_ta.put_nowait(chunk)  # ← Same chunk to BOTH
        if not queue_si.full():
            queue_si.put_nowait(chunk)
```

### 🔑 Why It's Critical:
- **Prevents blocking**: `put_nowait()` doesn't wait for space
- **Parallel processing**: Both sessions consume same audio
- **Prevents buildup**: `maxsize=300` caps memory usage
- **Non-blocking session feeding**: If queue is full, skip adding (don't hold client reader)

### Queue Behavior:
```
Audio chunk arrives
    │
    ├─→ Queue TA (Tamil) ────→ Session A (Sinhala → Tamil)
    │
    └─→ Queue SI (Sinhala) ──→ Session B (Tamil → Sinhala)

Both sessions process:
  • Same audio input
  • Independently
  • In parallel
  • Without blocking each other
```

---

## 5️⃣ SAFE COMMUNICATION - Error-Proof Broadcasting

**Location:** Lines 137-153 in `async def safe_send_json()`

```python
async def safe_send_json(payload: dict) -> bool:
    try:
        await client_ws.send_json(payload)
        return True
    except Exception:
        client_disconnected.set()  # ← Mark client as gone
        return False               # ← Signal failure
```

### 🔑 Why It's Critical:
- **Graceful failure handling**: Catches all send exceptions
- **Connection loss detection**: Sets `client_disconnected` event
- **Prevents cascading errors**: Other tasks see the event and exit
- **Non-crashing system**: If one client drops, system doesn't crash

### Usage Pattern:
```python
# Safe: Catches connection errors
await safe_send_json({"type": "transcription", ...})

# vs. Unsafe: Would crash server
await client_ws.send_json({"type": "transcription", ...})
```

---

## 6️⃣ ROOM-BASED BROADCASTING - Multi-Client Support

**Location:** Lines 330-350 & 410-430 in `receive_responses()`

```python
# Broadcast to all clients in room EXCEPT speaker
await manager.broadcast_json_except(notif_payload, client_ws, room_id)

# Broadcast text to all clients
await manager.broadcast_json_except(transcript_payload, client_ws, room_id)

# Audio: Smart routing based on room size
room_size = len(manager.rooms.get(room_id, set()))
if room_size <= 1:
    # Solo mode: send audio to speaker
    await client_ws.send_bytes(part.inline_data.data)
else:
    # Multi-device mode: send to OTHERS ONLY (prevent feedback)
    await manager.broadcast_bytes_except(part.inline_data.data, client_ws, room_id)
```

### 🔑 Why It's Critical:
- **Walkie-talkie effect**: All room members hear translations
- **Feedback prevention**: Speaker doesn't hear own translation (in group mode)
- **Room isolation**: Each room is independent
- **Scalability**: Supports 1+ clients per room

### Broadcasting Logic:
```
Single User (room_size = 1)
└─ Send audio back to speaker
   └─ User hears their own translation

Multiple Users (room_size > 1)
├─ User A speaks Sinhala → translated to Tamil
└─ Users B, C, D get Tamil audio (NOT User A)
   └─ Prevents: Tamil audio → User A's mic → feedback loop
```

---

## 7️⃣ SPEAKER LOCK MECHANISM - Preventing Audio Chaos

**Location:** Lines 165-175 & 425-435

```python
# ACQUIRE lock when audio arrives
if manager.try_acquire_lock(room_id, client_ws):
    if not has_lock:
        has_lock = True
        await manager.broadcast_json_except(
            {"type": "room_state", "payload": {"speaker": True}},
            client_ws, room_id
        )

# RELEASE lock when turn complete
if sc.turn_complete:
    manager.release_lock(room_id, client_ws)  # ← Let others speak
    await manager.broadcast_json_except(
        {"type": "room_state", "payload": {"speaker": False}},
        client_ws, room_id
    )
```

### 🔑 Why It's Critical:
- **Prevents overlapping speakers**: Only one person processes audio at a time
- **Queue separation**: Locks ensure organized flow
- **UI Feedback**: Clients know who's speaking (speaker: true/false)
- **Turn-based system**: Enforces walkie-talkie protocol

### Lock State Machine:
```
Initial: No lock
    │
    ├─ User A sends audio
    └─→ Try acquire lock
        │
        ├─ SUCCESS ✓
        │  └─ Broadcast "speaker: true"
        │  └─ Process audio
        │  └─ Get translation & audio response
        │  └─ Broadcast outputs
        │  └─ Turn complete
        │  └─ Release lock
        │  └─ Broadcast "speaker: false"
        │
        ├─ FAILURE (lock held by User B)
        │  └─ Skip this audio chunk
        │  └─ Try again next chunk
        │
    User A can now send audio
```

---

## 8️⃣ ERROR RECOVERY & RECONNECTION - Fault Tolerance

**Location:** Lines 450-460 in `run_session()`

```python
except Exception as sess_err:
    if client_disconnected.is_set():
        return  # ← Don't reconnect if client left
    logger.warning(f"[{target_code}] session error: {sess_err}. Reconnecting...")
    await asyncio.sleep(1)  # ← Wait before retry
    # Loop continues, creating new session ↻
```

### 🔑 Why It's Critical:
- **Automatic recovery**: If Gemini connection fails, reconnects automatically
- **Prevents busy-looping**: 1-second delay between attempts
- **Respects client state**: Doesn't reconnect if client already left
- **Infinite retry**: Keeps trying until client disconnects

### Recovery Flow:
```
Session error: "Connection timeout"
    │
    ├─ Is client still connected?
    │  ├─ YES: Wait 1 second
    │  │       Create new Gemini session
    │  │       Resume processing ↻
    │  │
    │  └─ NO: Exit cleanly
    │
Retry continues until client leaves
```

---

## 9️⃣ TURN COMPLETION SIGNAL - Flow Control

**Location:** Lines 435-445 in `receive_responses()`

```python
if sc.turn_complete:
    manager.release_lock(room_id, client_ws)
    turn_payload = {"type": "turn_complete", "payload": {}}
    await safe_send_json(turn_payload)
    await manager.broadcast_json_except(turn_payload, client_ws, room_id)
    await manager.broadcast_json_except(
        {"type": "room_state", "payload": {"speaker": False}},
        client_ws, room_id
    )
```

### 🔑 Why It's Critical:
- **Marks end of speaking turn** (Gemini detected natural pause)
- **Releases resources**: Speaker lock freed for next user
- **UI Update**: Frontend knows to stop showing "speaking" state
- **Clean handoff**: Prepares room for next speaker

### Timeline of One Turn:
```
0ms   → Audio arrives, lock acquired
50ms  → Transcription arrives
100ms → Translation completes
150ms → Audio synthesis completes
200ms → turn_complete signal sent
201ms → Lock released
202ms → Next user can send audio
```

---

## 🔟 GRACEFUL SHUTDOWN - Cleanup on Disconnect

**Location:** Lines 500-515 in `finally` block

```python
try:
    await asyncio.wait(
        [client_reader, session_ta, session_si],
        return_when=asyncio.FIRST_COMPLETED,
    )
finally:
    # Cancel all three main tasks
    for t in [client_reader, session_ta, session_si]:
        t.cancel()
        try: await t
        except asyncio.CancelledError: pass
    logger.info(f"Handler for client in room {room_id} finished.")
```

### 🔑 Why It's Critical:
- **Resource cleanup**: All tasks properly cancelled
- **No hanging connections**: Prevents memory leaks
- **Graceful termination**: Tasks stop cleanly
- **Logging**: Tracks when handler completes

---

## 📊 IMPORTANCE RANKING

| Rank | Component | Impact | Why |
|------|-----------|--------|-----|
| 1 | **Language Detection** | ⭐⭐⭐⭐⭐ | Enables automatic switching - app's core feature |
| 2 | **Dual Sessions** | ⭐⭐⭐⭐⭐ | Process both directions simultaneously |
| 3 | **Smart State Switching** | ⭐⭐⭐⭐⭐ | Decides which session to broadcast |
| 4 | **Safe Communication** | ⭐⭐⭐⭐ | Prevents crashes from network failures |
| 5 | **Speaker Lock** | ⭐⭐⭐⭐ | Prevents audio chaos in multi-user rooms |
| 6 | **Dual Queues** | ⭐⭐⭐⭐ | Parallel processing without blocking |
| 7 | **Room Broadcasting** | ⭐⭐⭐⭐ | Multi-device support |
| 8 | **Error Recovery** | ⭐⭐⭐ | Resilience against API failures |
| 9 | **Turn Complete** | ⭐⭐⭐ | Flow control & lock release |
| 10 | **Graceful Shutdown** | ⭐⭐⭐ | Resource cleanup |

---

## 🎓 Quick Cheat Sheet

### What Makes This System Work:

```
┌─────────────────────────────────────────────────────────┐
│ 1. Detect language from transcription                   │
│    └─ Use Unicode ranges (Sinhala/Tamil specific)       │
│                                                          │
│ 2. Switch active session based on detected language     │
│    └─ Only active session broadcasts                    │
│                                                          │
│ 3. Run both sessions in parallel with dual queues       │
│    └─ Non-blocking, concurrent processing              │
│                                                          │
│ 4. Broadcast to all room members safely                 │
│    └─ Catch errors, gracefully handle disconnections    │
│                                                          │
│ 5. Use speaker lock to prevent overlapping audio        │
│    └─ Maintain walkie-talkie protocol                   │
│                                                          │
│ 6. Auto-recover from API failures                       │
│    └─ Reconnect sessions, respect client state          │
│                                                          │
│ 7. Clean shutdown on disconnect                         │
│    └─ Cancel tasks, free resources, prevent leaks       │
└─────────────────────────────────────────────────────────┘
```

### The Secret Sauce:
**Automatic language detection** + **dual simultaneous sessions** + **smart state switching** = **Natural walkie-talkie conversation without user intervention**

