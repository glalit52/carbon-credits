"""A minimal XLSX reader.

Written against the OOXML spec rather than pulled in as a dependency, for the
same reason the rest of this repository has none: a statement parser is a thing
you want to be able to audit line by line, and it only has to read cell values
from the first worksheet. Formulas are read as their cached values -- which is
what a statement contains anyway -- and styles are ignored except for the date
detection that number formats make necessary.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, timedelta
from xml.etree import ElementTree as ET

from .parser import ParseException, ParseResult

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

#: Excel's serial date epoch, with the famous 1900 leap-year bug baked in:
#: day 60 is the non-existent 29 Feb 1900, so serials above it are one day out
#: unless the epoch is shifted back by two days.
_EXCEL_EPOCH = date(1899, 12, 30)

#: Built-in number format ids that mean "this is a date".
_DATE_FORMATS = set(range(14, 23)) | {27, 30, 36, 45, 46, 47, 50, 57}


class XlsxError(ValueError):
    pass


def _column_index(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref.upper())
    if not letters:
        return 0
    index = 0
    for char in letters.group(1):
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        raw = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(raw)
    out: list[str] = []
    for item in root.findall("main:si", NS):
        out.append("".join(node.text or "" for node in item.iter(f"{{{NS['main']}}}t")))
    return out


def _date_styles(archive: zipfile.ZipFile) -> set[int]:
    """Style indexes whose number format renders as a date."""
    try:
        root = ET.fromstring(archive.read("xl/styles.xml"))
    except KeyError:
        return set()
    custom = {
        int(node.get("numFmtId", "0")): node.get("formatCode", "")
        for node in root.iter(f"{{{NS['main']}}}numFmt")
    }
    styles: set[int] = set()
    cell_xfs = root.find("main:cellXfs", NS)
    if cell_xfs is None:
        return styles
    for index, xf in enumerate(cell_xfs.findall("main:xf", NS)):
        fmt_id = int(xf.get("numFmtId", "0"))
        code = custom.get(fmt_id, "")
        if fmt_id in _DATE_FORMATS or any(token in code for token in ("yy", "dd", "mmm")):
            styles.add(index)
    return styles


def _first_sheet(archive: zipfile.ZipFile) -> str:
    names = [n for n in archive.namelist() if n.startswith("xl/worksheets/sheet")]
    if not names:
        raise XlsxError("workbook contains no worksheets")
    return sorted(names)[0]


def read_rows(data: bytes) -> list[list[str]]:
    """Every cell of the first worksheet as text, with gaps preserved.

    Gaps matter: a row read as ``["HDFC", "1200"]`` instead of
    ``["HDFC", "", "1200"]`` shifts every later column and produces a
    plausible, wrong portfolio.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise XlsxError("not a readable XLSX file") from exc

    strings = _shared_strings(archive)
    date_styles = _date_styles(archive)
    root = ET.fromstring(archive.read(_first_sheet(archive)))

    rows: list[list[str]] = []
    for row_node in root.iter(f"{{{NS['main']}}}row"):
        cells: dict[int, str] = {}
        for cell in row_node.findall("main:c", NS):
            ref = cell.get("r", "")
            index = _column_index(ref)
            cells[index] = _cell_value(cell, strings, date_styles)
        if not cells:
            continue
        width = max(cells) + 1
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def _cell_value(cell: ET.Element, strings: list[str], date_styles: set[int]) -> str:
    cell_type = cell.get("t", "n")
    if cell_type == "inlineStr":
        node = cell.find("main:is", NS)
        return "".join(t.text or "" for t in node.iter(f"{{{NS['main']}}}t")) if node is not None else ""
    value_node = cell.find("main:v", NS)
    if value_node is None or value_node.text is None:
        return ""
    raw = value_node.text
    if cell_type == "s":
        index = int(raw)
        return strings[index] if 0 <= index < len(strings) else ""
    if cell_type in {"str", "e"}:
        return raw
    if cell_type == "b":
        return "TRUE" if raw == "1" else "FALSE"

    style = int(cell.get("s", "0") or 0)
    if style in date_styles:
        try:
            serial = float(raw)
        except ValueError:
            return raw
        if serial > 0:
            return (_EXCEL_EPOCH + timedelta(days=serial)).isoformat()
    return raw


def parse_xlsx(data: bytes, *, source_name: str = "statement.xlsx", user_id: str = "") -> ParseResult:
    """Read a workbook and hand the rows to the CSV parser.

    Deliberately shares the CSV path: the column-mapping logic is the hard,
    well-tested part, and duplicating it for a second file format is how the
    two implementations start disagreeing about what a "Units" column means.
    """
    from .csv_statement import parse_csv

    try:
        rows = read_rows(data)
    except XlsxError as exc:
        return ParseResult(
            source_name=source_name, source_format="xlsx", confidence=0.0,
            exceptions=[ParseException(0, source_name, str(exc), "Re-save the file as CSV")],
        )
    if not rows:
        return ParseResult(
            source_name=source_name, source_format="xlsx", confidence=0.0,
            exceptions=[ParseException(0, source_name, "worksheet is empty")],
        )

    buffer = io.StringIO()
    import csv as _csv
    writer = _csv.writer(buffer)
    for row in rows:
        writer.writerow(row)
    result = parse_csv(buffer.getvalue(), source_name=source_name, user_id=user_id)
    result.source_format = "xlsx"
    return result
