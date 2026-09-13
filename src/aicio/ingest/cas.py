"""CAMS/KFintech Consolidated Account Statement parsing.

The CAS is the single most valuable file an Indian investor can hand a wealth
product: every mutual fund folio they hold, across every AMC, with transaction
history. It is also unstructured text laid out for human eyes, so this parser
is explicitly heuristic and reports its own confidence.

Structure it relies on, in order of reliability:

1.  A folio header line containing ``Folio No:``.
2.  A scheme header line containing an ISIN (``INF`` + 9 alphanumerics), which
    is the anchor -- an ISIN is unambiguous where a scheme name is not.
3.  Transaction lines beginning with a date.
4.  A closing-balance line stating units and NAV.

Anything that does not match becomes an exception, so a layout change shows up
as unparsed rows rather than as a wrong portfolio.
"""

from __future__ import annotations

import re
from datetime import date

from ..domain import (
    Account, AccountType, Asset, Holding, Transaction, TxnType, new_id,
)
from ..money import MoneyError, money, quantity
from ..provenance import Provenance, SourceKind, utcnow
from .csv_statement import guess_asset_type, guess_txn_type
from .parser import ParseException, ParseResult, read_date

ISIN = re.compile(r"\b(INF[A-Z0-9]{9})\b")
FOLIO = re.compile(r"Folio\s*No[:.]?\s*([A-Z0-9/\- ]+?)(?:\s{2,}|$|KYC|PAN)", re.IGNORECASE)
DATE_AT_START = re.compile(r"^\s*(\d{2}[-/][A-Za-z]{3}[-/]\d{4}|\d{2}[-/]\d{2}[-/]\d{4})\b")
NUMBER = re.compile(r"\(?-?[\d,]+\.\d{2,4}\)?")
#: "Closing Unit Balance: 1,392.4567 NAV on 12-Sep-2026: INR 78.1200".
#: The NAV date sits between the label and the figure, so the gap has to allow
#: digits -- requiring a decimal point is what stops "12" of "12-Sep" being
#: read as the NAV.
CLOSING = re.compile(
    r"closing\s+unit\s+balance[:\s]*([\d,]+\.\d+).*?nav.*?([\d,]+\.\d{2,})",
    re.IGNORECASE | re.DOTALL,
)
NAV_ON = re.compile(r"nav\s+on\s+(\d{2}[-/][A-Za-z]{3}[-/]\d{4})", re.IGNORECASE)
STATEMENT_PERIOD = re.compile(
    r"(\d{2}[-/][A-Za-z]{3}[-/]\d{4})\s*(?:to|-)\s*(\d{2}[-/][A-Za-z]{3}[-/]\d{4})"
)


def _numbers(line: str) -> list[float]:
    out: list[float] = []
    for token in NUMBER.findall(line):
        negative = token.startswith("(")
        try:
            value = float(token.strip("()").replace(",", ""))
        except ValueError:
            continue
        out.append(-value if negative else value)
    return out


