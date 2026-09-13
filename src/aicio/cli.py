"""Command line interface.

The whole product, runnable in one command with no configuration:

    python -m aicio demo

That is not a convenience. A wealth product that cannot be run end to end by
whoever picks up the repository next is a product whose behaviour nobody can
check, and the parts of this system that most need checking -- the decision
engine and the grounding gate -- are the ones a screenshot cannot show.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from . import ENGINE_VERSION, __version__
from .money import format_money

DEFAULT_DB = Path(os.environ.get("AICIO_DB", "aicio.db"))


def _store(path: Path, actor: str = "cli"):
    from .crypto import CryptoError, SealedBox
    from .store import Store

    try:
        box = SealedBox.from_environment("documents")
    except CryptoError:
        # No key configured: everything works except document and token
        # storage, which fail loudly when reached rather than silently writing
        # plaintext.
        box = None
    return Store(path, actor=actor, box=box)


def _bundle_into(store, *, as_of: date | None = None) -> dict[str, Any]:
    from .seed import demo_bundle

    bundle = demo_bundle(as_of=as_of) if as_of else demo_bundle()
    store.save_user(bundle["user"])
    store.save_profile(bundle["profile"])
    store.save_policy(bundle["policy"])
    store.save_goals(bundle["goals"])
    store.save_portfolio(bundle["portfolio"])
    return bundle


def cmd_demo(args: argparse.Namespace) -> int:
    """Seed, analyse, decide, alert, report and answer -- in one pass."""
    from .ai import AIBanker
    from .alerts import detect, filter_alerts
    from .analysis import analyse
    from .decisions import generate
    from .reports import daily_brief

    store = _store(Path(args.db))
    bundle = _bundle_into(store)
    analysis = analyse(
        bundle["portfolio"], bundle["profile"], bundle["policy"], bundle["goals"],
        today=bundle["as_of"], quality=bundle["quality"], behaviour=bundle["behaviour"],
    )
    store.save_snapshot(analysis)
    recommendations = generate(analysis, today=bundle["as_of"], limit=args.limit)
    store.save_recommendations(recommendations)
    alerts = filter_alerts(detect(analysis, recommendations), user=bundle["user"])
    store.save_alerts(alerts.alerts)

    print(daily_brief(analysis, recommendations, alerts.alerts).render())
    print("ACTION CENTRE")
    print("-" * 13)
    for item in recommendations.recommendations:
        print(f"  [{item.priority.value:<8}] {item.action.value:<13} {item.headline}")
        for reason in item.reasons[:2]:
            print(f"                             · {reason}")
        if item.tax_impact:
            print(f"                             tax: {item.tax_impact}")
        print()
    if recommendations.suppressed:
        print("Held back:")
        for item in recommendations.suppressed:
            print(f"  {item.rule_id}: {item.suppressed_reason}")
        print()

    banker = AIBanker(analysis, recommendations)
    print(f"AI BANKER  (provider: {banker.gateway.name}/{banker.gateway.model})")
    print("-" * 13)
    for question in args.ask or [
        "How am I doing?", "What do I actually own?", "What should I do now?",
    ]:
        reply = banker.ask(question)
        print(f"  Q: {question}")
        print(f"  A: {reply.text}")
        if reply.grounding:
            print(f"     grounded: {reply.grounding.grounded}")
        print()
    store.close()
    return 0


def cmd_analyse(args: argparse.Namespace) -> int:
    from .api import dispatch

    store = _store(Path(args.db))
    status, payload = dispatch(store, "GET", f"/api/users/{args.user}/analysis", {}, {})
    print(json.dumps(payload, indent=2, default=str))
    store.close()
    return 0 if status == 200 else 1


def cmd_import(args: argparse.Namespace) -> int:
    from .ingest import parse_statement
    from .ingest.normalize import normalise

    path = Path(args.file)
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    result = parse_statement(path, user_id=args.user)
    print(f"Parsed {path.name} as {result.source_format}")
    print(f"  holdings     {len(result.holdings)}")
    print(f"  transactions {len(result.transactions)}")
    print(f"  confidence   {result.confidence:.0%}")
    for note in result.notes:
        print(f"  note: {note}")
    for exception in result.exceptions:
        print(f"  ! line {exception.line_no}: {exception.reason}")
        if exception.suggestion:
            print(f"    suggestion: {exception.suggestion}")
    if args.dry_run:
        return 0

    store = _store(Path(args.db))
    existing = store.load_portfolio(args.user)
    portfolio, report = normalise(
        [result], user_id=args.user, existing=existing if existing.holdings else None,
    )
    store.save_portfolio(portfolio)
    if args.store_document:
        store.store_document(args.user, path.name, path.read_bytes())
    print(f"  merged: {len(portfolio.holdings)} holdings, "
          f"{format_money(portfolio.market_value)}")
    if report.duplicate_holdings:
        print(f"  {len(report.duplicate_holdings)} duplicate position(s) reconciled")
    store.close()
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    from .ai import AIBanker
    from .api import _context

    store = _store(Path(args.db))
    analysis, recommendations, *_ = _context(store, args.user)
    banker = AIBanker(analysis, recommendations)
    reply = banker.ask(" ".join(args.question))
    print(reply.text)
    if args.verbose and reply.grounding:
        print()
        print(f"[{banker.gateway.name}/{banker.gateway.model} · prompt {reply.prompt_id} · "
              f"tools {', '.join(reply.tools_used) or 'none'} · "
              f"grounded {reply.grounding.grounded}]")
    store.close()
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from .api import dispatch

    store = _store(Path(args.db))
    status, payload = dispatch(store, "GET", f"/api/users/{args.user}/reports/{args.kind}", {}, {})
    if status != 200:
        print(payload.get("error", "failed"), file=sys.stderr)
        return 1
    print(payload["text"])
    store.close()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .api import serve

    store = _store(Path(args.db), actor="api")
    serve(store, host=args.host, port=args.port)
    store.close()
    return 0


def cmd_evals(args: argparse.Namespace) -> int:
    from .evals import run_suite

    report = run_suite(verbose=args.verbose)
    print(report.render())
    return 0 if report.passed else 1


def cmd_audit(args: argparse.Namespace) -> int:
    store = _store(Path(args.db))
    intact, bad = store.verify_chain()
    print(f"audit chain: {'intact' if intact else f'BROKEN at event {bad}'}")
    for event in store.audit_trail(args.user or "", limit=args.limit):
        print(f"  {event['created_at']}  {event['actor']:<10} {event['event']:<28} "
              f"{event['subject'][:32]}")
    store.close()
    return 0 if intact else 1


def cmd_connectors(args: argparse.Namespace) -> int:
    from .market.connectors import default_registry

    for connector in default_registry().available():
        missing = connector.get("missing_keys") or []
        state = connector["status"] + (f" (needs {', '.join(missing)})" if missing else "")
        print(f"  {connector['key']:<20} {connector['label']:<28} {connector['kind']:<11} "
              f"{connector['country']}  {state}")
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    from .web.build import build

    database = Path(args.db)
    if not database.exists() and not args.seed:
        # `aicio dashboard` with no database is the zero-configuration path:
        # build the demo rather than failing with an empty-portfolio error.
        print(f"  {database} does not exist; building the demo portfolio instead")
        database = None
    paths = build(Path(args.out), db=database, user=args.user, seed=args.seed)
    for path in paths:
        print(f"  wrote {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aicio",
        description="Personal AI CIO — an AI-native private investment banker.",
    )
    parser.add_argument("--version", action="version",
                        version=f"aicio {__version__} ({ENGINE_VERSION})")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="seed a demo portfolio and run the whole product")
    demo.add_argument("--limit", type=int, default=6)
    demo.add_argument("--ask", nargs="*", help="questions to put to the AI banker")
    demo.set_defaults(fn=cmd_demo)

    analyse_cmd = sub.add_parser("analyse", help="print the full deterministic analysis as JSON")
    analyse_cmd.add_argument("--user", default="user_demo")
    analyse_cmd.set_defaults(fn=cmd_analyse)

    import_cmd = sub.add_parser("import", help="parse and merge a statement")
    import_cmd.add_argument("file")
    import_cmd.add_argument("--user", default="user_demo")
    import_cmd.add_argument("--dry-run", action="store_true",
                            help="parse and report without saving")
    import_cmd.add_argument("--store-document", action="store_true",
                            help="also keep the encrypted original")
    import_cmd.set_defaults(fn=cmd_import)

    ask = sub.add_parser("ask", help="ask the AI banker a question")
    ask.add_argument("question", nargs="+")
    ask.add_argument("--user", default="user_demo")
    ask.add_argument("--verbose", "-v", action="store_true")
    ask.set_defaults(fn=cmd_ask)

    report = sub.add_parser("report", help="daily, weekly or monthly report")
    report.add_argument("kind", choices=["daily", "weekly", "monthly"])
    report.add_argument("--user", default="user_demo")
    report.set_defaults(fn=cmd_report)

    serve_cmd = sub.add_parser("serve", help="run the HTTP API")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8787)
    serve_cmd.set_defaults(fn=cmd_serve)

    evals = sub.add_parser("evals", help="run the financial AI evaluation suite")
    evals.add_argument("--verbose", "-v", action="store_true")
    evals.set_defaults(fn=cmd_evals)

    audit = sub.add_parser("audit", help="verify and print the audit chain")
    audit.add_argument("--user", default="")
    audit.add_argument("--limit", type=int, default=30)
    audit.set_defaults(fn=cmd_audit)

    connectors = sub.add_parser("connectors", help="list account integrations and their status")
    connectors.set_defaults(fn=cmd_connectors)

    dashboard = sub.add_parser("dashboard", help="build the static dashboard")
    dashboard.add_argument("--out", default="aicio_dashboard")
    dashboard.add_argument("--user", default="user_demo")
    dashboard.add_argument("--seed", action="store_true",
                           help="seed the demo portfolio first")
    dashboard.set_defaults(fn=cmd_dashboard)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
