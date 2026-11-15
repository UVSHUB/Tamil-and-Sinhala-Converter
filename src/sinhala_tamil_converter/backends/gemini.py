"""Google Gemini Live / GenAI Translation Backend."""

import io
import json
import os
import wave
from typing import Optional
from google import genai
from google.genai import types

from sinhala_tamil_converter.backends.base import BaseTranslationBackend
from sinhala_tamil_converter.exceptions import InvalidInputError, TranslationAPIError
from sinhala_tamil_converter.models import Language, TranslationResult


AUDIO_MIME_BY_EXT = {
    ".wav": "audio/wav",
    ".mp3": "audio/mp3",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
    ".3gp": "audio/3gpp",
    ".3gpp": "audio/3gpp",
    ".amr": "audio/amr",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".aifc": "audio/aiff",
}


def _ensure_wav_bytes(raw_bytes: bytes) -> bytes:
    """Wrap raw 16kHz 16-bit mono PCM into a WAV container if not already RIFF WAV."""
    if raw_bytes[:4] == b"RIFF":
        return raw_bytes
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(raw_bytes)
    return buf.getvalue()


def _prepare_audio_payload(raw_bytes: bytes, path: str) -> tuple[bytes, str]:
    """Return (audio_bytes, mime_type) for WAV, MP3, M4A, OGG, FLAC, AAC, WEBM, or raw PCM."""
    ext = os.path.splitext(path.lower())[1]
    if ext in (".pcm", ".raw") and raw_bytes[:4] != b"RIFF":
        return _ensure_wav_bytes(raw_bytes), "audio/wav"
    if ext in AUDIO_MIME_BY_EXT:
        return raw_bytes, AUDIO_MIME_BY_EXT[ext]
    if raw_bytes[:4] == b"RIFF":
        return raw_bytes, "audio/wav"
    if raw_bytes[:3] == b"ID3" or (len(raw_bytes) >= 2 and raw_bytes[0] == 0xFF and (raw_bytes[1] & 0xE0) == 0xE0):
        return raw_bytes, "audio/mp3"
    if raw_bytes[:4] == b"OggS":
        return raw_bytes, "audio/ogg"
    if raw_bytes[:4] == b"fLaC":
        return raw_bytes, "audio/flac"
    if len(raw_bytes) >= 8 and raw_bytes[4:8] == b"ftyp":
        return raw_bytes, "audio/mp4"
    return _ensure_wav_bytes(raw_bytes), "audio/wav"


def _save_pcm_or_wav(audio_data: bytes, output_path: str, sample_rate: int = 24000) -> str:
    """Save raw 24kHz 16-bit mono PCM (or RIFF WAV bytes) as a standard WAV file."""
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    if audio_data[:4] == b"RIFF":
        with open(output_path, "wb") as f:
            f.write(audio_data)
    else:
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
    return output_path


