"""Command-line interface: validate the model, score customers, explain one result."""
from __future__ import annotations

import argparse
from collections import Counter

from .config import ConfigError, load_config
from .scoring import read_customers, score_customer, write_results


def _score_all(args):
    config = load_config(args.config)
    return [score_customer(row, config) for row in read_customers(args.input)]


def _cmd_validate(args) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"INVALID: {exc}")
        return 1
    print(f"OK: model v{config.get('version', '?')} with {len(config['factors'])} factors, "
          f"{len(config.get('overrides', []))} overrides.")
    return 0


def _cmd_score(args) -> int:
    results = _score_all(args)
    write_results(results, args.output)
    levels = Counter(r.final_level for r in results)
    decisions = Counter(r.decision for r in results)
    print(f"Scored {len(results)} customers -> {args.output}")
    print("  levels:   " + ", ".join(f"{k}={levels.get(k, 0)}" for k in ("low", "medium", "high")))
    print("  decisions: " + ", ".join(f"{k}={v}" for k, v in sorted(decisions.items())))
    return 0


def _cmd_explain(args) -> int:
    for result in _score_all(args):
        if result.customer_id == args.customer_id:
            print(f"Customer {result.customer_id}: {result.final_level.upper()} -> {result.decision}")
            for f in sorted(result.factors, key=lambda f: -f.contribution):
                print(f"  {f.name:<24} score {f.score:g}  +{f.contribution:5.1f} pts  ({f.detail})")
            print(f"  {'TOTAL':<24} {result.score:.1f}/100")
            print(result.explanation())
            return 0
    print(f"Customer {args.customer_id} not found")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kyc-score", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="Check the risk model for errors")
    p.add_argument("--config")
    p.set_defaults(func=_cmd_validate)

    for name, func, help_ in (("score", _cmd_score, "Score a customer CSV"),
                              ("explain", _cmd_explain, "Show the factor breakdown of one customer")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--input", required=True)
        p.add_argument("--config")
        p.set_defaults(func=func)
        if name == "score":
            p.add_argument("--output", required=True)
        else:
            p.add_argument("--customer-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2
