# 🏛️ System Architecture & Engineering Flowcharts

This document details the architectural design, data pipelines, sequence lifecycles, and deployment topologies of the **Sinhala ↔ Tamil Real-Time Continuous Voice Translator (SinTam)**.

---

## 1. High-Level System Architecture

The following flowchart illustrates the complete component layout, from the user's microphone to the browser audio playback and external AI model layers:

```mermaid
flowchart TB
    subgraph ClientLayer["🖥️ Client Application Layer"]
        User(["👤 User Speaking"])
        Mic["🎤 Browser Microphone Input"]
        Worklet["⚡ AudioWorklet Processor<br/>(16kHz Mono Int16 PCM, 100ms frames)"]
        UI["💻 React SPA Dashboard<br/>(Language Selector, Captions, Waveform)"]
        Speaker["🔊 Web Audio API Player<br/>(AudioContext Destination)"]
    end

    subgraph NetworkGateway["🌐 WebSocket Gateway & Networking"]
        WS["⚡ FastAPI WebSocket Gateway<br/>/ws/translate-auto"]
        Router["🔀 Connection & Room Manager<br/>(Broadcast & State Sync)"]
    end

    subgraph AudioEngine["⚙️ Real-Time Audio & Cadence Engine"]
        Ingest["📥 Stream Ingest Queue"]
        VAD["📊 Voice Activity Detector & RMS Gate<br/>(RMS >= 0.005)"]
        Slicer["⏱️ Cadence Slicer<br/>(3.0s Max Cadence / 250ms Pause Flush)"]
        ProcQueue["📦 Processing Queue"]
    end

    subgraph AILayer["🤖 Google Gemini AI Core"]
        ASR_Trans["🧠 Gemini 3.5 Flash Lite<br/>(Tri-Lingual ASR & Translation)"]
        TTS["🗣️ Gemini 3.8 Flash Lite TTS<br/>(Natural Speech Synthesis)"]
    end

    %% Connections
    User --> Mic --> Worklet -->|PCM binary packets| WS
    UI -.->|JSON Control: set_target| WS
    WS --> Router --> Ingest --> VAD --> Slicer --> ProcQueue
    ProcQueue --> ASR_Trans
    ASR_Trans -->|Translated Text| TTS
    ASR_Trans -->|JSON Transcripts & Detected Lang| WS
    TTS -->|Binary Audio Bytes| WS
    WS -->|Transcripts & Status| UI
    WS -->|Audio PCM / WAV Chunks| Speaker
```

---

## 2. End-to-End WebSocket Sequence Diagram

This sequence diagram depicts the chronological message exchange between the Client, the FastAPI Backend, and the Google Gemini AI APIs:

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Browser as Browser Client (AudioWorklet)
    participant Gateway as FastAPI Gateway (/ws/translate-auto)
    participant Slicer as Cadence Slicer & VAD
    participant GeminiTrans as Gemini 3.5 Flash Lite
    participant GeminiTTS as Gemini 3.8 Flash Lite TTS

    User->>Browser: Speaks "Kohomada oyata?"
    Browser->>Gateway: WebSocket Connect (?target=Tamil)
    Gateway-->>Browser: 200 Handshake OK (Status: Active)
    
    loop Stream Audio Packets (Every 100ms)
        Browser->>Gateway: Send binary PCM chunk (3200 bytes)
        Gateway->>Slicer: Push to Ingest Queue
    end

    Note over User,Browser: User finishes speaking (250ms pause)
    Browser--xGateway: Audio stops (Frontend drops silence)
    Slicer->>Slicer: Detect 180ms timeout with buffered audio
    Slicer->>GeminiTrans: Submit Audio Slice (450ms - 3.0s WAV)

    GeminiTrans-->>Slicer: JSON {"detected": "Sinhala", "trans": "Kohomada", "translation": "எப்படி இருக்கிறீர்கள்?"}
    
    par Stream Transcripts
        Slicer->>Gateway: Send JSON Transcripts
        Gateway->>Browser: Emit lang_detected & translation JSON
        Browser->>User: Display Tamil text caption on UI
    and Stream Synthesized Audio
        Slicer->>GeminiTTS: Synthesize text ("எப்படி இருக்கிறீர்கள்?")
        GeminiTTS-->>Slicer: Synthesized PCM / WAV Audio Bytes
        Slicer->>Gateway: Forward binary audio
        Gateway->>Browser: Binary audio stream chunk
        Browser->>User: 🔊 Plays natural Tamil speech through speaker
    end
