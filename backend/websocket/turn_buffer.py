from dataclasses import dataclass, field


def merge_translation_fragments(fragments: list[str]) -> str:
    """Merge streamed text fragments into the best complete turn text."""
    merged = ""
    for fragment in fragments:
        piece = fragment
        normalized_piece = piece.strip()
        if not normalized_piece:
            continue
        if not merged:
            merged = normalized_piece
            continue

        normalized_merged = merged.strip()
        if normalized_piece == normalized_merged or normalized_piece in normalized_merged:
            continue
        if normalized_merged in normalized_piece:
            merged = normalized_piece
            continue

        overlap = 0
        max_overlap = min(len(merged), len(piece))
        for size in range(max_overlap, 0, -1):
            if merged.endswith(piece[:size]):
                overlap = size
                break

        merged = f"{merged}{piece[overlap:]}"

    return merged.strip()


@dataclass
class DeferredTurnOutput:
    translation_fragments: list[str] = field(default_factory=list)
    audio_chunks: list[bytes] = field(default_factory=list)

    def add_translation(self, text: str | None) -> None:
        if text and text.strip():
            self.translation_fragments.append(text)

    def add_audio(self, data: bytes | None) -> None:
        if data:
            self.audio_chunks.append(data)

    def translation_text(self) -> str:
        return merge_translation_fragments(self.translation_fragments)

    def clear(self) -> None:
        self.translation_fragments.clear()
        self.audio_chunks.clear()
