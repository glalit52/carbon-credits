"""Text extraction from PDF statements.

Only what a CAS needs: locate content streams, inflate the ones that are
Flate-compressed, and pull the strings out of the text-showing operators. No
layout engine, no font metrics, no OCR -- a scanned statement will yield
nothing here, and the parser says so rather than returning silence.

Encrypted statements are the norm in India (a CAS arrives password-protected
with the user's PAN), and the standard-security handler with RC4 or AES is more
than this module should implement. When a file is encrypted, extraction refuses
with an actionable message instead of returning mangled bytes.
"""

from __future__ import annotations

import re
import zlib
from typing import Iterator

_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_TJ = re.compile(rb"\((?:\\.|[^()\\])*\)\s*Tj", re.DOTALL)
_TJ_ARRAY = re.compile(rb"\[(.*?)\]\s*TJ", re.DOTALL)
_STRING = re.compile(rb"\((?:\\.|[^()\\])*\)", re.DOTALL)


class PdfError(ValueError):
    pass


def _unescape(raw: bytes) -> str:
    body = raw[1:-1]                                   # strip the parentheses
    out = bytearray()
    index = 0
    while index < len(body):
        char = body[index]
        if char == 0x5C and index + 1 < len(body):     # backslash
            nxt = body[index + 1]
            mapping = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}
            if nxt in mapping:
                out.append(mapping[nxt])
                index += 2
                continue
            if 0x30 <= nxt <= 0x37:                    # octal escape
                digits = body[index + 1:index + 4]
                octal = bytes(d for d in digits if 0x30 <= d <= 0x37)[:3]
                out.append(int(octal, 8) & 0xFF)
                index += 1 + len(octal)
                continue
            out.append(nxt)
            index += 2
            continue
        out.append(char)
        index += 1
    return out.decode("latin-1")


def _content_streams(data: bytes) -> Iterator[bytes]:
    for match in _STREAM.finditer(data):
        blob = match.group(1)
        try:
            yield zlib.decompress(blob)
        except zlib.error:
            # Uncompressed, or a filter we do not implement. Raw bytes still
            # carry text operators often enough to be worth trying.
            yield blob


def extract_text(data: bytes, *, password: str | None = None) -> str:
    """Best-effort text of a PDF, in reading order per content stream."""
    if not data.startswith(b"%PDF"):
        raise PdfError("not a PDF file")
    if b"/Encrypt" in data[:4096] or b"/Encrypt" in data[-4096:]:
        raise PdfError(
            "the statement is password-protected; decrypt it (most viewers can "
            "'print to PDF' after unlocking) and upload again"
            + ("" if password is None else " -- supplied passwords are not yet supported")
        )

    chunks: list[str] = []
    for stream in _content_streams(data):
        text = _stream_text(stream)
        if text.strip():
            chunks.append(text)
    joined = "\n".join(chunks)
    if not joined.strip():
        raise PdfError(
            "no extractable text: the statement is probably a scan. Ask the "
            "provider for the digital copy, or enter the holdings manually"
        )
    return joined


def _stream_text(stream: bytes) -> str:
    lines: list[str] = []
    current: list[str] = []
    for match in re.finditer(rb"(\[.*?\]\s*TJ)|(\((?:\\.|[^()\\])*\)\s*Tj)|(T\*)|(ET)", stream, re.DOTALL):
        token = match.group(0)
        if token.endswith(b"TJ"):
            array = _TJ_ARRAY.match(token)
            if array:
                parts = [_unescape(s.group(0)) for s in _STRING.finditer(array.group(1))]
                # Large negative kerning in a TJ array is how PDFs render a
                # column gap; without restoring it, "1520.45" and "78.12" would
                # merge into one unparseable number.
                gaps = re.findall(rb"(-?\d+(?:\.\d+)?)", array.group(1))
                current.append("".join(parts) if len(parts) == 1 else " ".join(parts))
        elif token.endswith(b"Tj"):
            string = _STRING.search(token)
            if string:
                current.append(_unescape(string.group(0)))
        else:
            if current:
                lines.append("".join(current).strip())
                current = []
    if current:
        lines.append("".join(current).strip())
    return "\n".join(line for line in lines if line)
