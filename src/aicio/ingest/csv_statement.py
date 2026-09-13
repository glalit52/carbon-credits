"""CSV and TSV statements.

Broker exports have no common schema, so the parser matches columns by meaning
rather than by position: a column called ``Qty``, ``Units``, ``Quantity`` or
``Balance Units`` is all the same field. Anything it cannot map becomes an
exception with the header it saw, which is far more useful to a user than
"invalid file".
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from typing import Any, Iterable

from ..domain import (
    Account, AccountType, Asset, AssetType, Holding, Transaction, TxnType, new_id,
)
from ..money import MoneyError, money, quantity
from ..provenance import Provenance, SourceKind, utcnow
from .parser import ParseException, ParseResult, read_date

#: Header synonyms, normalised to lowercase alphanumerics before matching.
COLUMNS: dict[str, tuple[str, ...]] = {
    "name": ("name", "schemename", "securityname", "instrument", "scheme", "fundname",
             "symbol", "tradingsymbol", "description", "particulars"),
    "isin": ("isin", "isincode"),
    "ticker": ("ticker", "symbol", "tradingsymbol", "scripcode", "nsecode", "bsecode"),
    "folio": ("folio", "folionumber", "folionum", "accountno", "account", "clientid", "dpid"),
    "units": ("units", "quantity", "qty", "balanceunits", "closingunits", "shares",
              "closingbalance", "holdingqty"),
    "price": ("price", "nav", "currentnav", "ltp", "closingprice", "marketprice", "rate"),
    "cost": ("avgcost", "averagecost", "averageprice", "buyavg", "costperunit",
             "purchasenav", "buyprice", "avgprice"),
    "value": ("value", "marketvalue", "currentvalue", "amount", "marketval", "closingvalue"),
    "invested": ("invested", "investedvalue", "costvalue", "purchasevalue", "totalcost"),
    "date": ("date", "transactiondate", "traddate", "tradedate", "valuedate", "asondate"),
    "type": ("type", "transactiontype", "txntype", "action", "buysell", "narration"),
    "category": ("category", "assetclass", "schemecategory", "type2", "producttype"),
    "institution": ("institution", "broker", "amc", "fundhouse", "depository"),
    "sector": ("sector", "industry"),
}

#: Words that identify a transaction row's direction. Ordered longest-first at
#: match time so "switch out" is not read as "switch".
TXN_WORDS: tuple[tuple[str, TxnType], ...] = (
    ("systematic investment", TxnType.SIP), ("sip", TxnType.SIP),
    ("switch out", TxnType.SWITCH_OUT), ("switch-out", TxnType.SWITCH_OUT),
    ("switch in", TxnType.SWITCH_IN), ("switch-in", TxnType.SWITCH_IN),
    ("redemption", TxnType.SELL), ("redeem", TxnType.SELL), ("sell", TxnType.SELL),
    ("purchase", TxnType.BUY), ("buy", TxnType.BUY), ("subscription", TxnType.BUY),
    ("dividend", TxnType.DIVIDEND), ("idcw", TxnType.DIVIDEND),
    ("interest", TxnType.INTEREST), ("bonus", TxnType.BONUS), ("split", TxnType.SPLIT),
    ("stamp duty", TxnType.FEE), ("fee", TxnType.FEE), ("tds", TxnType.TAX),
)


def _key(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def map_columns(headers: Iterable[str]) -> dict[str, int]:
    """Field name -> column index. First match wins, so a file with both
    ``Symbol`` and ``Name`` maps ``name`` to ``Name``."""
    mapping: dict[str, int] = {}
    normalised = [_key(h) for h in headers]
    for field_name, synonyms in COLUMNS.items():
        for synonym in synonyms:
            if synonym in normalised:
                mapping.setdefault(field_name, normalised.index(synonym))
                break
    return mapping


def guess_asset_type(name: str, category: str = "") -> AssetType:
    """Classify from the instrument's own name.

    Fund names are unusually informative -- an Indian scheme name states its
    category by regulation -- so this is reliable in a way that name-based
    heuristics usually are not.
    """
    text = f"{name} {category}".lower()
    if "elss" in text or "tax saver" in text or "taxsaver" in text:
        return AssetType.ELSS
    if "liquid" in text or "overnight" in text or "money market" in text:
        return AssetType.LIQUID_FUND
    if any(word in text for word in ("index", "nifty 50", "sensex", "nifty50")) and "fund" in text:
        return AssetType.INDEX_FUND
    if "etf" in text:
        return AssetType.GOLD_ETF if "gold" in text else AssetType.ETF
    if any(word in text for word in ("hybrid", "balanced", "advantage", "asset allocat")):
        return AssetType.HYBRID_FUND
    # Checked before the debt list: "Sovereign Gold Bond" contains "bond" and
    # would otherwise be filed as a debt fund, which is wrong about its asset
    # class, its tax treatment and its lock-in all at once.
    if "sovereign gold" in text or "sgb" in text:
        return AssetType.SGB
    if any(word in text for word in ("debt", "bond", "gilt", "corporate bond", "credit risk",
                                     "short duration", "ultra short", "banking and psu", "income")):
        return AssetType.DEBT_FUND
    if any(word in text for word in ("equity", "flexi cap", "flexicap", "large cap", "mid cap",
                                     "small cap", "multi cap", "focused", "value fund",
                                     "contra", "bluechip", "opportunities")):
        return AssetType.EQUITY_FUND
    if "gold" in text:
        return AssetType.GOLD_ETF
    if "reit" in text or "invit" in text:
        return AssetType.REIT
    if any(word in text for word in ("ppf", "public provident")):
        return AssetType.PPF
    if "epf" in text or "provident fund" in text:
        return AssetType.EPF
    if "nps" in text or "pension" in text:
        return AssetType.NPS
    if any(word in text for word in ("fd", "fixed deposit", "term deposit")):
        return AssetType.FIXED_DEPOSIT
    if "fund" in text or "scheme" in text:
        return AssetType.EQUITY_FUND
    return AssetType.STOCK


def guess_txn_type(text: str) -> TxnType | None:
    lowered = text.lower()
    for word, txn_type in TXN_WORDS:
        if word in lowered:
            return txn_type
    return None


def _dialect(sample: str) -> Any:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def parse_csv(text: str, *, source_name: str = "statement.csv", user_id: str = "") -> ParseResult:
    """Parse a delimited holdings or transactions export."""
    result = ParseResult(source_name=source_name, source_format="csv")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        result.exceptions.append(ParseException(0, "", "file is empty"))
        return result

    # Some exports prepend a title block before the real header; find the first
    # row that maps at least two known fields.
    header_index, mapping = 0, {}
    reader_rows = list(csv.reader(io.StringIO(text), _dialect("\n".join(lines[:5]))))
    for index, row in enumerate(reader_rows[:15]):
        candidate = map_columns(row)
        if len({"name", "units"} & candidate.keys()) == 2 or len(candidate) >= 4:
            header_index, mapping = index, candidate
            break
    if not mapping:
        result.exceptions.append(ParseException(
            1, ",".join(reader_rows[0])[:200] if reader_rows else "",
            "no recognisable column headers",
            "Expected at least a name/scheme column and a units/quantity column",
        ))
        return result

    headers = reader_rows[header_index]
    result.notes.append(
        f"Mapped columns: " + ", ".join(f"{k}<-{headers[v]}" for k, v in sorted(mapping.items()))
    )
    is_transactions = "date" in mapping and ("type" in mapping or "price" in mapping)

    account = Account(
        id=new_id("acc", user_id, source_name),
        user_id=user_id,
        institution=_first_value(reader_rows, mapping.get("institution")) or "Imported",
        account_type=AccountType.MF_FOLIO if is_transactions else AccountType.DEMAT,
        source=SourceKind.USER_UPLOAD,
    )
    result.accounts.append(account)

    seen_assets: dict[str, Asset] = {}
    for offset, row in enumerate(reader_rows[header_index + 1:], start=header_index + 2):
        if not any(cell.strip() for cell in row):
            continue
        try:
            _row(row, mapping, account, seen_assets, result, offset, is_transactions)
        except (MoneyError, ValueError) as exc:
            result.exceptions.append(ParseException(
                offset, ",".join(row)[:300], str(exc),
                "Correct the row in the app, or re-export with numeric amounts",
            ))

    result.assets = list(seen_assets.values())
    result.recompute_confidence()
    return result


def _first_value(rows: list[list[str]], index: int | None) -> str:
    if index is None:
        return ""
    for row in rows[1:]:
        if len(row) > index and row[index].strip():
            return row[index].strip()
    return ""


def _cell(row: list[str], mapping: dict[str, int], field_name: str) -> str:
    index = mapping.get(field_name)
    if index is None or index >= len(row):
        return ""
    return row[index].strip()


def _row(
    row: list[str],
    mapping: dict[str, int],
    account: Account,
    seen: dict[str, Asset],
    result: ParseResult,
    line_no: int,
    is_transactions: bool,
) -> None:
    name = _cell(row, mapping, "name")
    if not name:
        raise ValueError("row has no instrument name")
    # Totals rows are a classic source of phantom holdings.
    if name.lower().strip().rstrip(":") in {"total", "grand total", "subtotal", "sum"}:
        return

    isin = _cell(row, mapping, "isin")
    asset_id = new_id("ast", isin or name.lower())
    if asset_id not in seen:
        seen[asset_id] = Asset(
            id=asset_id,
            name=name,
            asset_type=guess_asset_type(name, _cell(row, mapping, "category")),
            isin=isin,
            ticker=_cell(row, mapping, "ticker"),
            category=_cell(row, mapping, "category"),
            sector=_cell(row, mapping, "sector"),
        )

    provenance = Provenance(
        kind=SourceKind.USER_UPLOAD,
        provider=f"upload:{result.source_format}",
        observed_at=utcnow(),
        reference=f"{result.source_name}:{line_no}",
        transformation="csv column mapping",
        confidence=0.95,
    )

    if is_transactions:
        raw_type = _cell(row, mapping, "type") or name
        txn_type = guess_txn_type(raw_type)
        if txn_type is None:
            raise ValueError(f"cannot tell whether {raw_type!r} is a buy or a sell")
        trade_date = read_date(_cell(row, mapping, "date"))
        units_raw = _cell(row, mapping, "units")
        amount_raw = _cell(row, mapping, "value") or _cell(row, mapping, "invested")
        price_raw = _cell(row, mapping, "price")
        result.transactions.append(Transaction(
            id=new_id("txn", account.id, asset_id, trade_date, units_raw, amount_raw, line_no),
            account_id=account.id,
            asset_id=asset_id,
            txn_type=txn_type,
            trade_date=trade_date,
            units=quantity(units_raw) if units_raw else 0,
            price=money(price_raw) if price_raw else 0,
            amount=money(amount_raw) if amount_raw else 0,
            provenance=provenance,
        ))
        return

    units_raw = _cell(row, mapping, "units")
    if not units_raw:
        raise ValueError("holding row has no units or quantity")
    units = quantity(units_raw)
    if units == 0:
        return                                    # a closed position, not an error

    price_raw = _cell(row, mapping, "price")
    value_raw = _cell(row, mapping, "value")
    if price_raw:
        price = money(price_raw)
    elif value_raw:
        price = money(money(value_raw) / units)
    else:
        raise ValueError("holding row has neither a price/NAV nor a market value")

    cost_raw = _cell(row, mapping, "cost")
    invested_raw = _cell(row, mapping, "invested")
    if cost_raw:
        average_cost = money(cost_raw)
    elif invested_raw:
        average_cost = money(money(invested_raw) / units)
    else:
        # Without cost basis there is no gain and no tax position. Assuming the
        # current price would silently report a zero gain, so the holding is
        # kept and the gap is recorded as a note instead.
        average_cost = price
        result.notes.append(f"{name}: no cost basis in the file; gains cannot be computed")

    result.holdings.append(Holding(
        id=new_id("hld", account.id, asset_id),
        account_id=account.id,
        asset_id=asset_id,
        units=units,
        average_cost=average_cost,
        current_price=price,
        as_of=result.statement_date or date.today(),
        provenance=provenance,
    ))
