"""Декодирует Confluence MHTML-экспорты (.doc с MIME-обёрткой) в plain text.

Confluence при экспорте «Web Page (Single File)» делает MHTML-конверт:
multipart/related + quoted-printable HTML с embedded картинками. textutil
конвертирует это в .docx как сырой текст — Claude видит =D0=... + теги.

Скрипт читает оригинальные .doc-файлы, отделяет MIME-обёртку, декодирует
quoted-printable, превращает HTML в чистый текст и пишет .txt рядом.

    python scripts/decode_confluence_mhtml.py <directory>
"""
from __future__ import annotations

import email
import email.policy
import re
import sys
from html import unescape
from pathlib import Path


_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
_HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head>", re.DOTALL | re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BLOCK_OPEN_RE = re.compile(
    r"<(p|div|br|tr|li|h[1-6])\b[^>]*/?>", re.IGNORECASE
)
_BLOCK_CLOSE_RE = re.compile(r"</(p|div|tr|li|h[1-6])>", re.IGNORECASE)
_CELL_OPEN_RE = re.compile(r"<(td|th)\b[^>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(html: str) -> str:
    """Конвертирует HTML в чистый текст: убирает script/style/head/comments,
    переводит блочные теги в \\n, ячейки в \\t, остальные теги выкидывает,
    декодирует HTML-entities, сжимает пробелы."""
    html = _SCRIPT_RE.sub(" ", html)
    html = _STYLE_RE.sub(" ", html)
    html = _HEAD_RE.sub(" ", html)
    html = _COMMENT_RE.sub(" ", html)
    html = _BLOCK_OPEN_RE.sub("\n", html)
    html = _BLOCK_CLOSE_RE.sub("\n", html)
    html = _CELL_OPEN_RE.sub("\t", html)
    html = _TAG_RE.sub("", html)
    html = unescape(html)
    lines = [" ".join(ln.split()) for ln in html.splitlines()]
    out: list[str] = []
    prev_blank = False
    for ln in lines:
        if not ln:
            if not prev_blank:
                out.append("")
            prev_blank = True
        else:
            out.append(ln)
            prev_blank = False
    return "\n".join(out).strip()


def is_mhtml(path: Path) -> bool:
    try:
        head = path.open("rb").read(2048).decode("ascii", errors="ignore")
    except OSError:
        return False
    return "MIME-Version:" in head and "Content-Type:" in head


def decode_one(path: Path) -> str | None:
    if not is_mhtml(path):
        return None
    with path.open("rb") as f:
        msg = email.message_from_binary_file(f, policy=email.policy.default)
    html_text: str | None = None
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                html_text = payload.decode(charset, errors="replace")
            except (UnicodeDecodeError, LookupError):
                html_text = payload.decode("utf-8", errors="replace")
            break
    if not html_text:
        return None
    return html_to_text(html_text)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/decode_confluence_mhtml.py <directory>")
        sys.exit(1)
    root = Path(sys.argv[1]).expanduser()
    if not root.is_dir():
        print(f"Not a directory: {root}")
        sys.exit(1)

    converted = skipped = failed = 0
    for path in sorted(root.rglob("*.doc")):
        if path.suffix.lower() == ".docx":
            continue
        try:
            text = decode_one(path)
        except Exception as exc:
            print(f"  ОШИБКА {path.name}: {exc}")
            failed += 1
            continue
        if text is None:
            print(f"  не MHTML: {path.name}")
            skipped += 1
            continue
        out = path.with_suffix(".txt")
        out.write_text(text, encoding="utf-8")
        print(f"  + {out.name} ({len(text):,} chars)")
        converted += 1

    print(
        f"\nИтого: декодировано {converted}, пропущено (не MHTML) {skipped}, "
        f"ошибок {failed}"
    )


if __name__ == "__main__":
    main()
