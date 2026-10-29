"""Scoring engine: factor scores -> weighted 0-100 score -> level -> overrides -> decision."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .config import LEVELS


def _norm(value) -> str:
    return "" if value is None else str(value).strip().lower()


@dataclass(frozen=True)
class FactorResult:
    name: str
    score: float          # raw factor score on the model scale
    contribution: float   # points contributed to the 0-100 total
    detail: str


@dataclass
class ScoreResult:
    customer_id: str
    score: float
    calculated_level: str
    final_level: str
    measures: str
    review_months: int
    approval: str
    decision: str
    factors: list[FactorResult] = field(default_factory=list)
    overrides: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def explanation(self) -> str:
        drivers = sorted(self.factors, key=lambda f: -f.contribution)
        top = ", ".join(f"{f.name} {f.contribution:.1f}" for f in drivers[:3] if f.contribution > 0)
        text = f"Score {self.score:.1f} ({self.calculated_level})."
        if top:
            text += f" Main drivers: {top}."
        if self.final_level != self.calculated_level:
            text += f" Raised to {self.final_level} by override."
        if self.reasons:
            text += " " + " ".join(self.reasons)
        return text

    def to_row(self) -> dict:
        return {
            "customer_id": self.customer_id,
            "risk_score": round(self.score, 1),
            "calculated_level": self.calculated_level,
            "final_level": self.final_level,
            "due_diligence": self.measures,
            "review_months": self.review_months,
            "approval": self.approval,
            "decision": self.decision,
            "overrides": "; ".join(self.overrides),
            **{f"pts_{f.name}": round(f.contribution, 1) for f in self.factors},
            "explanation": self.explanation(),
        }


def _factor_score(name: str, cfg: dict, row: dict, scale: dict) -> tuple[float, str]:
    kind = cfg["type"]
    if kind == "country":
        values = [_norm(row.get(f)).upper() for f in cfg["fields"]]
        values = [v for v in values if v]
        if not values:
            return cfg.get("missing", scale["max"]), "country missing"
        high, medium = set(cfg.get("high", [])), set(cfg.get("medium", []))
        scores = [3 if v in high else 2 if v in medium else cfg.get("default", scale["min"]) for v in values]
        return max(scores), "countries=" + "/".join(values)

    raw = row.get(cfg["field"])
    if _norm(raw) == "":
        return cfg.get("missing", scale["max"]), f"{cfg['field']} missing"

    if kind == "mapping":
        key = _norm(raw)
        table = {_norm(k): v for k, v in cfg["scores"].items()}
        return table.get(key, cfg.get("default", scale["max"])), f"{cfg['field']}={key}"

    try:  # bands
        value = float(str(raw).replace(",", ""))
    except ValueError:
        return cfg.get("missing", scale["max"]), f"{cfg['field']} not numeric"
    for band in cfg["bands"]:
        if band["upto"] is None or value <= band["upto"]:
            return band["score"], f"{cfg['field']}={value:g}"
    return cfg["bands"][-1]["score"], f"{cfg['field']}={value:g}"


def _level_for(score: float, levels: dict) -> str:
    if score >= levels["high"]:
        return "high"
    if score >= levels["medium"]:
        return "medium"
    return "low"


def _override_hit(when: dict, row: dict, factor_scores: dict[str, float]) -> bool:
    if "field" in when:
        return _norm(row.get(when["field"])) == _norm(when["equals"])
    if "factor" in when:
        return factor_scores[when["factor"]] >= when["score_at_least"]
    return False


def score_customer(row: dict, config: dict) -> ScoreResult:
    scale = config["scale"]
    span = scale["max"] - scale["min"]
    factors: list[FactorResult] = []
    for name, cfg in config["factors"].items():
        raw, detail = _factor_score(name, cfg, row, scale)
        contribution = cfg["weight"] * (raw - scale["min"]) / span * 100
        factors.append(FactorResult(name, raw, contribution, detail))

    total = sum(f.contribution for f in factors)
    calculated = _level_for(total, config["levels"])
    final = calculated
    factor_scores = {f.name: f.score for f in factors}

    hit_names: list[str] = []
    reasons: list[str] = []
    actions: set[str] = set()
    for ov in config.get("overrides", []):
        if not _override_hit(ov["when"], row, factor_scores):
            continue
        hit_names.append(ov["name"])
        if ov.get("reason"):
            reasons.append(ov["reason"] + ".")
        if ov.get("min_level") and LEVELS.index(ov["min_level"]) > LEVELS.index(final):
            final = ov["min_level"]
        if ov.get("action"):
            actions.add(ov["action"])

    dd = config["due_diligence"][final]
    if "reject" in actions:
        decision = "REJECT"
    elif "escalate" in actions:
        decision = "ESCALATE_TO_MLRO"
    elif final == "high":
        decision = "APPROVE_AFTER_EDD"
    else:
        decision = "APPROVE"

    return ScoreResult(
        customer_id=str(row.get("customer_id", "")).strip(),
        score=total,
        calculated_level=calculated,
        final_level=final,
        measures=dd["measures"],
        review_months=dd["review_months"],
        approval=dd.get("approval", ""),
        decision=decision,
        factors=factors,
        overrides=hit_names,
        reasons=reasons,
    )


def read_customers(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if "customer_id" not in (reader.fieldnames or []):
            raise ValueError("Input file must contain a 'customer_id' column")
        return list(reader)


def write_results(results: list[ScoreResult], path: str | Path) -> None:
    rows = [r.to_row() for r in results]
    if not rows:
        raise ValueError("No customers to write")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
