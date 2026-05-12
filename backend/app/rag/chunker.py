"""Семантический chunking — разбивка по разделам документа."""
from __future__ import annotations

import re
from dataclasses import dataclass

CHUNK_TARGET_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50


@dataclass
class Chunk:
    content: str
    section: str
    subsection: str
    chunk_index: int
    token_count: int
    metadata: dict


def _approx_tokens(text: str) -> int:
    return len(text) // 4  # грубая оценка: 4 символа ≈ 1 токен


def split_by_headers(text: str) -> list[tuple[str, str, str]]:
    """Возвращает (h1, h2, body) для каждого раздела."""
    sections = []
    current_h1 = ""
    current_h2 = ""
    buffer: list[str] = []

    for line in text.splitlines():
        if re.match(r"^#{1,2} ", line):
            if buffer:
                sections.append((current_h1, current_h2, "\n".join(buffer).strip()))
                buffer = []
            level = len(re.match(r"^(#+)", line).group(1))
            title = line.lstrip("# ").strip()
            if level == 1:
                current_h1 = title
                current_h2 = ""
            else:
                current_h2 = title
        else:
            buffer.append(line)

    if buffer:
        sections.append((current_h1, current_h2, "\n".join(buffer).strip()))

    return [(h1, h2, body) for h1, h2, body in sections if body]


def chunk_document(text: str, document_metadata: dict) -> list[Chunk]:
    sections = split_by_headers(text)
    chunks: list[Chunk] = []
    idx = 0

    for h1, h2, body in sections:
        if _approx_tokens(body) <= CHUNK_TARGET_TOKENS:
            chunks.append(Chunk(
                content=body,
                section=h1,
                subsection=h2,
                chunk_index=idx,
                token_count=_approx_tokens(body),
                metadata={**document_metadata, "section": h1, "subsection": h2},
            ))
            idx += 1
        else:
            # Разбиваем длинный раздел на части с overlap
            words = body.split()
            step = CHUNK_TARGET_TOKENS * 4  # символов
            overlap = CHUNK_OVERLAP_TOKENS * 4
            start = 0
            while start < len(body):
                piece = body[start: start + step]
                chunks.append(Chunk(
                    content=piece,
                    section=h1,
                    subsection=h2,
                    chunk_index=idx,
                    token_count=_approx_tokens(piece),
                    metadata={**document_metadata, "section": h1, "subsection": h2},
                ))
                idx += 1
                start += step - overlap

    return chunks
