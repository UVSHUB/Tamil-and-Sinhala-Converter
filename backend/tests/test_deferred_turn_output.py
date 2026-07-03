from backend.websocket.turn_buffer import DeferredTurnOutput, merge_translation_fragments

VANA = "\u0bb5\u0ba3"
VANAKKAM = "\u0bb5\u0ba3\u0b95\u0bcd\u0b95\u0bae\u0bcd"
KKAM = "\u0b95\u0bcd\u0b95\u0bae\u0bcd"


def test_merge_translation_fragments_prefers_complete_revisions():
    assert merge_translation_fragments([VANA, VANAKKAM]) == VANAKKAM


def test_merge_translation_fragments_joins_delta_chunks():
    assert merge_translation_fragments([VANA, KKAM]) == VANAKKAM


def test_deferred_turn_output_clears_text_and_audio():
    output = DeferredTurnOutput()
    output.add_translation(VANA)
    output.add_translation(VANAKKAM)
    output.add_audio(b"audio-1")
    output.add_audio(b"audio-2")

    assert output.translation_text() == VANAKKAM
    assert output.audio_chunks == [b"audio-1", b"audio-2"]

    output.clear()

    assert output.translation_text() == ""
    assert output.audio_chunks == []
