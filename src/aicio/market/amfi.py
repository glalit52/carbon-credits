"""AMFI: the authoritative NAV source for Indian mutual funds.

AMFI publishes every scheme's declared NAV daily as a semicolon-delimited text
file. It is the right primary source for an India-first product: it is the
industry body's own number, it is free to use, it covers every scheme, and it
is keyed by ISIN, which is the identifier the rest of this system resolves on.

It is also a once-a-day file. Nothing here pretends to be intraday, and the
provenance attached says "declared NAV" with the declaration date, so a user
looking at a Sunday dashboard sees Friday's NAV labelled as Friday's.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .cache import Cache
from .providers import (
    FundInfo, MarketDataProvider, NavPoint, ProviderError, http_text,
)

NAV_ALL_URL = os.environ.get(
    "AICIO_AMFI_NAV_URL", "https://www.amfiindia.com/spages/NAVAll.txt"
)
#: Historical NAVs for one scheme over a date range. Used for rolling returns
#: and drawdown, which a single day's file cannot support.
NAV_HISTORY_URL = os.environ.get(
    "AICIO_AMFI_HISTORY_URL",
    "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx",
)

HEADER_PREFIX = "Scheme Code"


@dataclass
class AmfiRow:
    scheme_code: str
    isin_growth: str
    isin_reinvest: str
    name: str
    nav: float
    on: date
    category: str = ""
    amc: str = ""


def parse_navall(text: str) -> list[AmfiRow]:
    """Parse the NAVAll file.

    The file interleaves data with two kinds of unmarked heading -- a category
    line in parentheses and a bare AMC name -- so the parser tracks both as it
    goes. That context is worth keeping: it is where a scheme's category and
    fund house come from without a second lookup.
    """
    rows: list[AmfiRow] = []
    category = ""
    amc = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(HEADER_PREFIX):
            continue
        if ";" not in line:
            if "(" in line and line.endswith(")"):
                category = line[line.find("(") + 1:-1].strip()
            else:
                amc = line
            continue
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 6:
            continue
        code, isin_growth, isin_reinvest, name, nav_raw, date_raw = parts[:6]
        if nav_raw.upper() in {"N.A.", "NA", "-", ""}:
            continue                              # a scheme with no NAV declared today
        try:
            nav = float(nav_raw)
            on = datetime.strptime(date_raw, "%d-%b-%Y").date()
        except ValueError:
            continue
        rows.append(AmfiRow(
            scheme_code=code,
            isin_growth="" if isin_growth in {"-", "N.A."} else isin_growth,
            isin_reinvest="" if isin_reinvest in {"-", "N.A."} else isin_reinvest,
            name=name, nav=nav, on=on, category=category, amc=amc,
        ))
    return rows


class AmfiProvider(MarketDataProvider):
    """NAV and basic reference data for Indian mutual funds."""

    name = "amfi"
    covers = ("fund",)

    def __init__(self, cache: Cache | None = None, *, ttl: int = 6 * 3600) -> None:
        self.cache = cache
        self.ttl = ttl
        self._index: dict[str, AmfiRow] = {}
        self._loaded_on: date | None = None

    # -- loading -----------------------------------------------------------

    def load(self, text: str | None = None) -> int:
        """Populate the in-process index, from a supplied file or from AMFI.

        Accepting text directly is what lets the whole ingest path be tested,
        demoed and run offline with a checked-in fixture.
        """
        if text is None:
            text = self._fetch()
        rows = parse_navall(text)
        index: dict[str, AmfiRow] = {}
        for row in rows:
            index[row.scheme_code] = row
            for isin in (row.isin_growth, row.isin_reinvest):
                if isin:
                    index[isin] = row
        self._index = index
        self._loaded_on = rows[0].on if rows else None
        return len(rows)

    def _fetch(self) -> str:
        if self.cache is not None:
            cached = self.cache.get("amfi:navall", ttl=self.ttl)
            if cached:
                return cached
        text = http_text(NAV_ALL_URL)
        if HEADER_PREFIX not in text[:400]:
            raise ProviderError("AMFI response did not look like the NAV file")
        if self.cache is not None:
            self.cache.put("amfi:navall", text)
        return text

    @property
    def loaded(self) -> bool:
        return bool(self._index)

    # -- provider protocol -------------------------------------------------

    def nav(self, *, isin: str = "", scheme_code: str = "") -> NavPoint | None:
        if not self.loaded:
            self.load()
        row = self._index.get(isin) or self._index.get(scheme_code)
        if row is None:
            return None
        return NavPoint(
            scheme_code=row.scheme_code, isin=isin or row.isin_growth,
            name=row.name, nav=row.nav, on=row.on, provider=self.name,
        )

    def fund_info(self, isin: str) -> FundInfo | None:
        if not self.loaded:
            self.load()
        row = self._index.get(isin)
        if row is None:
            return None
        return FundInfo(
            isin=isin, name=row.name, category=row.category, amc=row.amc,
            as_of=row.on, provider=self.name,
        )

    def nav_history(
        self, *, isin: str = "", scheme_code: str = "", start: date | None = None
    ) -> list[NavPoint]:
        """Historical NAVs for one scheme.

        AMFI's history endpoint is a report generator rather than an API, so
        this is best-effort and returns an empty list rather than raising when
        the layout is not what we expect -- a missing history degrades rolling
        returns to "not available", which the analytics layer handles.
        """
        if not scheme_code and isin:
            if not self.loaded:
                self.load()
            row = self._index.get(isin)
            scheme_code = row.scheme_code if row else ""
        if not scheme_code:
            return []
        start = start or date(date.today().year - 3, 1, 1)
        url = (
            f"{NAV_HISTORY_URL}?frmdt={start.strftime('%d-%b-%Y')}"
            f"&todt={date.today().strftime('%d-%b-%Y')}&mf=&scode={scheme_code}"
        )
        key = f"amfi:history:{scheme_code}:{start.isoformat()}"
        text: str | None = None
        if self.cache is not None:
            text = self.cache.get(key, ttl=24 * 3600)
        if text is None:
            try:
                text = http_text(url)
            except ProviderError:
                return []
            if self.cache is not None:
                self.cache.put(key, text)
        points = [
            NavPoint(row.scheme_code, isin or row.isin_growth, row.name, row.nav, row.on, self.name)
            for row in parse_navall(text)
            if row.scheme_code == scheme_code
        ]
        return sorted(points, key=lambda p: p.on)

    def search(self, term: str, *, limit: int = 20) -> list[AmfiRow]:
        """Find schemes by name. The only way a user can attach a manually
        entered holding to a real ISIN."""
        if not self.loaded:
            self.load()
        needle = term.lower()
        seen: set[str] = set()
        out: list[AmfiRow] = []
        for row in self._index.values():
            if row.scheme_code in seen:
                continue
            if needle in row.name.lower():
                seen.add(row.scheme_code)
                out.append(row)
            if len(out) >= limit:
                break
        return out

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "status": "ok" if self.loaded else "not loaded",
            "schemes": len({r.scheme_code for r in self._index.values()}),
            "nav_date": self._loaded_on.isoformat() if self._loaded_on else None,
            "source": NAV_ALL_URL,
        }
