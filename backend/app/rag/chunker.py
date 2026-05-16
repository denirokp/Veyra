"""Семантический chunking — разбивка по разделам документа."""
from __future__ import annotations

import re
from dataclasses import dataclass

CHUNK_TARGET_TOKENS = 500


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


def _split_long_section(body: str, step_chars: int) -> list[str]:
    """Разбивает длинный раздел построчно. Если граница части попадает внутрь
    Markdown-таблицы — переносит строку-заголовок и разделитель таблицы в
    новую часть, иначе строки данных теряют имена колонок."""
    lines = body.splitlines()
    pieces: list[str] = []
    buf: list[str] = []
    buf_len = 0
    table_header: list[str] = []

    for i, line in enumerate(lines):
        is_header = (
            line.startswith("|")
            and i + 1 < len(lines)
            and lines[i + 1].lstrip().startswith("| ---")
        )
        if is_header:
            table_header = [line, lines[i + 1]]
        elif line.strip() and not line.startswith("|"):
            table_header = []

        if buf and buf_len + len(line) > step_chars:
            pieces.append("\n".join(buf).strip())
            buf, buf_len = [], 0
            starts_table_body = (
                table_header
                and line.startswith("|")
                and line not in table_header
                and not line.lstrip().startswith("| ---")
            )
            if starts_table_body:
                buf.extend(table_header)
                buf_len += sum(len(x) + 1 for x in table_header)

        buf.append(line)
        buf_len += len(line) + 1

    if buf:
        pieces.append("\n".join(buf).strip())

    return [p for p in pieces if p]


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
            for piece in _split_long_section(body, CHUNK_TARGET_TOKENS * 4):
                chunks.append(Chunk(
                    content=piece,
                    section=h1,
                    subsection=h2,
                    chunk_index=idx,
                    token_count=_approx_tokens(piece),
                    metadata={**document_metadata, "section": h1, "subsection": h2},
                ))
                idx += 1

    return chunks
