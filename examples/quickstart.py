"""Quickstart examples for sinhala-tamil-converter."""

import asyncio
from sinhala_tamil_converter import (
    SinhalaTamilConverter,
    auto_translate,
    detect_language,
    translate_sinhala_to_tamil,
    translate_tamil_to_sinhala,
)


def demo_convenience_functions():
    print("--- 1. Quick 2-3 Line Translation ---")
    sinhala_sample = "ආයුබෝවන්, ඔබට කොහොමද?"
    tamil_translation = translate_sinhala_to_tamil(sinhala_sample)
    print(f"Sinhala Input: {sinhala_sample}")
    print(f"Tamil Output:  {tamil_translation}\n")

    tamil_sample = "வணக்கம், நீங்கள் எப்படி இருக்கிறீர்கள்?"
    sinhala_translation = translate_tamil_to_sinhala(tamil_sample)
    print(f"Tamil Input:   {tamil_sample}")
    print(f"Sinhala Output:{sinhala_translation}\n")


def demo_auto_detection():
    print("--- 2. Auto-Language Detection ---")
    text = "සුභ උදෑසනක්"
    lang = detect_language(text)
    print(f"Text: '{text}' -> Detected Language: {lang}")

    result = auto_translate(text)
    print(f"Auto-translate Result: [{result.source_language} -> {result.target_language}]: {result.text}\n")


async def demo_async():
    print("--- 3. Async & Batch Translation ---")
    converter = SinhalaTamilConverter()
    texts = [
        "ස්තූතියි",
        "සුභ රාත්‍රියක්",
    ]
    results = await converter.batch_translate_async(texts, source="sinhala", target="tamil")
    for orig, res in zip(texts, results):
        print(f"'{orig}' -> '{res.text}'")


if __name__ == "__main__":
    demo_convenience_functions()
    demo_auto_detection()
    asyncio.run(demo_async())
