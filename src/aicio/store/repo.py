"""The repository.

Plain SQL, one class, no ORM. Two things here are worth more than they cost:

*   **Every write lands in a hash-chained audit log.** A recommendation shown,
    a user's approval, a consent revoked, a token stored -- each commits to the
    hash of the row before it. Editing history becomes detectable rather than
    invisible, which is what "maintain audit logs for recommendations and
    approvals" has to mean to be worth anything.
*   **Documents and tokens are sealed before they reach the disk.** There is no
    code path that writes a statement or an access token in plaintext, so
    "encrypted at rest" is a property of the type rather than a discipline.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..analysis import PortfolioAnalysis
from ..crypto import CryptoError, SealedBox
from ..decisions.engine import RecommendationSet
from ..domain import (
    Account, AccountType, Alert, AlertStatus, Asset, AssetType, Conversation,
    DecisionOutcome, DecisionRecord, FinancialProfile, Frequency, Goal, GoalType,
    Holding, Portfolio, Priority, SIP, Transaction, TxnType, User,
)
from ..ips import InvestmentPolicy
from ..market.connectors import TokenVault
from ..money import money, quantity
from ..provenance import Provenance, SourceKind, utcnow

GENESIS = "0" * 64


class StoreError(RuntimeError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


class Store:
    """A connection to one database, with an actor attached to its writes."""

    def __init__(self, path: str | Path, *, actor: str = "system",
                 box: SealedBox | None = None) -> None:
        self.path = str(path)
        self.actor = actor
        self._box = box
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        from .schema import migrate
        self.version = migrate(self.connection)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- audit -------------------------------------------------------------

    def _last_hash(self) -> str:
        row = self.connection.execute(
            "SELECT hash FROM audit_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["hash"] if row else GENESIS

    def record(
        self, event: str, *, user_id: str = "", subject: str = "",
        payload: dict[str, Any] | None = None, actor: str | None = None,
    ) -> str:
        """Append an audit event. Returns its hash."""
        previous = self._last_hash()
        created = utcnow().isoformat()
        body = _json(payload or {})
        digest = hashlib.sha256(
            "|".join([previous, actor or self.actor, event, user_id, subject, body, created])
            .encode()
        ).hexdigest()
        with self.connection:
            self.connection.execute(
                "INSERT INTO audit_events "
                "(user_id, actor, event, subject, payload_json, prev_hash, hash, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (user_id, actor or self.actor, event, subject, body, previous, digest, created),
            )
        return digest

    def verify_chain(self) -> tuple[bool, int | None]:
        """Walk the audit log and confirm each row still commits to the last."""
        previous = GENESIS
        for row in self.connection.execute("SELECT * FROM audit_events ORDER BY id"):
            digest = hashlib.sha256(
                "|".join([previous, row["actor"], row["event"], row["user_id"],
                          row["subject"], row["payload_json"], row["created_at"]]).encode()
            ).hexdigest()
            if digest != row["hash"] or row["prev_hash"] != previous:
                return False, row["id"]
            previous = row["hash"]
        return True, None

    def audit_trail(self, user_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        if user_id:
            rows = self.connection.execute(
                "SELECT * FROM audit_events WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            )
        else:
            rows = self.connection.execute(
                "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)
            )
        return [
            {"id": r["id"], "actor": r["actor"], "event": r["event"], "subject": r["subject"],
             "created_at": r["created_at"], "hash": r["hash"][:16]}
            for r in rows
        ]

    # -- users -------------------------------------------------------------

    def save_user(self, user: User) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO users (id, email, name, country, currency, timezone, locale, "
                "quiet_start, quiet_end, channels, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET email=excluded.email, name=excluded.name, "
                "country=excluded.country, currency=excluded.currency, "
                "timezone=excluded.timezone, locale=excluded.locale, "
                "quiet_start=excluded.quiet_start, quiet_end=excluded.quiet_end, "
                "channels=excluded.channels",
                (user.id, user.email, user.name, user.country, user.base_currency,
                 user.timezone, user.locale, user.quiet_hours[0], user.quiet_hours[1],
                 ",".join(user.notification_channels), user.created_at.isoformat()),
            )
            for purpose, granted in user.consents.items():
                self.connection.execute(
                    "INSERT INTO consents (user_id, purpose, granted_at) VALUES (?,?,?)",
                    (user.id, purpose, granted.isoformat()),
                )
        self.record("user.saved", user_id=user.id, subject=user.id)

    def load_user(self, user_id: str) -> User:
        row = self.connection.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise StoreError(f"no user {user_id!r}")
        user = User(
            id=row["id"], email=row["email"], name=row["name"], country=row["country"],
            base_currency=row["currency"], timezone=row["timezone"], locale=row["locale"],
            created_at=datetime.fromisoformat(row["created_at"]),
            quiet_hours=(row["quiet_start"], row["quiet_end"]),
            notification_channels=tuple(row["channels"].split(",")) if row["channels"] else (),
        )
        for consent in self.connection.execute(
            "SELECT purpose, granted_at FROM consents WHERE user_id = ? AND revoked_at IS NULL",
            (user_id,),
        ):
            user.consents[consent["purpose"]] = datetime.fromisoformat(consent["granted_at"])
        return user

    def revoke_consent(self, user_id: str, purpose: str) -> int:
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE consents SET revoked_at = ? WHERE user_id = ? AND purpose = ? "
                "AND revoked_at IS NULL",
                (utcnow().isoformat(), user_id, purpose),
            )
        self.record("consent.revoked", user_id=user_id, subject=purpose)
        return cursor.rowcount

    def save_profile(self, profile: FinancialProfile) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO financial_profiles (user_id, payload_json, risk_tolerance, "
                "risk_capacity, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET payload_json=excluded.payload_json, "
                "risk_tolerance=excluded.risk_tolerance, risk_capacity=excluded.risk_capacity, "
                "updated_at=excluded.updated_at",
                (profile.user_id, _json(_profile_dict(profile)), profile.risk_tolerance,
                 profile.risk_capacity, profile.updated_at.isoformat()),
            )
        self.record("profile.saved", user_id=profile.user_id, subject="financial_dna")

    def load_profile(self, user_id: str) -> FinancialProfile:
        row = self.connection.execute(
            "SELECT payload_json FROM financial_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise StoreError(f"no financial profile for {user_id!r}")
        return _profile_from(json.loads(row["payload_json"]))

    # -- policy ------------------------------------------------------------

    def save_policy(self, policy: InvestmentPolicy) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO policies (id, user_id, version, payload_json, edited_by_user, "
                "created_at) VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json, "
                "version=excluded.version, edited_by_user=excluded.edited_by_user",
                (policy.id, policy.user_id, policy.version, _json(policy.to_dict()),
                 int(policy.edited_by_user), policy.created_at.isoformat()),
            )
        self.record("policy.saved", user_id=policy.user_id, subject=policy.id,
                    payload={"version": policy.version})

    def load_policy(self, user_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT payload_json FROM policies WHERE user_id = ? ORDER BY version DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    # -- portfolio ---------------------------------------------------------

    def save_portfolio(self, portfolio: Portfolio) -> None:
        """Write accounts, assets, holdings, transactions and SIPs as one unit.

        Holdings are replaced rather than merged: a re-import is the user's
        current truth, and leaving an old position behind is how a sold fund
        haunts a dashboard for months.
        """
        with self.connection:
            for account in portfolio.accounts:
                self.connection.execute(
                    "INSERT INTO accounts (id, user_id, institution, account_type, currency, "
                    "masked, source, connected_at, last_synced_at, active) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "institution=excluded.institution, last_synced_at=excluded.last_synced_at, "
                    "active=excluded.active",
                    (account.id, portfolio.user_id, account.institution,
                     account.account_type.value, account.currency, account.identifier_masked,
                     account.source.value,
                     account.connected_at.isoformat() if account.connected_at else None,
                     account.last_synced_at.isoformat() if account.last_synced_at else None,
                     int(account.active)),
                )
            for asset in portfolio.assets.values():
                self.connection.execute(
                    "INSERT INTO assets (id, name, asset_type, isin, scheme_code, ticker, "
                    "payload_json) VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "name=excluded.name, payload_json=excluded.payload_json",
                    (asset.id, asset.name, asset.asset_type.value, asset.isin,
                     asset.scheme_code, asset.ticker, _json(_asset_dict(asset))),
                )
            self.connection.execute(
                "DELETE FROM holdings WHERE user_id = ?", (portfolio.user_id,)
            )
            for holding in portfolio.holdings:
                self.connection.execute(
                    "INSERT INTO holdings (id, user_id, account_id, asset_id, units, "
                    "average_cost, price, as_of, provenance_json) VALUES (?,?,?,?,?,?,?,?,?)",
                    (holding.id, portfolio.user_id, holding.account_id, holding.asset_id,
                     str(holding.units), str(holding.average_cost), str(holding.current_price),
                     holding.as_of.isoformat(), _json(holding.provenance.to_dict())),
                )
            for txn in portfolio.transactions:
                self.connection.execute(
                    "INSERT OR IGNORE INTO transactions (id, user_id, account_id, asset_id, "
                    "txn_type, trade_date, units, price, amount, fees, note, provenance_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (txn.id, portfolio.user_id, txn.account_id, txn.asset_id,
                     txn.txn_type.value, txn.trade_date.isoformat(), str(txn.units),
                     str(txn.price), str(txn.amount), str(txn.fees), txn.note,
                     _json(txn.provenance.to_dict())),
                )
            for sip in portfolio.sips:
                self.connection.execute(
                    "INSERT INTO sips (id, user_id, account_id, asset_id, amount, frequency, "
                    "start_date, end_date, goal_id, active) VALUES (?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET amount=excluded.amount, "
                    "active=excluded.active, goal_id=excluded.goal_id",
                    (sip.id, portfolio.user_id, sip.account_id, sip.asset_id, str(sip.amount),
                     sip.frequency.value, sip.start_date.isoformat(),
                     sip.end_date.isoformat() if sip.end_date else None, sip.goal_id,
                     int(sip.active)),
                )
            self.connection.execute(
                "INSERT INTO portfolio_state (user_id, cash, liabilities, updated_at) "
                "VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET cash=excluded.cash, "
                "liabilities=excluded.liabilities, updated_at=excluded.updated_at",
                (portfolio.user_id, str(portfolio.cash), str(portfolio.external_liabilities),
                 utcnow().isoformat()),
            )
        self.record(
            "portfolio.saved", user_id=portfolio.user_id, subject=portfolio.fingerprint(),
            payload={"holdings": len(portfolio.holdings),
                     "transactions": len(portfolio.transactions)},
        )

    def load_portfolio(self, user_id: str, *, as_of: date | None = None) -> Portfolio:
        assets: dict[str, Asset] = {}
        for row in self.connection.execute("SELECT * FROM assets"):
            assets[row["id"]] = _asset_from(json.loads(row["payload_json"]))
        accounts = [
            Account(
                id=r["id"], user_id=user_id, institution=r["institution"],
                account_type=AccountType(r["account_type"]), currency=r["currency"],
                identifier_masked=r["masked"], source=SourceKind(r["source"]),
                connected_at=datetime.fromisoformat(r["connected_at"]) if r["connected_at"] else None,
                last_synced_at=datetime.fromisoformat(r["last_synced_at"])
                if r["last_synced_at"] else None,
                active=bool(r["active"]),
            )
            for r in self.connection.execute(
                "SELECT * FROM accounts WHERE user_id = ?", (user_id,))
        ]
        holdings = [
            Holding(
                id=r["id"], account_id=r["account_id"], asset_id=r["asset_id"],
                units=quantity(r["units"]), average_cost=money(r["average_cost"]),
                current_price=money(r["price"]), as_of=date.fromisoformat(r["as_of"]),
                provenance=Provenance.from_dict(json.loads(r["provenance_json"])),
            )
            for r in self.connection.execute(
                "SELECT * FROM holdings WHERE user_id = ?", (user_id,))
        ]
        transactions = [
            Transaction(
                id=r["id"], account_id=r["account_id"], asset_id=r["asset_id"],
                txn_type=TxnType(r["txn_type"]), trade_date=date.fromisoformat(r["trade_date"]),
                units=quantity(r["units"]), price=money(r["price"]), amount=money(r["amount"]),
                fees=money(r["fees"]),
                provenance=Provenance.from_dict(json.loads(r["provenance_json"])),
                note=r["note"],
            )
            for r in self.connection.execute(
                "SELECT * FROM transactions WHERE user_id = ?", (user_id,))
        ]
        sips = [
            SIP(
                id=r["id"], user_id=user_id, account_id=r["account_id"], asset_id=r["asset_id"],
                amount=money(r["amount"]), frequency=Frequency(r["frequency"]),
                start_date=date.fromisoformat(r["start_date"]),
                end_date=date.fromisoformat(r["end_date"]) if r["end_date"] else None,
                goal_id=r["goal_id"], active=bool(r["active"]),
            )
            for r in self.connection.execute("SELECT * FROM sips WHERE user_id = ?", (user_id,))
        ]
        state = self.connection.execute(
            "SELECT cash, liabilities FROM portfolio_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        return Portfolio(
            user_id=user_id,
            as_of=as_of or max((h.as_of for h in holdings), default=date.today()),
            accounts=accounts,
            assets={a.id: a for a in assets.values() if a.id in {h.asset_id for h in holdings}
                    or a.id in {t.asset_id for t in transactions}},
            holdings=holdings, transactions=transactions, sips=sips,
            cash=money(state["cash"]) if state else money(0),
            external_liabilities=money(state["liabilities"]) if state else money(0),
        )

    # -- goals -------------------------------------------------------------

    def save_goals(self, goals: Iterable[Goal]) -> None:
        with self.connection:
            for goal in goals:
                self.connection.execute(
                    "INSERT INTO goals (id, user_id, name, goal_type, target_amount, "
                    "target_date, priority, payload_json, created_at) VALUES (?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
                    "target_amount=excluded.target_amount, target_date=excluded.target_date, "
                    "priority=excluded.priority, payload_json=excluded.payload_json",
                    (goal.id, goal.user_id, goal.name, goal.goal_type.value,
                     str(goal.target_amount), goal.target_date.isoformat(), goal.priority,
                     _json(_goal_dict(goal)), goal.created_at.isoformat()),
                )

    def load_goals(self, user_id: str) -> list[Goal]:
        return [
            _goal_from(json.loads(r["payload_json"]))
            for r in self.connection.execute(
                "SELECT payload_json FROM goals WHERE user_id = ? ORDER BY priority, target_date",
                (user_id,))
        ]

    # -- analysis and recommendations --------------------------------------

    def save_snapshot(self, analysis: PortfolioAnalysis) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO snapshots (user_id, as_of, payload_json, fingerprint, created_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(user_id, as_of) DO UPDATE SET "
                "payload_json=excluded.payload_json, fingerprint=excluded.fingerprint",
                (analysis.user_id, analysis.as_of.isoformat(), _json(analysis.to_dict()),
                 analysis.fingerprint, utcnow().isoformat()),
            )
        self.record("analysis.saved", user_id=analysis.user_id, subject=analysis.fingerprint,
                    payload={"health": analysis.health.score})

    def load_snapshot(self, user_id: str, *, as_of: date | None = None) -> dict[str, Any] | None:
        if as_of:
            row = self.connection.execute(
                "SELECT payload_json FROM snapshots WHERE user_id = ? AND as_of = ?",
                (user_id, as_of.isoformat()),
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT payload_json FROM snapshots WHERE user_id = ? ORDER BY as_of DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def save_recommendations(self, result: RecommendationSet) -> None:
        with self.connection:
            for recommendation in list(result.recommendations) + list(result.suppressed):
                self.connection.execute(
                    "INSERT INTO recommendations (id, user_id, as_of, action, priority, "
                    "subject_id, rule_id, confidence, engine_version, fingerprint, suppressed, "
                    "payload_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json, "
                    "suppressed=excluded.suppressed",
                    (recommendation.id, recommendation.user_id, result.as_of.isoformat(),
                     recommendation.action.value, recommendation.priority.value,
                     recommendation.subject_id, recommendation.rule_id,
                     recommendation.confidence, recommendation.engine_version,
                     recommendation.portfolio_fingerprint, recommendation.suppressed_reason,
                     _json(recommendation.to_dict()), recommendation.created_at.isoformat()),
                )
        self.record(
            "recommendations.generated", user_id=result.user_id,
            subject=result.portfolio_fingerprint,
            payload={"shown": len(result.recommendations),
                     "suppressed": len(result.suppressed),
                     "rules": result.rules_fired},
        )

    def load_recommendations(self, user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return [
            json.loads(r["payload_json"])
            for r in self.connection.execute(
                "SELECT payload_json FROM recommendations WHERE user_id = ? AND suppressed = '' "
                "ORDER BY created_at DESC LIMIT ?", (user_id, limit))
        ]

    def record_decision(self, record: DecisionRecord) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO decisions (user_id, recommendation_id, outcome, note, decided_at) "
                "VALUES (?,?,?,?,?)",
                (record.user_id, record.recommendation_id, record.outcome.value,
                 record.note, record.decided_at.isoformat()),
            )
        # A user's approval is the event a regulator asks about, so it is the
        # one audit entry that must never be batched away.
        self.record("decision.recorded", user_id=record.user_id,
                    subject=record.recommendation_id,
                    payload={"outcome": record.outcome.value, "note": record.note})

    def decision_history(self, user_id: str, *, limit: int = 100) -> list[DecisionRecord]:
        return [
            DecisionRecord(
                id=str(r["id"]), user_id=r["user_id"], recommendation_id=r["recommendation_id"],
                outcome=DecisionOutcome(r["outcome"]), note=r["note"],
                decided_at=datetime.fromisoformat(r["decided_at"]),
            )
            for r in self.connection.execute(
                "SELECT * FROM decisions WHERE user_id = ? ORDER BY decided_at DESC LIMIT ?",
                (user_id, limit))
        ]

    # -- alerts ------------------------------------------------------------

    def save_alerts(self, alerts: Iterable[Alert]) -> int:
        count = 0
        with self.connection:
            for alert in alerts:
                self.connection.execute(
                    "INSERT INTO alerts (id, user_id, alert_type, severity, title, body, "
                    "dedupe_key, status, useful, snooze_until, recommendation_id, created_at, "
                    "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(user_id, dedupe_key) DO UPDATE SET status=excluded.status, "
                    "useful=excluded.useful, snooze_until=excluded.snooze_until, "
                    "updated_at=excluded.updated_at",
                    (alert.id, alert.user_id, alert.alert_type, alert.severity.value,
                     alert.title, alert.body, alert.dedupe_key, alert.status.value,
                     None if alert.useful is None else int(alert.useful),
                     alert.snooze_until.isoformat() if alert.snooze_until else None,
                     alert.recommendation_id, alert.created_at.isoformat(),
                     alert.updated_at.isoformat()),
                )
                count += 1
        return count

    def load_alerts(self, user_id: str, *, include_closed: bool = False) -> list[Alert]:
        query = "SELECT * FROM alerts WHERE user_id = ?"
        if not include_closed:
            query += " AND status IN ('open','snoozed')"
        query += " ORDER BY created_at DESC"
        return [
            Alert(
                id=r["id"], user_id=r["user_id"], alert_type=r["alert_type"],
                severity=Priority(r["severity"]), title=r["title"], body=r["body"],
                dedupe_key=r["dedupe_key"], status=AlertStatus(r["status"]),
                created_at=datetime.fromisoformat(r["created_at"]),
                updated_at=datetime.fromisoformat(r["updated_at"]),
                snooze_until=datetime.fromisoformat(r["snooze_until"])
                if r["snooze_until"] else None,
                recommendation_id=r["recommendation_id"],
                useful=None if r["useful"] is None else bool(r["useful"]),
            )
            for r in self.connection.execute(query, (user_id,))
        ]

    # -- conversation ------------------------------------------------------

    def save_message(
        self, conversation: Conversation, role: str, content: str, *,
        fact_ids: Sequence[str] = (), prompt_id: str = "", model: str = "",
        grounded: bool | None = None,
    ) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO conversations (id, user_id, created_at) VALUES (?,?,?)",
                (conversation.id, conversation.user_id, conversation.created_at.isoformat()),
            )
            self.connection.execute(
                "INSERT INTO messages (conversation_id, role, content, fact_ids, prompt_id, "
                "model, grounded, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (conversation.id, role, content, ",".join(fact_ids), prompt_id, model,
                 None if grounded is None else int(grounded), utcnow().isoformat()),
            )

    def load_conversation(self, conversation_id: str) -> Conversation | None:
        row = self.connection.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row is None:
            return None
        conversation = Conversation(
            id=row["id"], user_id=row["user_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        for message in self.connection.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,)
        ):
            conversation.add(
                message["role"], message["content"],
                fact_ids=tuple(f for f in message["fact_ids"].split(",") if f),
            )
        return conversation

    # -- documents ---------------------------------------------------------

    @property
    def box(self) -> SealedBox:
        if self._box is None:
            raise StoreError(
                "no encryption key configured; set AICIO_SECRET_KEY and AICIO_SECRET_SALT "
                "before storing documents or tokens"
            )
        return self._box

    def store_document(
        self, user_id: str, filename: str, data: bytes, *, media_type: str = "",
        retain_days: int = 2555,
    ) -> str:
        """Seal and store an uploaded statement.

        Default retention is seven years, which is the horizon Indian tax
        records are ordinarily kept to. It is a parameter because that is a
        policy decision, not a technical one.
        """
        sealed = self.box.seal(data)
        digest = hashlib.sha256(data).hexdigest()
        document_id = "doc_" + digest[:16]
        retain_until = (utcnow() + timedelta(days=retain_days)).date().isoformat()
        try:
            with self.connection:
                self.connection.execute(
                    "INSERT OR REPLACE INTO documents (id, user_id, filename, media_type, "
                    "sealed, key_id, sha256, bytes, retain_until, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (document_id, user_id, filename, media_type, sealed,
                     self.box.fingerprint(), digest, len(data), retain_until,
                     utcnow().isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise StoreError(
                f"cannot store a document for unknown user {user_id!r}: {exc}"
            ) from exc
        self.record("document.stored", user_id=user_id, subject=document_id,
                    payload={"filename": filename, "bytes": len(data), "sha256": digest})
        return document_id

    def read_document(self, document_id: str) -> tuple[str, bytes]:
        row = self.connection.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if row is None:
            raise StoreError(f"no document {document_id!r}")
        data = self.box.open(row["sealed"])
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise StoreError("document failed its integrity check after decryption")
        self.record("document.read", user_id=row["user_id"], subject=document_id)
        return row["filename"], data

    def delete_user_data(self, user_id: str) -> dict[str, int]:
        """Erasure. Everything the user owns, in one call.

        The audit log is not deleted: it records that data existed and was
        erased, holds no financial detail, and is what proves the erasure
        happened. That distinction is what makes the right to erasure and the
        duty to keep records compatible.
        """
        counts: dict[str, int] = {}
        tables = ["messages", "conversations", "documents", "connector_tokens", "alerts",
                  "decisions", "recommendations", "snapshots", "portfolio_state", "sips",
                  "transactions", "holdings", "accounts", "goals", "policies",
                  "financial_profiles", "consents", "users"]
        with self.connection:
            for table in tables:
                if table == "messages":
                    cursor = self.connection.execute(
                        "DELETE FROM messages WHERE conversation_id IN "
                        "(SELECT id FROM conversations WHERE user_id = ?)", (user_id,))
                elif table == "users":
                    # The users table is keyed on `id`; every other table
                    # references it as `user_id`.
                    cursor = self.connection.execute(
                        "DELETE FROM users WHERE id = ?", (user_id,))
                else:
                    cursor = self.connection.execute(
                        f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
                counts[table] = cursor.rowcount
        self.record("user.erased", user_id=user_id, subject=user_id, payload=counts)
        return counts

    # -- health ------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        intact, bad = self.verify_chain()
        counts = {
            table: self.connection.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
            for table in ("users", "holdings", "transactions", "recommendations", "alerts",
                          "audit_events", "documents")
        }
        return {
            "database": self.path, "schema_version": self.version,
            "chain_intact": intact, "first_bad_event": bad, "counts": counts,
            "encryption": "configured" if self._box else "not configured",
        }


class EncryptedTokenVault(TokenVault):
    """Connector tokens, sealed under their own purpose.

    Separate from documents so that a sealed statement can never be swapped
    into a token slot: the AEAD associated data differs, so the tag check fails
    rather than the substitution succeeding.
    """

    def __init__(self, store: Store, box: SealedBox | None = None) -> None:
        self.store = store
        self.box = box or SealedBox(store.box.key, "connector_tokens")

    def get(self, user_id: str, connector: str) -> dict[str, Any] | None:
        row = self.store.connection.execute(
            "SELECT sealed FROM connector_tokens WHERE user_id = ? AND connector = ?",
            (user_id, connector),
        ).fetchone()
        if row is None:
            return None
        try:
            return self.box.open_json(row["sealed"])
        except CryptoError as exc:
            raise StoreError(
                f"stored token for {connector} could not be opened: {exc}. "
                "Ask the user to reconnect the account."
            ) from exc

    def put(self, user_id: str, connector: str, token: dict[str, Any]) -> None:
        with self.store.connection:
            self.store.connection.execute(
                "INSERT INTO connector_tokens (user_id, connector, sealed, key_id, updated_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(user_id, connector) DO UPDATE SET "
                "sealed=excluded.sealed, key_id=excluded.key_id, updated_at=excluded.updated_at",
                (user_id, connector, self.box.seal_json(token), self.box.fingerprint(),
                 utcnow().isoformat()),
            )
        # The token itself is never in the payload -- only that one was stored.
        self.store.record("connector.token_stored", user_id=user_id, subject=connector)

    def drop(self, user_id: str, connector: str) -> None:
        with self.store.connection:
            self.store.connection.execute(
                "DELETE FROM connector_tokens WHERE user_id = ? AND connector = ?",
                (user_id, connector),
            )
        self.store.record("connector.token_removed", user_id=user_id, subject=connector)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _profile_dict(profile: FinancialProfile) -> dict[str, Any]:
    data = {k: v for k, v in profile.__dict__.items() if k != "provenance"}
    data["provenance"] = profile.provenance.to_dict()
    return data


def _profile_from(raw: dict[str, Any]) -> FinancialProfile:
    return FinancialProfile(
        user_id=raw["user_id"], age_band=raw.get("age_band", "35-44"),
        dependents=int(raw.get("dependents", 0)),
        annual_income=money(raw.get("annual_income", 0)),
        annual_expenses=money(raw.get("annual_expenses", 0)),
        monthly_surplus=money(raw.get("monthly_surplus", 0)),
        liabilities=money(raw.get("liabilities", 0)),
        emergency_reserve=money(raw.get("emergency_reserve", 0)),
        risk_tolerance=int(raw["risk_tolerance"]), risk_capacity=int(raw["risk_capacity"]),
        income_stability=raw.get("income_stability", "stable"),
        tax_regime=raw.get("tax_regime", "new"),
        marginal_tax_rate=float(raw.get("marginal_tax_rate", 0.3)),
        horizon_years=int(raw.get("horizon_years", 20)),
        liquidity_need_months=int(raw.get("liquidity_need_months", 6)),
        excluded_sectors=tuple(raw.get("excluded_sectors", ())),
        preferred_geographies=tuple(raw.get("preferred_geographies", ("IN",))),
        max_single_holding_pct=float(raw.get("max_single_holding_pct", 0.1)),
        max_sector_pct=float(raw.get("max_sector_pct", 0.3)),
        updated_at=datetime.fromisoformat(raw["updated_at"]) if raw.get("updated_at") else utcnow(),
        provenance=Provenance.from_dict(raw["provenance"]) if raw.get("provenance")
        else Provenance(SourceKind.USER_INPUT, "user", utcnow()),
    )


def _asset_dict(asset: Asset) -> dict[str, Any]:
    data = dict(asset.__dict__)
    data["asset_type"] = asset.asset_type.value
    return data


def _asset_from(raw: dict[str, Any]) -> Asset:
    return Asset(
        id=raw["id"], name=raw["name"], asset_type=AssetType(raw["asset_type"]),
        isin=raw.get("isin", ""), scheme_code=raw.get("scheme_code", ""),
        ticker=raw.get("ticker", ""), issuer=raw.get("issuer", ""),
        currency=raw.get("currency", "INR"), category=raw.get("category", ""),
        benchmark=raw.get("benchmark", ""), sector=raw.get("sector", ""),
        geography=raw.get("geography", "IN"), expense_ratio=raw.get("expense_ratio"),
        aum_cr=raw.get("aum_cr"),
        holdings_lookthrough={k: float(v) for k, v in (raw.get("holdings_lookthrough") or {}).items()},
        equity_share=raw.get("equity_share"), metadata=raw.get("metadata") or {},
    )


def _goal_dict(goal: Goal) -> dict[str, Any]:
    data = dict(goal.__dict__)
    data["goal_type"] = goal.goal_type.value
    return data


def _goal_from(raw: dict[str, Any]) -> Goal:
    return Goal(
        id=raw["id"], user_id=raw["user_id"], name=raw["name"],
        goal_type=GoalType(raw["goal_type"]), target_amount=money(raw["target_amount"]),
        target_date=date.fromisoformat(raw["target_date"]), priority=int(raw.get("priority", 3)),
        current_funding=money(raw.get("current_funding", 0)),
        monthly_contribution=money(raw.get("monthly_contribution", 0)),
        inflation_rate=float(raw.get("inflation_rate", 0.06)),
        flexible=bool(raw.get("flexible", True)),
        linked_account_ids=tuple(raw.get("linked_account_ids", ())),
        assumptions=raw.get("assumptions") or {},
        created_at=datetime.fromisoformat(raw["created_at"]) if raw.get("created_at") else utcnow(),
    )
