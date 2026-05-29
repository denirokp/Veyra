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
import sys
from html.parser import HTMLParser
from pathlib import Path


class HTMLTextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "head", "meta"}
    BLOCK_TAGS = {
        "p", "div", "br", "tr", "li",
        "h1", "h2", "h3", "h4", "h5", "h6",
    }
    CELL_TAGS = {"td", "th"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in self.CELL_TAGS:
            self.parts.append("\t")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1
            return
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [ln.strip() for ln in raw.splitlines()]
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
    parser = HTMLTextExtractor()
    parser.feed(html_text)
    return parser.text()


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
