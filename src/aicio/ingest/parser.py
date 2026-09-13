"""Format detection and the shared parse contract."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..domain import Account, Asset, Holding, Transaction
from ..provenance import Provenance, SourceKind, utcnow


@dataclass
class ParseException:
    """A line we could not read, kept rather than dropped."""

    line_no: int
    raw: str
    reason: str
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_no": self.line_no, "raw": self.raw[:300],
            "reason": self.reason, "suggestion": self.suggestion,
        }


@dataclass
class ParseResult:
    """Everything one statement yielded, including what it did not."""

    source_name: str
    source_format: str
    accounts: list[Account] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    holdings: list[Holding] = field(default_factory=list)
    transactions: list[Transaction] = field(default_factory=list)
    exceptions: list[ParseException] = field(default_factory=list)
    #: 0..1. Driven by how much of the file we understood, and carried onto
    #: every holding so a shaky import cannot masquerade as a clean one.
    confidence: float = 1.0
    statement_date: date | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def rows_read(self) -> int:
        return len(self.holdings) + len(self.transactions)

    @property
    def clean(self) -> bool:
        return not self.exceptions

    def recompute_confidence(self) -> float:
        total = self.rows_read + len(self.exceptions)
        if total == 0:
            self.confidence = 0.0
        else:
            self.confidence = round(self.rows_read / total, 4)
        return self.confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_format": self.source_format,
            "statement_date": self.statement_date.isoformat() if self.statement_date else None,
            "accounts": len(self.accounts),
            "assets": len(self.assets),
            "holdings": len(self.holdings),
            "transactions": len(self.transactions),
            "confidence": self.confidence,
            "exceptions": [e.to_dict() for e in self.exceptions],
            "notes": list(self.notes),
        }


def sniff_format(path: str | Path, data: bytes | None = None) -> str:
    """Identify a statement by its bytes, not its extension.

    A ``.xls`` that is really a CSV and a ``.txt`` that is really a CAS are
    both routine in this domain, and trusting the extension means failing on
    exactly the files users are most likely to send.
    """
    path = Path(path)
    head = (data or b"")[:2048]
    if data is None and path.exists():
        head = path.read_bytes()[:2048]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "xlsx"
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".txt"}:
        return "csv"
    if suffix in {".xlsx", ".xlsm"}:
        return "xlsx"
    if suffix == ".pdf":
        return "pdf"
    if head and b"," in head:
        return "csv"
    return "unknown"


def parse_statement(
    path: str | Path,
    *,
    data: bytes | None = None,
    password: str | None = None,
    user_id: str = "",
    today: date | None = None,
) -> ParseResult:
    """Parse any supported statement into a :class:`ParseResult`."""
    path = Path(path)
    fmt = sniff_format(path, data)
    raw = data if data is not None else (path.read_bytes() if path.exists() else b"")

    if fmt == "csv":
        from .csv_statement import parse_csv
        result = parse_csv(raw.decode("utf-8", "replace"), source_name=path.name, user_id=user_id)
    elif fmt == "xlsx":
        from .xlsx import parse_xlsx
        result = parse_xlsx(raw, source_name=path.name, user_id=user_id)
    elif fmt == "pdf":
        from .pdf_text import extract_text
        from .cas import parse_cas
        text = extract_text(raw, password=password)
        result = parse_cas(text, source_name=path.name, user_id=user_id)
    else:
        result = ParseResult(
            source_name=path.name, source_format="unknown", confidence=0.0,
            exceptions=[ParseException(0, path.name, "unrecognised file format",
                                       "Export the statement as CSV, XLSX or PDF")],
        )
    if result.statement_date is None:
        result.statement_date = today or date.today()
    result.recompute_confidence()
    return result


def statement_provenance(result: ParseResult, *, reference: str = "") -> Provenance:
    return Provenance(
        kind=SourceKind.USER_UPLOAD,
        provider=f"upload:{result.source_format}",
        observed_at=datetime.combine(
            result.statement_date or date.today(), datetime.min.time()
        ).replace(tzinfo=utcnow().tzinfo),
        reference=reference or result.source_name,
        transformation=f"parsed by aicio.ingest ({result.source_format})",
        confidence=result.confidence,
    )


def read_date(raw: str) -> date:
    """Statements use every date format ever invented. Try the plausible ones
    in an order that cannot silently swap day and month: unambiguous formats
    first, and ``DD-MM-YYYY`` before ``MM-DD-YYYY`` because this is an
    India-first product."""
    text = raw.strip().replace("/", "-").replace(".", "-")
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%d-%b-%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {raw!r}")
