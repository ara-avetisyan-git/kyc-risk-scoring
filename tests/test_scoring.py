from pathlib import Path

import pytest
import yaml

from kyc_risk_scoring.cli import main
from kyc_risk_scoring.config import ConfigError, load_config, validate_config
from kyc_risk_scoring.scoring import read_customers, score_customer

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="module")
def config():
    return load_config()


@pytest.fixture(scope="module")
def results(config):
    return {r.customer_id: r for r in (score_customer(row, config) for row in read_customers(DATA / "customers.csv"))}


def test_default_model_is_valid(config):
    assert abs(sum(f["weight"] for f in config["factors"].values()) - 1.0) < 1e-9


def test_low_risk_domestic_customer(results):
    r = results["K001"]
    assert r.final_level == "low" and r.decision == "APPROVE" and r.measures == "SDD"
    assert r.score < 20


def test_high_risk_nationality_forces_high_level(results):
    r = results["K003"]
    assert "high_risk_country" in r.overrides
    assert r.final_level == "high" and r.decision == "APPROVE_AFTER_EDD"
    assert r.review_months == 12


def test_pep_is_always_high_even_with_low_score(results):
    r = results["K004"]
    assert r.calculated_level == "low"
    assert r.final_level == "high" and "pep" in r.overrides


def test_risky_legal_entity_scores_high(results):
    assert results["K005"].calculated_level == "medium"          # numeric score alone is not enough...
    assert results["K005"].final_level == "high"                 # ...the sector override raises it
    assert "high_risk_sector" in results["K005"].overrides
    assert results["K006"].final_level == "high"


def test_sanctions_overrides_set_the_decision(results):
    assert results["K007"].decision == "ESCALATE_TO_MLRO"
    assert results["K008"].decision == "REJECT"


def test_missing_data_is_treated_conservatively(results):
    assert results["K009"].final_level == "high"


def test_scores_stay_within_bounds(results):
    assert all(0 <= r.score <= 100 for r in results.values())


def test_explanation_mentions_drivers(results):
    text = results["K005"].explanation()
    assert "Main drivers" in text and "Raised to high" in text


def test_invalid_weights_are_rejected(config):
    broken = yaml.safe_load(yaml.safe_dump(config))
    broken["factors"]["country"]["weight"] = 0.5
    with pytest.raises(ConfigError, match="sum to 1.0"):
        validate_config(broken)


def test_unknown_override_factor_is_rejected(config):
    broken = yaml.safe_load(yaml.safe_dump(config))
    broken["overrides"].append({"name": "x", "when": {"factor": "nope", "score_at_least": 3}, "min_level": "high"})
    with pytest.raises(ConfigError, match="unknown factor"):
        validate_config(broken)


def test_cli_score_and_explain(tmp_path, capsys):
    out = tmp_path / "scored.csv"
    assert main(["score", "--input", str(DATA / "customers.csv"), "--output", str(out)]) == 0
    assert out.exists() and "Scored 10 customers" in capsys.readouterr().out
    assert main(["explain", "--input", str(DATA / "customers.csv"), "--customer-id", "K003"]) == 0
    assert main(["explain", "--input", str(DATA / "customers.csv"), "--customer-id", "ZZZ"]) == 1
    assert main(["validate"]) == 0