class GeminiTranslationBackend(BaseTranslationBackend):
    """Translation engine powered by Google GenAI."""

    DEFAULT_MODEL = "gemini-3.5-flash-lite"
    DEFAULT_TTS_MODEL = "gemini-3.8-flash-lite-tts"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """Initialize the Gemini backend.

        Args:
            api_key: Optional Gemini API key. If not provided, it will be lazily loaded from
                     the `GEMINI_API_KEY` environment variable when translation is requested.
            model: Gemini model identifier (defaults to 'gemini-3.5-flash-lite').
        """
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        """Lazily initialize and return the Google GenAI client."""
        if self._client is None:
            resolved_key = self.api_key or os.environ.get("GEMINI_API_KEY")
            if not resolved_key:
                try:
                    from dotenv import load_dotenv
                    load_dotenv()
                    resolved_key = os.environ.get("GEMINI_API_KEY")
                except ImportError:
                    pass
            if not resolved_key and os.path.isfile(".env"):
                with open(".env", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY="):
                            resolved_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break

            if not resolved_key:
                raise TranslationAPIError(
                    "Gemini API Key not found. Provide `api_key` or set the `GEMINI_API_KEY` environment variable."
                )
            self._client = genai.Client(
                api_key=resolved_key,
                http_options=types.HttpOptions(
                    base_url="https://generativelanguage.googleapis.com",
                    api_version="v1beta",
                ),
            )
        return self._client

    def _build_prompt(self, text: str, source_lang: Language, target_lang: Language) -> str:
        return (
            f"You are a native professional translator between Sinhala and Tamil.\n"
            f"Translate the following {source_lang.value.title()} text into accurate, natural {target_lang.value.title()}.\n"
            f"Only return the raw translated text. Do not include notes, explanations, or transliteration brackets.\n\n"
            f"Input Text:\n{text}"
        )

    def synthesize_speech(
        self,
        text: str,
        voice: str = "Aoede",
        output_wav: Optional[str] = None,
    ) -> bytes:
        """Synthesize spoken audio (24kHz PCM) for translated text and optionally save to WAV."""
        if not text or not text.strip():
            return b""
        client = self._get_client()
        tts_models = [
            self.DEFAULT_TTS_MODEL,
            "gemini-3.1-flash-tts-preview",
            "gemini-3.8-flash-tts",
            "gemini-2.5-flash-preview-tts",
        ]
        audio_bytes = b""
        for tts_model in tts_models:
            try:
                tts_res = client.models.generate_content(
                    model=tts_model,
                    contents=text,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                            )
                        ),
                    ),
                )
                if tts_res.candidates and tts_res.candidates[0].content:
                    for p in tts_res.candidates[0].content.parts:
                        if p.inline_data and p.inline_data.data:
                            audio_bytes = p.inline_data.data
                            break
                if audio_bytes:
                    break
            except Exception:
                continue

        if audio_bytes and output_wav:
            _save_pcm_or_wav(audio_bytes, output_wav)
        return audio_bytes

    def translate_audio(
        self,
        audio_path: str,
        source_lang: Optional[Language] = None,
        target_lang: Optional[Language] = None,
        voice: str = "Aoede",
        output_wav: Optional[str] = "output.wav",
    ) -> TranslationResult:
        """Transcribe and translate an audio file (.mp3, .wav, .m4a, .ogg, .flac, .aac, .pcm, etc.) and synthesize translated speech."""
        cleaned_path = os.path.expanduser(audio_path.strip().strip('"').strip("'"))
        if not os.path.isfile(cleaned_path):
            raise InvalidInputError(f"Audio file not found: {audio_path}")

        with open(cleaned_path, "rb") as f:
            raw_bytes = f.read()
        if not raw_bytes:
            raise InvalidInputError(f"Audio file is empty: {audio_path}")

        audio_payload, mime_type = _prepare_audio_payload(raw_bytes, cleaned_path)
        target_str = target_lang.value.title() if target_lang in (Language.SINHALA, Language.TAMIL) else "opposite language (Tamil if Sinhala, Sinhala if Tamil)"
        source_hint = (
            f"The speaker is speaking {source_lang.value.title()}."
            if source_lang in (Language.SINHALA, Language.TAMIL)
            else "Detect whether the speaker spoke Sinhala or Tamil."
        )
        prompt = (
            "You are an expert Sinhala <-> Tamil voice translator in Sri Lanka.\n"
            f"1. {source_hint}\n"
            "2. Transcribe the spoken audio verbatim.\n"
            f"3. Translate the speech accurately and naturally into {target_str}.\n"
            "Respond ONLY with valid JSON with keys:\n"
            '{"detected_language": "sinhala"|"tamil", "target_language": "tamil"|"sinhala", "transcription": "...", "translation": "..."}'
        )

        client = self._get_client()
        candidate_models = [
            self.model,
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite-preview",
            "gemini-3.8-flash",
            "gemini-2.0-flash",
            "gemini-flash-latest",
        ]
        res_data = None
        last_err = None
        for m in candidate_models:
            try:
                res = client.models.generate_content(
                    model=m,
                    contents=[
                        types.Part.from_bytes(data=audio_payload, mime_type=mime_type),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                txt = (res.text or "").strip()
                if txt:
                    res_data = json.loads(txt)
                    break
            except Exception as exc:
                last_err = exc
                continue

        if not res_data:
            raise TranslationAPIError(f"Audio transcription/translation failed: {last_err}")

        det_str = (res_data.get("detected_language") or "sinhala").lower()
        detected = Language.TAMIL if "tamil" in det_str else Language.SINHALA
        resolved_target = target_lang if target_lang in (Language.SINHALA, Language.TAMIL) else (
            Language.TAMIL if detected == Language.SINHALA else Language.SINHALA
        )
        transcription = (res_data.get("transcription") or "").strip()
        translation = (res_data.get("translation") or "").strip()

        audio_bytes = self.synthesize_speech(translation, voice=voice, output_wav=output_wav)
        saved_path = output_wav if (audio_bytes and output_wav) else None

        return TranslationResult(
            text=translation,
            source_language=detected,
            target_language=resolved_target,
            transcription=transcription,
            audio_bytes=audio_bytes or None,
            audio_path=saved_path,
        )

    def translate(
        self,
        text: str,
        source_lang: Language,
        target_lang: Language,
        temperature: float = 0.2,
    ) -> TranslationResult:
        prompt = self._build_prompt(text, source_lang, target_lang)
        client = self._get_client()
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=temperature),
            )
            translated_text = (response.text or "").strip()
            return TranslationResult(
                text=translated_text,
                source_language=source_lang,
                target_language=target_lang,
            )
        except Exception as exc:
            if isinstance(exc, TranslationAPIError):
                raise
            raise TranslationAPIError(f"Gemini translation failed: {exc}") from exc

    async def translate_async(
        self,
        text: str,
        source_lang: Language,
        target_lang: Language,
        temperature: float = 0.2,
    ) -> TranslationResult:
        prompt = self._build_prompt(text, source_lang, target_lang)
        client = self._get_client()
        try:
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=temperature),
            )
            translated_text = (response.text or "").strip()
            return TranslationResult(
                text=translated_text,
                source_language=source_lang,
                target_language=target_lang,
            )
        except Exception as exc:
            if isinstance(exc, TranslationAPIError):
                raise
            raise TranslationAPIError(f"Async Gemini translation failed: {exc}") from exc
