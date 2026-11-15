"""CLI entry point for command-line text, MP3/WAV/M4A/OGG audio, and live microphone translation (`st-convert`)."""

import argparse
import os
import subprocess
import sys
import tempfile
import time
import wave
from typing import Optional, Tuple
from sinhala_tamil_converter.converter import SinhalaTamilConverter

AUDIO_EXTENSIONS = (
    ".wav", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".oga",
    ".flac", ".webm", ".mp4", ".3gp", ".3gpp", ".amr", ".wma",
    ".aiff", ".aif", ".aifc", ".caf", ".pcm", ".raw",
)


def _is_audio_file_input(val: str) -> bool:
    cleaned = val.strip().strip('"').strip("'").strip()
    if cleaned.lower().endswith(AUDIO_EXTENSIONS):
        return True
    expanded = os.path.expanduser(cleaned)
    return os.path.isfile(expanded)


def _parse_mic_command(val: str) -> Tuple[bool, Optional[float]]:
    parts = val.strip().split()
    if not parts:
        return False, None
    cmd = parts[0].lower().rstrip(":")
    if cmd in ("mic", "voice", "record", "speak"):
        if len(parts) > 1:
            try:
                return True, float(parts[1])
            except ValueError:
                return False, None
        return True, None
    return False, None


def _record_mic_wav(duration: Optional[float] = None) -> str:
    """Record live voice from the microphone into a temporary 16kHz 16-bit mono WAV file."""
    fd, out_wav = tempfile.mkstemp(prefix="st_mic_", suffix=".wav")
    os.close(fd)

    try:
        import sounddevice as sd  # type: ignore
        secs = duration or 5.0
        print(f"🎤 Recording live voice from microphone for {secs:.1f}s ... Speak now!")
        rec = sd.rec(int(secs * 16000), samplerate=16000, channels=1, dtype="int16")
        sd.wait()
        with wave.open(out_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(rec.tobytes())
        return out_wav
    except ImportError:
        pass

    if sys.platform == "darwin":
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AVFoundation.framework/AVFoundation")
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]

        def msg(obj, sel_name, *args, restype=ctypes.c_void_p, argtypes=None):
            sel = objc.sel_registerName(sel_name.encode("utf-8"))
            fn = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, ctypes.c_void_p, *(argtypes or []))(("objc_msgSend", objc))
            return fn(obj, sel, *args)

        def nsstr(s: str) -> ctypes.c_void_p:
            return msg(objc.objc_getClass(b"NSString"), "stringWithUTF8String:", s.encode("utf-8"), argtypes=[ctypes.c_char_p])

        NSNumber = objc.objc_getClass(b"NSNumber")
        NSMutableDictionary = objc.objc_getClass(b"NSMutableDictionary")
        NSURL = objc.objc_getClass(b"NSURL")
        AVAudioRecorder = objc.objc_getClass(b"AVAudioRecorder")

        settings = msg(NSMutableDictionary, "dictionary")
        for key, val in [
            ("AVFormatIDKey", msg(NSNumber, "numberWithInt:", 1819304813, argtypes=[ctypes.c_int])),
            ("AVSampleRateKey", msg(NSNumber, "numberWithDouble:", 16000.0, argtypes=[ctypes.c_double])),
            ("AVNumberOfChannelsKey", msg(NSNumber, "numberWithInt:", 1, argtypes=[ctypes.c_int])),
            ("AVLinearPCMBitDepthKey", msg(NSNumber, "numberWithInt:", 16, argtypes=[ctypes.c_int])),
            ("AVLinearPCMIsBigEndianKey", msg(NSNumber, "numberWithBool:", False, argtypes=[ctypes.c_bool])),
            ("AVLinearPCMIsFloatKey", msg(NSNumber, "numberWithBool:", False, argtypes=[ctypes.c_bool])),
        ]:
            msg(settings, "setObject:forKey:", val, nsstr(key), argtypes=[ctypes.c_void_p, ctypes.c_void_p])

        url = msg(NSURL, "fileURLWithPath:", nsstr(out_wav), argtypes=[ctypes.c_void_p])
        err = ctypes.c_void_p(0)
        rec_alloc = msg(AVAudioRecorder, "alloc")
        recorder = msg(
            rec_alloc,
            "initWithURL:settings:error:",
            url,
            settings,
            ctypes.byref(err),
            argtypes=[ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
        )
        if not recorder:
            raise RuntimeError("Could not initialize macOS AVAudioRecorder.")
        msg(recorder, "prepareToRecord", restype=ctypes.c_bool)
        if not msg(recorder, "record", restype=ctypes.c_bool):
            raise RuntimeError("Could not start microphone recording. Check Microphone permission.")
        if duration and duration > 0:
            print(f"🎤 Recording live voice from microphone for {duration:.1f}s ... Speak now!")
            time.sleep(duration)
        else:
            try:
                input("🎤 Recording live voice from microphone... Speak now and press [Enter] when finished > ")
            except EOFError:
                time.sleep(4.0)
        msg(recorder, "stop", restype=None)
        return out_wav

    raise RuntimeError("No microphone recorder available. Install 'sounddevice' or pass an audio file (.mp3/.wav).")


def _play_wav(path: str) -> None:
    if not path or not os.path.isfile(path):
        return
    try:
        if sys.platform == "darwin":
            subprocess.run(["afplay", path], check=True)
        elif sys.platform.startswith("linux"):
            subprocess.run(["aplay", "-q", path], check=True)
        elif sys.platform == "win32":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
    except Exception as exc:
        sys.stderr.write(f"Warning: could not play audio: {exc}\n")


def _process_single(
    converter: SinhalaTamilConverter,
    text_or_path: Optional[str],
    audio_path: Optional[str],
    source: str,
    target: Optional[str],
    temperature: float,
    voice: str,
    output_wav: Optional[str],
    play: bool,
) -> None:
    # Determine if input is an audio file path
    resolved_audio = audio_path
    if not resolved_audio and text_or_path and _is_audio_file_input(text_or_path):
        resolved_audio = text_or_path

    if resolved_audio:
        out_file = output_wav or "output.wav"
        result = converter.translate_audio(
            resolved_audio,
            source=source,
            target=target,
            voice=voice,
            output_wav=out_file,
        )
        print(f"Transcribed Text ({result.source_language.value}): {result.transcription}")
        print(f"Translated Text  ({result.target_language.value}): {result.text}")
        if result.audio_path:
            print(f"Translated Voice : {result.audio_path}")
            if play:
                _play_wav(result.audio_path)
    else:
        if not text_or_path:
            raise ValueError("Please provide text or a .wav file path.")
        result = converter.translate(
            text_or_path,
            source=source,
            target=target,
            temperature=temperature,
        )
        print(result.text)
        if output_wav or play:
            out_file = output_wav or "output.wav"
            if hasattr(converter.backend, "synthesize_speech"):
                audio_bytes = converter.backend.synthesize_speech(
                    result.text, voice=voice, output_wav=out_file
                )
                if audio_bytes:
                    print(f"Translated Voice : {out_file}")
                    if play:
                        _play_wav(out_file)


def main() -> None:
    """Run CLI argument parser and translation execution."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="st-convert",
        description="Convert / Translate text, audio files (.mp3, .wav, .m4a, .ogg, .flac), or live microphone voice between Sinhala and Tamil",
    )
    parser.add_argument(
        "text",
        nargs="?",
        default=None,
        type=str,
        help="Text to translate, 'mic', OR path to an audio file (.mp3, .wav, .m4a, .ogg, .flac, .pcm)",
    )
    parser.add_argument(
        "--audio",
        "--wav",
        "--mp3",
        dest="audio",
        type=str,
        default=None,
        help="Path to an audio file (.mp3, .wav, .m4a, .aac, .ogg, .flac, .pcm) to transcribe, translate, and synthesize voice output",
    )
    parser.add_argument(
        "--mic",
        "--voice-input",
        dest="mic",
        action="store_true",
        help="Record live normal voice from the microphone and translate it",
    )
    parser.add_argument(
        "--record-seconds",
        "--duration",
        dest="record_seconds",
        type=float,
        default=None,
        help="Seconds to record from microphone when using --mic (omit to press Enter when done)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output WAV file path for translated voice (defaults to output.wav for audio input)",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="Aoede",
        choices=["Aoede", "Charon", "Kore", "Puck", "Fenrir"],
        help="TTS voice for translated audio output (default: Aoede)",
    )
    parser.add_argument(
        "--play",
        action="store_true",
        help="Play the translated voice WAV file through speakers",
    )
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Start an interactive terminal prompt accepting text, 'mic', or audio file paths (.mp3/.wav/.m4a)",
    )
    parser.add_argument(
        "--source",
        "-s",
        type=str,
        default="auto",
        choices=["sinhala", "tamil", "auto"],
        help="Source language (default: auto)",
    )
    parser.add_argument(
        "--target",
        "-t",
        type=str,
        default=None,
        choices=["sinhala", "tamil"],
        help="Target language (defaults to opposite of source)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Model temperature (default: 0.2)",
    )

    args = parser.parse_args()
    try:
        converter = SinhalaTamilConverter()
        if args.mic:
            rec_file = _record_mic_wav(args.record_seconds)
            _process_single(
                converter=converter,
                text_or_path=None,
                audio_path=rec_file,
                source=args.source,
                target=args.target,
                temperature=args.temperature,
                voice=args.voice,
                output_wav=args.output or "output.wav",
                play=args.play,
            )
            return

        if args.text and not args.audio:
            is_mic, mic_secs = _parse_mic_command(args.text)
            if is_mic:
                rec_file = _record_mic_wav(mic_secs if mic_secs is not None else args.record_seconds)
                _process_single(
                    converter=converter,
                    text_or_path=None,
                    audio_path=rec_file,
                    source=args.source,
                    target=args.target,
                    temperature=args.temperature,
                    voice=args.voice,
                    output_wav=args.output or "output.wav",
                    play=args.play,
                )
                return

        if args.interactive or (args.text is None and args.audio is None):
            print("SinTam Interactive Terminal (enter text, 'mic', or an audio file path [.mp3/.wav/.m4a]; 'exit' to quit)")
            while True:
                try:
                    user_in = input("Input (text, 'mic', or .mp3/.wav path) > ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not user_in:
                    continue
                if user_in.lower() in ("exit", "quit"):
                    break
                try:
                    is_mic, mic_secs = _parse_mic_command(user_in)
                    if is_mic:
                        rec_file = _record_mic_wav(mic_secs if mic_secs is not None else args.record_seconds)
                        _process_single(
                            converter=converter,
                            text_or_path=None,
                            audio_path=rec_file,
                            source=args.source,
                            target=args.target,
                            temperature=args.temperature,
                            voice=args.voice,
                            output_wav=args.output or "output.wav",
                            play=args.play,
                        )
                    else:
                        _process_single(
                            converter=converter,
                            text_or_path=user_in,
                            audio_path=None,
                            source=args.source,
                            target=args.target,
                            temperature=args.temperature,
                            voice=args.voice,
                            output_wav=args.output or "output.wav",
                            play=args.play,
                        )
                except Exception as item_err:
                    sys.stderr.write(f"Error: {item_err}\n")
            return

        _process_single(
            converter=converter,
            text_or_path=args.text,
            audio_path=args.audio,
            source=args.source,
            target=args.target,
            temperature=args.temperature,
            voice=args.voice,
            output_wav=args.output,
            play=args.play,
        )
    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
