#!/usr/bin/env python3
"""
scripts/generate_demo_video.py
-----------------------------------
Automated high-definition video generator for SinTam AI.
Produces a ready-to-publish MP4 demo video showcasing:
1. Product Introduction & Problem Statement
2. Universal 1-line CLI installation and startup (`sintam`)
3. Live Speech-to-Speech translation (Sinhala <-> Tamil)
4. AI Architecture (Gemini 2.0 Live WebSocket, WebRTC Noise Gate, Persona)
5. Call to Action & GitHub Links for LinkedIn and social media.
"""

import os
import sys
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

# Video configuration
WIDTH = 1280
HEIGHT = 720
FPS = 30
TOTAL_SECONDS = 42
TOTAL_FRAMES = FPS * TOTAL_SECONDS

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "sintam_demo_showcase.mp4")

# Font configuration (Windows system fonts)
FONT_BOLD = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 36)
FONT_LARGE = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 46)
FONT_SUB = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 24)
FONT_TEXT = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 20)
FONT_SMALL = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 16)
FONT_CODE = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 20)
FONT_CODE_BOLD = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf" if os.path.exists("C:/Windows/Fonts/consolab.ttf") else "C:/Windows/Fonts/consola.ttf", 22)
FONT_INDIC = ImageFont.truetype("C:/Windows/Fonts/Nirmala.ttc", 26)
FONT_INDIC_LARGE = ImageFont.truetype("C:/Windows/Fonts/Nirmala.ttc", 32)

# Colors (RGB)
BG_COLOR = (11, 15, 25)
CARD_BG = (22, 30, 46)
CARD_BORDER = (45, 60, 85)
CYAN = (34, 211, 238)
INDIGO = (99, 102, 241)
PURPLE = (168, 85, 247)
GREEN = (52, 211, 153)
YELLOW = (251, 191, 36)
RED = (248, 113, 113)
WHITE = (248, 250, 252)
GRAY = (148, 163, 184)
DARK_GRAY = (71, 85, 105)

def draw_header_badge(draw, text, x, y, bg_col, text_col, font=FONT_SMALL):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + 16
    h = bbox[3] - bbox[1] + 10
    draw.rounded_rectangle([x, y, x + w, y + h], radius=6, fill=bg_col)
    draw.text((x + 8, y + 4), text, font=font, fill=text_col)
    return x + w + 10

def draw_ambient_background(draw, frame_idx):
    # Radial glowing light top-left & bottom-right
    t = frame_idx / 30.0
    cx1 = int(250 + 60 * math.sin(t * 0.8))
    cy1 = int(180 + 40 * math.cos(t * 0.7))
    cx2 = int(1050 + 50 * math.cos(t * 0.9))
    cy2 = int(550 + 40 * math.sin(t * 0.6))
    
    # Subtle grid lines
    grid_spacing = 60
    for gx in range(0, WIDTH, grid_spacing):
        draw.line([(gx, 0), (gx, HEIGHT)], fill=(18, 24, 38), width=1)
    for gy in range(0, HEIGHT, grid_spacing):
        draw.line([(0, gy), (WIDTH, gy)], fill=(18, 24, 38), width=1)

def draw_progress_bar(draw, frame_idx):
    # Sleek bottom progress bar
    progress = frame_idx / TOTAL_FRAMES
    bar_width = int(WIDTH * progress)
    draw.rectangle([0, HEIGHT - 6, WIDTH, HEIGHT], fill=(20, 25, 35))
    draw.rectangle([0, HEIGHT - 6, bar_width, HEIGHT], fill=CYAN)