```

---

## 3. Cadence Slicing & Voice Activity Decision Flowchart

How the continuous engine prevents latency and slices speech without waiting for users to finish:

```mermaid
flowchart TD
    Start["Audio Packet Received"] --> CalcRMS["Calculate RMS Energy"]
    CalcRMS --> IsVoiced{"RMS >= 0.005?<br/>(Voiced Speech?)"}
    
    IsVoiced -- Yes --> ResetSilence["Reset Silence Counter<br/>Append to Accumulated Buffer"]
    IsVoiced -- No --> AddSilence["Increment Silence Bytes<br/>Append to Accumulated Buffer"]
    
    ResetSilence --> CheckMax{"Buffer Duration >= 3.0s?<br/>(Continuous Speech Limit)"}
    AddSilence --> CheckPause{"Buffer >= 450ms AND<br/>Silence >= 250ms?"}
    
    CheckMax -- Yes --> SliceCont["✂️ Slice Audio (Retain 120ms boundary overlap)"]
    CheckMax -- No --> WaitNext["Wait for Next Chunk"]
    
    CheckPause -- Yes --> SlicePause["✂️ Slice Audio (Flush Entire Buffer)"]
    CheckPause -- No --> CheckTimeout{"Queue Timeout > 180ms?<br/>(User Stopped Speaking)"}
    
    CheckTimeout -- Yes --> SliceTimeout["✂️ Instant Flush on Pause"]
    CheckTimeout -- No --> WaitNext

    SliceCont --> Enqueue["Push Slice to Async Worker Queue"]
    SlicePause --> Enqueue
    SliceTimeout --> Enqueue
    Enqueue --> ResetBuffer["Reset Accumulator"]
    ResetBuffer --> WaitNext
```

---

## 4. Tri-Lingual Language Detection & Output Routing

The decision logic determining which language was spoken and how the translation is targeted:

```mermaid
graph TD
    InputAudio["Spoken Speech Input"] --> AIAnalysis["Gemini Multi-Modal Acoustic & Phoneme Analysis"]
    
    AIAnalysis --> LangDetect{"Detected Input Language"}
    
    LangDetect -->|Sinhala| OutCheck1{"Target Language Selected"}
    LangDetect -->|Tamil| OutCheck2{"Target Language Selected"}
    LangDetect -->|English / Singlish / Tanglish| OutCheck3{"Target Language Selected"}
    
    OutCheck1 -->|Tamil| TransToTamil1["Translate directly to natural Sri Lankan Tamil"]
    OutCheck1 -->|Sinhala| EchoSi["Correct & Polished Sinhala output"]
    
    OutCheck2 -->|Sinhala| TransToSi1["Translate directly to authentic Sri Lankan Sinhala"]
    OutCheck2 -->|Tamil| EchoTa["Correct & Polished Tamil output"]
    
    OutCheck3 -->|Tamil| TransToTamil2["Translate loanwords/English into Tamil"]
    OutCheck3 -->|Sinhala| TransToSi2["Translate loanwords/English into Sinhala"]
    
    TransToTamil1 --> Synthesis["Gemini TTS Synthesis"]
    EchoSi --> Synthesis
    TransToSi1 --> Synthesis
    EchoTa --> Synthesis
    TransToTamil2 --> Synthesis
    TransToSi2 --> Synthesis

    Synthesis --> ClientDelivery["Deliver Audio & Transcripts to User"]
```

---

## 5. AWS EC2 Cloud Deployment Topology

The infrastructure topology currently deployed and serving traffic on AWS:

```mermaid
flowchart LR
    subgraph Internet["🌍 Public Internet"]
        WebUser["📱 Mobile / Desktop Web Browser"]
        DevClient["🐍 Python Client Script<br/>(examples/aws_client_example.py)"]
    end

    subgraph AWSCloud["☁️ AWS Cloud — eu-north-1"]
        subgraph VPC["Virtual Private Cloud (VPC)"]
            subgraph SecurityGroup["🛡️ Security Group (Firewall)"]
                P80["Port 80 (HTTP)"]
                P443["Port 443 (HTTPS)"]
                P8000["Port 8000 (Custom TCP)"]
                P22["Port 22 (SSH)"]
            end

            subgraph EC2Instance["🖥️ EC2 Instance: t3.micro / t3.small"]
                Swap["💾 2GB Swap Memory (Virtual RAM)"]
                
                subgraph DockerCompose["🐳 Docker Compose Environment"]
                    Nginx["🌐 Nginx Proxy Container<br/>(Port 80 / 443)"]
                    Frontend["⚛️ Frontend Container<br/>(React 19 SPA)"]
                    Backend["⚡ FastAPI Backend Container<br/>(Port 8000, Python 3.11)"]
                end
            end
        end
    end

    subgraph GoogleCloud["☁️ Google AI Cloud"]
        GeminiAPI["🤖 Google Gemini API Gateway<br/>• gemini-3.5-flash-lite<br/>• gemini-3.8-flash-lite-tts"]
    end

    %% Traffic routing
    WebUser -->|HTTP / WS| P80
    WebUser -.->|Direct WS| P8000
    DevClient -->|Direct WS| P8000

    P80 --> Nginx
    P8000 --> Backend

    Nginx -->|Proxy /| Frontend
    Nginx -->|Proxy /api and /ws| Backend

    Backend -->|Secure HTTPS / REST| GeminiAPI
```

---

## 6. Summary of Architectural Guarantees

1. **Sub-3-Second Turnaround**: Slicing cadence + `gemini-3.5-flash-lite` + `gemini-3.8-flash-lite-tts` provides near-instant continuous translation without blocking the conversation.
2. **Full Duplex Audio**: User can speak non-stop without pausing; the system ingests audio in the background and speaks translated responses concurrently.
3. **No Disconnect on Language Toggle**: The target language can be switched between Tamil and Sinhala dynamically in real time without tearing down the WebSocket connection.