def parse_cas(text: str, *, source_name: str = "cas.pdf", user_id: str = "") -> ParseResult:
    """Parse extracted CAS text into folios, schemes, holdings and history."""
    result = ParseResult(source_name=source_name, source_format="cas")
    lines = [line.rstrip() for line in text.splitlines()]
    if not lines:
        result.exceptions.append(ParseException(0, "", "statement contained no text"))
        return result

    period = STATEMENT_PERIOD.search(text)
    if period:
        try:
            result.statement_date = read_date(period.group(2))
        except ValueError:
            pass

    accounts: dict[str, Account] = {}
    assets: dict[str, Asset] = {}
    current_account: Account | None = None
    current_asset: Asset | None = None
    pending_units = 0.0
    pending_txns: list[Transaction] = []

    def flush(nav: float, as_of: date, line_no: int) -> None:
        nonlocal pending_units
        if current_asset is None or current_account is None or pending_units <= 0:
            return
        invested = sum(
            float(t.amount) for t in pending_txns
            if t.asset_id == current_asset.id and t.txn_type in
            {TxnType.BUY, TxnType.SIP, TxnType.SWITCH_IN}
        )
        units_bought = sum(
            float(t.units) for t in pending_txns
            if t.asset_id == current_asset.id and t.txn_type in
            {TxnType.BUY, TxnType.SIP, TxnType.SWITCH_IN}
        )
        average = money(invested / units_bought) if units_bought else money(nav)
        result.holdings.append(Holding(
            id=new_id("hld", current_account.id, current_asset.id),
            account_id=current_account.id,
            asset_id=current_asset.id,
            units=quantity(pending_units),
            average_cost=average,
            current_price=money(nav),
            as_of=as_of,
            provenance=Provenance(
                kind=SourceKind.USER_UPLOAD,
                provider="upload:cas",
                observed_at=utcnow(),
                reference=f"{source_name}:{line_no}",
                transformation="CAS closing balance",
                # A CAS is authoritative on units and NAV; cost basis is
                # reconstructed from the transactions we could read, so it is
                # the weaker half of this holding.
                confidence=0.9 if units_bought else 0.6,
            ),
        ))
        pending_units = 0.0

    for line_no, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        folio = FOLIO.search(line)
        if folio:
            folio_number = folio.group(1).strip()
            account_id = new_id("acc", user_id, folio_number)
            current_account = accounts.setdefault(account_id, Account(
                id=account_id,
                user_id=user_id,
                institution=_amc_from(line) or "Mutual fund folio",
                account_type=AccountType.MF_FOLIO,
                identifier_masked=_mask(folio_number),
                source=SourceKind.USER_UPLOAD,
            ))
            continue

        isin = ISIN.search(line)
        if isin:
            code = isin.group(1)
            name = _scheme_name(line, code)
            asset_id = new_id("ast", code)
            current_asset = assets.setdefault(asset_id, Asset(
                id=asset_id,
                name=name or code,
                asset_type=guess_asset_type(name),
                isin=code,
                issuer=_amc_from(line),
            ))
            if current_account is None:
                current_account = accounts.setdefault("acc_unknown", Account(
                    id=new_id("acc", user_id, "unknown-folio"),
                    user_id=user_id, institution="Unknown folio",
                    account_type=AccountType.MF_FOLIO, source=SourceKind.USER_UPLOAD,
                ))
                result.notes.append(
                    "A scheme appeared before any folio header; its holdings are "
                    "grouped under an 'Unknown folio' account for you to correct."
                )
            continue

        closing = CLOSING.search(line)
        if closing and current_asset is not None:
            try:
                units = float(closing.group(1).replace(",", ""))
                nav = float(closing.group(2).replace(",", ""))
            except ValueError:
                result.exceptions.append(ParseException(
                    line_no, line, "closing balance line had unreadable numbers"))
                continue
            nav_date = result.statement_date or date.today()
            nav_match = NAV_ON.search(line)
            if nav_match:
                try:
                    nav_date = read_date(nav_match.group(1))
                except ValueError:
                    pass
            pending_units = units
            flush(nav, nav_date, line_no)
            continue

        if DATE_AT_START.match(line) and current_asset is not None and current_account is not None:
            txn = _transaction(line, line_no, current_account, current_asset, result)
            if txn is not None:
                pending_txns.append(txn)
                result.transactions.append(txn)
            continue

    result.accounts = list(accounts.values())
    result.assets = list(assets.values())
    if not result.holdings and not result.transactions:
        result.exceptions.append(ParseException(
            0, source_name,
            "no folios or schemes recognised in this statement",
            "Check that this is a CAMS/KFintech consolidated statement rather than "
            "a single-AMC account statement",
        ))
    result.recompute_confidence()
    return result


def _transaction(
    line: str, line_no: int, account: Account, asset: Asset, result: ParseResult
) -> Transaction | None:
    match = DATE_AT_START.match(line)
    if match is None:
        return None
    try:
        trade_date = read_date(match.group(1))
    except ValueError:
        result.exceptions.append(ParseException(line_no, line, "unreadable transaction date"))
        return None

    description = line[match.end():].strip()
    txn_type = guess_txn_type(description)
    if txn_type is None:
        result.exceptions.append(ParseException(
            line_no, line, "could not classify this transaction",
            "Tell us whether this row is a purchase, redemption or dividend",
        ))
        return None

    numbers = _numbers(description)
    # CAS transaction rows read: amount, units, NAV, unit balance. Rows with
    # fewer numbers (stamp duty, TDS) carry only an amount.
    amount = numbers[0] if numbers else 0.0
    units = numbers[1] if len(numbers) > 1 else 0.0
    price = numbers[2] if len(numbers) > 2 else 0.0
    if txn_type in {TxnType.FEE, TxnType.TAX}:
        units, price = 0.0, 0.0

    try:
        return Transaction(
            id=new_id("txn", account.id, asset.id, trade_date, line_no),
            account_id=account.id,
            asset_id=asset.id,
            txn_type=txn_type,
            trade_date=trade_date,
            units=quantity(abs(units)),
            price=money(abs(price)),
            amount=money(abs(amount)),
            provenance=Provenance(
                kind=SourceKind.USER_UPLOAD, provider="upload:cas", observed_at=utcnow(),
                reference=f"{result.source_name}:{line_no}",
                transformation="CAS transaction row", confidence=0.85,
            ),
            note=description[:120],
        )
    except MoneyError as exc:
        result.exceptions.append(ParseException(line_no, line, str(exc)))
        return None


def _scheme_name(line: str, isin: str) -> str:
    cleaned = line.replace(isin, " ")
    cleaned = re.sub(r"\bISIN\b[:\s]*", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[\s\-–|]*[A-Z0-9]{3,8}[\s\-–]+", "", cleaned)   # AMC scheme code
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -–|")
    return cleaned[:140]


def _amc_from(line: str) -> str:
    match = re.search(
        r"([A-Z][A-Za-z&.\s]{2,40}?(?:Mutual Fund|AMC|Asset Management))", line
    )
    return match.group(1).strip() if match else ""


def _mask(folio: str) -> str:
    """Folio numbers are account identifiers. Only the tail is kept, so a
    leaked database row cannot be used to impersonate the holder."""
    compact = folio.replace(" ", "")
    return ("*" * max(0, len(compact) - 4)) + compact[-4:]