def draw_scene_1(draw, frame_idx, local_frame):
    # 0s - 7s (frames 0 - 210) : Title & Hook
    t = local_frame / 30.0
    fade = min(1.0, local_frame / 20.0)
    
    # Glowing title banner
    draw_ambient_background(draw, frame_idx)
    
    # Badges
    bx = 360
    bx = draw_header_badge(draw, "AI VOICE TRANSLATOR", bx, 110, (30, 41, 59), CYAN, FONT_SMALL)
    bx = draw_header_badge(draw, "GEMINI 2.0 LIVE", bx, 110, (30, 41, 59), PURPLE, FONT_SMALL)
    draw_header_badge(draw, "SUB-SECOND LATENCY", bx, 110, (30, 41, 59), GREEN, FONT_SMALL)
    
    # Main Title
    draw.text((WIDTH // 2, 195), "SinTam AI Voice Engine", font=FONT_LARGE, fill=WHITE, anchor="mm")
    
    # Subtitle with gradient feel
    draw.text((WIDTH // 2, 250), "Real-Time Bidirectional Sinhala <-> Tamil Speech Translation", font=FONT_SUB, fill=CYAN, anchor="mm")
    
    # Glassmorphism Card
    cx, cy, cw, ch = 200, 310, 880, 270
    draw.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=2)
    
    # Left pill: Sinhala
    draw.rounded_rectangle([cx + 40, cy + 40, cx + 380, cy + 220], radius=12, fill=(28, 38, 58), outline=(60, 80, 115), width=2)
    draw.text((cx + 65, cy + 65), "සිංහල (Sinhala)", font=FONT_INDIC_LARGE, fill=WHITE)
    draw.text((cx + 65, cy + 120), "Natural voice speech input", font=FONT_TEXT, fill=GRAY)
    draw.text((cx + 65, cy + 150), "Built for Sri Lankan call centers", font=FONT_TEXT, fill=GREEN)
    
    # Arrow icon
    draw.text((WIDTH // 2, cy + 130), "⇄", font=FONT_LARGE, fill=CYAN, anchor="mm")
    
    # Right pill: Tamil
    draw.rounded_rectangle([cx + 500, cy + 40, cx + 840, cy + 220], radius=12, fill=(28, 38, 58), outline=(60, 80, 115), width=2)
    draw.text((cx + 525, cy + 65), "தமிழ் (Tamil)", font=FONT_INDIC_LARGE, fill=WHITE)
    draw.text((cx + 525, cy + 120), "Instant speech-to-speech audio", font=FONT_TEXT, fill=GRAY)
    draw.text((cx + 525, cy + 150), "Colloquial & Tanglish aware", font=FONT_TEXT, fill=CYAN)
    
    # Bottom tag
    draw.text((WIDTH // 2, 630), "Empowering Seamless Bilingual Communication Across Sri Lanka", font=FONT_SUB, fill=WHITE, anchor="mm")

def draw_scene_2(draw, frame_idx, local_frame):
    # 7s - 16s (frames 210 - 480) : The 1-Line Universal CLI
    t = local_frame / 30.0
    draw_ambient_background(draw, frame_idx)
    
    # Section Header
    draw.text((WIDTH // 2, 65), "Zero-Friction 1-Line Deployment", font=FONT_LARGE, fill=WHITE, anchor="mm")
    draw.text((WIDTH // 2, 105), "Run anywhere with Python - No Docker lag, No Node.js required at runtime", font=FONT_SUB, fill=CYAN, anchor="mm")
    
    # Terminal Window Container
    tx, ty, tw, th = 160, 140, 960, 500
    draw.rounded_rectangle([tx, ty, tx + tw, ty + th], radius=14, fill=(15, 20, 32), outline=CARD_BORDER, width=2)
    
    # Terminal Title Bar
    draw.rounded_rectangle([tx, ty, tx + tw, ty + 42], radius=14, fill=(24, 32, 48))
    draw.rectangle([tx, ty + 25, tx + tw, ty + 42], fill=(24, 32, 48)) # square bottom corners
    draw.line([(tx, ty + 42), (tx + tw, ty + 42)], fill=CARD_BORDER, width=1)
    
    # Window buttons
    draw.ellipse([tx + 18, ty + 14, tx + 32, ty + 28], fill=RED)
    draw.ellipse([tx + 40, ty + 14, tx + 54, ty + 28], fill=YELLOW)
    draw.ellipse([tx + 62, ty + 14, tx + 76, ty + 28], fill=GREEN)
    draw.text((tx + tw // 2, ty + 20), "bash ~ sintam-cli (Universal Runner)", font=FONT_SMALL, fill=GRAY, anchor="mm")
    
    # Terminal Content Simulation based on timing
    line_y = ty + 65
    
    # Step 1: pip install
    cmd1 = "pip install git+https://github.com/UVSHUB/Tamil-and-Sinhala-Converter.git"
    chars_to_show = int(min(len(cmd1), (t * 22)))
    typed_cmd1 = cmd1[:chars_to_show]
    cursor = "_" if (int(t * 4) % 2 == 0) and (t < 3.5) else ""
    
    draw.text((tx + 25, line_y), "$ " + typed_cmd1 + cursor, font=FONT_CODE, fill=WHITE)
    line_y += 35
    
    if t >= 3.2:
        draw.text((tx + 25, line_y), "Fetching package from GitHub... [OK]", font=FONT_CODE, fill=GRAY)
        line_y += 30
        draw.text((tx + 25, line_y), "Successfully installed sintam-1.0.0 (backend + bundled UI)", font=FONT_CODE, fill=GREEN)
        line_y += 45
        
    # Step 2: running sintam
    if t >= 4.5:
        cmd2 = "sintam"
        t2 = t - 4.5
        chars2 = int(min(len(cmd2), (t2 * 15)))
        cursor2 = "_" if (int(t * 4) % 2 == 0) and (t < 6.0) else ""
        draw.text((tx + 25, line_y), "$ " + cmd2[:chars2] + cursor2, font=FONT_CODE_BOLD, fill=CYAN)
        line_y += 38
        
    if t >= 5.8:
        # Beautiful ASCII / Banner output
        draw.text((tx + 25, line_y), "==========================================", font=FONT_CODE, fill=CYAN)
        line_y += 26
        draw.text((tx + 25, line_y), "   SinTam Voice Translator Launcher", font=FONT_CODE_BOLD, fill=WHITE)
        line_y += 26
        draw.text((tx + 25, line_y), "==========================================", font=FONT_CODE, fill=CYAN)
        line_y += 34
        draw.text((tx + 25, line_y), "[✓] React UI Static Assets Mounted", font=FONT_CODE, fill=GREEN)
        line_y += 28
        draw.text((tx + 25, line_y), "[✓] FastAPI WebSocket Handlers Active", font=FONT_CODE, fill=GREEN)
        line_y += 28
        draw.text((tx + 25, line_y), "Starting server at http://127.0.0.1:8000 (Auto-opening browser)", font=FONT_CODE_BOLD, fill=YELLOW)

def draw_scene_3(draw, frame_idx, local_frame):
    # 16s - 26s (frames 480 - 780) : Live Voice Translation Demo
    t = local_frame / 30.0
    draw_ambient_background(draw, frame_idx)
    
    # Header
    draw.text((WIDTH // 2, 55), "Live Interactive Voice Translation", font=FONT_LARGE, fill=WHITE, anchor="mm")
    draw.text((WIDTH // 2, 92), "Real-time speech streaming with WebRTC Noise Gating & Call Center Persona", font=FONT_SUB, fill=CYAN, anchor="mm")
    
    # Main App Window
    wx, wy, ww, wh = 140, 120, 1000, 540
    draw.rounded_rectangle([wx, wy, wx + ww, wy + wh], radius=14, fill=(18, 25, 40), outline=CARD_BORDER, width=2)
    
    # App Bar
    draw.rounded_rectangle([wx, wy, wx + ww, wy + 48], radius=14, fill=(26, 36, 56))
    draw.rectangle([wx, wy + 30, wx + ww, wy + 48], fill=(26, 36, 56))
    draw.text((wx + 30, wy + 24), "SinTam Translator", font=FONT_BOLD, fill=WHITE, anchor="lm")
    draw_header_badge(draw, "ONLINE: 8000", wx + ww - 140, wy + 13, (16, 185, 129), (0, 0, 0), FONT_SMALL)
    
    # Mode selector pill
    draw.rounded_rectangle([wx + 340, wy + 10, wx + 660, wy + 40], radius=8, fill=(35, 48, 75))
    draw.text((wx + 500, wy + 25), "Mode: Sinhala -> Tamil (Call Center)", font=FONT_TEXT, fill=CYAN, anchor="mm")
    
    # Left Box: Customer Speaking (Sinhala)
    bx1, by1, bw, bh = wx + 40, wy + 70, 440, 360
    draw.rounded_rectangle([bx1, by1, bx1 + bw, by1 + bh], radius=12, fill=(24, 33, 52), outline=(48, 65, 98), width=2)
    
    # Speaker header
    draw.text((bx1 + 25, by1 + 35), "Sinhala Speaker (Customer)", font=FONT_SUB, fill=WHITE)
    draw_header_badge(draw, "MIC ACTIVE", bx1 + bw - 120, by1 + 22, (239, 68, 68), WHITE, FONT_SMALL)
    
    # Animated Audio Waveform for voice
    wave_y = by1 + 100
    for i in range(26):
        bar_x = bx1 + 35 + i * 14
        # Dynamic sine bounce
        freq = 0.5 + i * 0.2
        bar_h = int(12 + 35 * abs(math.sin(t * 4.5 + freq)))
        draw.rounded_rectangle([bar_x, wave_y - bar_h // 2, bar_x + 8, wave_y + bar_h // 2], radius=4, fill=CYAN)
        
    # Sinhala Speech Transcription
    speech_sin = "මට මේ බිල්පත ගැන විස්තර දැනගන්න පුළුවන්ද?"
    draw.text((bx1 + 25, by1 + 160), "Spoken Audio Transcribed:", font=FONT_TEXT, fill=GRAY)
    draw.text((bx1 + 25, by1 + 195), speech_sin, font=FONT_INDIC_LARGE, fill=WHITE)
    draw.text((bx1 + 25, by1 + 250), "\"Could I get details about this bill?\"", font=FONT_TEXT, fill=(180, 200, 230))
    
    # Filter status
    draw.rounded_rectangle([bx1 + 25, by1 + 295, bx1 + bw - 25, by1 + 335], radius=6, fill=(16, 30, 45))
    draw.text((bx1 + 40, by1 + 315), "✓ Noise Gate: Filtered background call chatter", font=FONT_SMALL, fill=GREEN, anchor="lm")
    
    # Center Arrow & Processing
    draw.text((wx + ww // 2, wy + 240), "➔", font=FONT_LARGE, fill=CYAN, anchor="mm")
    draw.text((wx + ww // 2, wy + 275), "320ms", font=FONT_CODE_BOLD, fill=GREEN, anchor="mm")
    
    # Right Box: Translated Audio & Text (Tamil)
    bx2 = wx + ww - 480
    draw.rounded_rectangle([bx2, by1, bx2 + bw, by1 + bh], radius=12, fill=(24, 33, 52), outline=(48, 65, 98), width=2)
    
    draw.text((bx2 + 25, by1 + 35), "Tamil Output (Agent / Audio)", font=FONT_SUB, fill=WHITE)
    draw_header_badge(draw, "SPEAKING", bx2 + bw - 110, by1 + 22, (34, 197, 94), (0, 0, 0), FONT_SMALL)
    
    # Output waveform
    wave_y2 = by1 + 100
    for i in range(26):
        bar_x = bx2 + 35 + i * 14
        bar_h = int(10 + 38 * abs(math.cos(t * 4.0 + i * 0.25)))
        draw.rounded_rectangle([bar_x, wave_y2 - bar_h // 2, bar_x + 8, wave_y2 + bar_h // 2], radius=4, fill=GREEN)
        
    # Tamil Output
    speech_tam = "இந்த பில் பற்றிய விவரங்களை\nநான் தெரிந்து கொள்ளலாமா?"
    draw.text((bx2 + 25, by1 + 160), "Real-Time Translated Speech:", font=FONT_TEXT, fill=GRAY)
    draw.text((bx2 + 25, by1 + 195), speech_tam, font=FONT_INDIC_LARGE, fill=GREEN)
    
    # Persona badge
    draw.rounded_rectangle([bx2 + 25, by1 + 295, bx2 + bw - 25, by1 + 335], radius=6, fill=(20, 35, 30))
    draw.text((bx2 + 40, by1 + 315), "✓ Call-Center Persona Applied (Natural Tone)", font=FONT_SMALL, fill=CYAN, anchor="lm")
    
    # Bottom Bar Metrics
    draw.text((wx + 50, wy + wh - 40), "Bi-directional WebSocket streaming • Auto Voice-Activity-Detection (VAD) • High Fidelity TTS", font=FONT_TEXT, fill=GRAY)

def draw_scene_4(draw, frame_idx, local_frame):
    # 26s - 34s (frames 780 - 1020) : Architecture & Under-the-hood features
    t = local_frame / 30.0
    draw_ambient_background(draw, frame_idx)
    
    draw.text((WIDTH // 2, 65), "Under The Hood: Enterprise Architecture", font=FONT_LARGE, fill=WHITE, anchor="mm")
    draw.text((WIDTH // 2, 105), "Engineered specifically for high-noise Sri Lankan customer service operations", font=FONT_SUB, fill=CYAN, anchor="mm")
    
    cards = [
        ("1. Sri Lankan AI Persona", 
         "Fine-Tuned System Prompt",
         "Understands native colloquial phrasing,",
         "effortlessly interprets Singlish & Tanglish,",
         "and preserves polite call-center context.",
         PURPLE),
        ("2. WebRTC Noise Gate", 
         "Acoustic Noise Isolation",
         "Configured with strict RMS threshold (0.025)",
         "to eliminate office keyboard clatter, side",
         "conversations, and background echoes.",
         CYAN),
        ("3. Universal CLI", 
         "FastAPI + React Bundling",
         "Single-command pip installable package.",
         "Direct memory streaming via WebSockets",
         "bypassing containerization latency.",
         GREEN)
    ]
    
    card_w = 340
    card_h = 380
    gap = 40
    start_x = (WIDTH - (3 * card_w + 2 * gap)) // 2
    card_y = 150
    
    for idx, (title, sub, l1, l2, l3, accent) in enumerate(cards):
        cx = start_x + idx * (card_w + gap)
        # Subtle hover bounce
        offset_y = int(4 * math.sin(t * 3.0 + idx))
        cy = card_y + offset_y
        
        draw.rounded_rectangle([cx, cy, cx + card_w, cy + card_h], radius=14, fill=CARD_BG, outline=CARD_BORDER, width=2)
        # Top accent line
        draw.rounded_rectangle([cx, cy, cx + card_w, cy + 8], radius=4, fill=accent)
        
        draw.text((cx + 25, cy + 35), title, font=FONT_BOLD, fill=WHITE)
        draw.text((cx + 25, cy + 75), sub, font=FONT_TEXT, fill=accent)
        
        draw.line([(cx + 25, cy + 115), (cx + card_w - 25, cy + 115)], fill=(45, 60, 85), width=1)
        
        draw.text((cx + 25, cy + 145), l1, font=FONT_TEXT, fill=GRAY)
        draw.text((cx + 25, cy + 180), l2, font=FONT_TEXT, fill=GRAY)
        draw.text((cx + 25, cy + 215), l3, font=FONT_TEXT, fill=GRAY)
        
        # Bottom badge
        draw.rounded_rectangle([cx + 25, cy + 295, cx + card_w - 25, cy + 345], radius=8, fill=(28, 38, 58))
        draw.text((cx + card_w // 2, cy + 320), "Enterprise Ready", font=FONT_TEXT, fill=WHITE, anchor="mm")
        
    draw.text((WIDTH // 2, 600), "FastAPI • Google Gemini 2.0 • WebRTC • WebSockets • React Vite", font=FONT_SUB, fill=GRAY, anchor="mm")

def draw_scene_5(draw, frame_idx, local_frame):
    # 34s - 42s (frames 1020 - 1260) : Outro & Call To Action (LinkedIn showcase)
    t = local_frame / 30.0
    draw_ambient_background(draw, frame_idx)
    
    # Large glowing badge
    draw_header_badge(draw, "OPEN SOURCE & ENTERPRISE READY", WIDTH // 2 - 160, 80, (30, 41, 59), CYAN, FONT_TEXT)
    
    draw.text((WIDTH // 2, 175), "SinTam: Voice AI for Sri Lanka", font=FONT_LARGE, fill=WHITE, anchor="mm")
    draw.text((WIDTH // 2, 230), "Connect Sinhala & Tamil Speakers with Instant Voice Intelligence", font=FONT_SUB, fill=CYAN, anchor="mm")
    
    # CTA Big Card
    cx, cy, cw, ch = 240, 280, 800, 240
    draw.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=16, fill=CARD_BG, outline=CARD_BORDER, width=2)
    
    draw.text((cx + 50, cy + 50), "Get Started in 60 Seconds:", font=FONT_SUB, fill=WHITE)
    
    # Command Box
    draw.rounded_rectangle([cx + 50, cy + 90, cx + cw - 50, cy + 160], radius=10, fill=(15, 20, 32), outline=(60, 80, 115), width=2)
    draw.text((cx + 75, cy + 125), "pip install git+https://github.com/UVSHUB/Tamil-and-Sinhala-Converter.git", font=FONT_CODE_BOLD, fill=GREEN, anchor="lm")
    
    # Link
    draw.text((cx + 50, cy + 195), "⭐ GitHub: UVSHUB/Tamil-and-Sinhala-Converter", font=FONT_BOLD, fill=YELLOW)
    
    # Footer
    draw.text((WIDTH // 2, 590), "Share, Star & Contribute on GitHub!", font=FONT_SUB, fill=WHITE, anchor="mm")
    draw.text((WIDTH // 2, 635), "Follow for more AI Innovations in Natural Language & Voice", font=FONT_TEXT, fill=GRAY, anchor="mm")

def main():
    print(f"Generating SinTam HD Demo Video ({WIDTH}x{HEIGHT} @ {FPS}fps, {TOTAL_SECONDS}s)...")
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(OUTPUT_PATH, fourcc, float(FPS), (WIDTH, HEIGHT))
    
    if not out.isOpened():
        print(f"Error: OpenCV could not open VideoWriter for {OUTPUT_PATH}")
        sys.exit(1)
        
    for frame_idx in range(TOTAL_FRAMES):
        # Create base PIL canvas
        img = Image.new("RGB", (WIDTH, HEIGHT), color=BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        # Determine scene
        # 0s - 7s: Scene 1 (frames 0 - 210)
        # 7s - 16s: Scene 2 (frames 210 - 480)
        # 16s - 26s: Scene 3 (frames 480 - 780)
        # 26s - 34s: Scene 4 (frames 780 - 1020)
        # 34s - 42s: Scene 5 (frames 1020 - 1260)
        
        if frame_idx < 210:
            draw_scene_1(draw, frame_idx, frame_idx)
        elif frame_idx < 480:
            draw_scene_2(draw, frame_idx, frame_idx - 210)
        elif frame_idx < 780:
            draw_scene_3(draw, frame_idx, frame_idx - 480)
        elif frame_idx < 1020:
            draw_scene_4(draw, frame_idx, frame_idx - 780)
        else:
            draw_scene_5(draw, frame_idx, frame_idx - 1020)
            
        # Draw continuous progress bar
        draw_progress_bar(draw, frame_idx)
        
        # Convert PIL Image to OpenCV BGR numpy array
        frame_bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        out.write(frame_bgr)
        
        if frame_idx % 150 == 0 or frame_idx == TOTAL_FRAMES - 1:
            pct = int((frame_idx + 1) / TOTAL_FRAMES * 100)
            print(f"Rendering progress: {pct}% ({frame_idx + 1}/{TOTAL_FRAMES} frames)")
            
    out.release()
    print(f"\n[SUCCESS] Video created successfully at:\n{OUTPUT_PATH}")
    print(f"File size: {os.path.getsize(OUTPUT_PATH) / (1024 * 1024):.2f} MB")

if __name__ == "__main__":
    main()
