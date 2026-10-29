"""Loading and validation of the risk model."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

import yaml

LEVELS = ("low", "medium", "high")
FACTOR_TYPES = {"mapping", "country", "bands"}
ACTIONS = {"escalate", "reject"}


class ConfigError(ValueError):
    """Raised when the risk model file is inconsistent."""


def default_config_path() -> Path:
    return Path(str(resources.files("kyc_risk_scoring").joinpath("risk_model.yaml")))


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else default_config_path()
    with open(path, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    validate_config(config)
    return config


def validate_config(config: dict) -> None:
    if not isinstance(config, dict):
        raise ConfigError("Config must be a mapping.")
    for key in ("scale", "levels", "factors", "due_diligence"):
        if key not in config:
            raise ConfigError(f"Missing top-level key: {key}")

    smin, smax = config["scale"]["min"], config["scale"]["max"]
    if smax <= smin:
        raise ConfigError("scale.max must be greater than scale.min")

    levels = config["levels"]
    if not 0 < levels["medium"] < levels["high"] <= 100:
        raise ConfigError("levels must satisfy 0 < medium < high <= 100")

    factors = config["factors"]
    total = 0.0
    for name, f in factors.items():
        if f.get("type") not in FACTOR_TYPES:
            raise ConfigError(f"Factor '{name}': type must be one of {sorted(FACTOR_TYPES)}")
        weight = f.get("weight")
        if not isinstance(weight, (int, float)) or weight <= 0:
            raise ConfigError(f"Factor '{name}': weight must be a positive number")
        total += weight
        if f["type"] == "mapping":
            if "field" not in f or not f.get("scores"):
                raise ConfigError(f"Factor '{name}': mapping needs 'field' and 'scores'")
            scores = list(f["scores"].values()) + [f.get("default", smax), f.get("missing", smax)]
        elif f["type"] == "country":
            if not f.get("fields"):
                raise ConfigError(f"Factor '{name}': country needs 'fields'")
            scores = [3, 2, f.get("default", smin), f.get("missing", smax)]
        else:
            bands = f.get("bands") or []
            if "field" not in f or not bands or bands[-1].get("upto") is not None:
                raise ConfigError(f"Factor '{name}': bands need 'field' and a final band with upto: null")
            limits = [b["upto"] for b in bands[:-1]]
            if limits != sorted(limits):
                raise ConfigError(f"Factor '{name}': band limits must be ascending")
            scores = [b["score"] for b in bands] + [f.get("missing", smax)]
        if any(not smin <= s <= smax for s in scores):
            raise ConfigError(f"Factor '{name}': every score must be within {smin}..{smax}")
    if abs(total - 1.0) > 1e-6:
        raise ConfigError(f"Factor weights must sum to 1.0 (currently {total:.4f})")

    for ov in config.get("overrides", []):
        if "name" not in ov or "when" not in ov:
            raise ConfigError("Every override needs 'name' and 'when'")
        if ov.get("min_level") is None and ov.get("action") is None:
            raise ConfigError(f"Override '{ov['name']}' needs 'min_level' or 'action'")
        if ov.get("min_level") not in (None, *LEVELS):
            raise ConfigError(f"Override '{ov['name']}': invalid min_level")
        if ov.get("action") not in (None, *ACTIONS):
            raise ConfigError(f"Override '{ov['name']}': action must be one of {sorted(ACTIONS)}")
        when = ov["when"]
        if "factor" in when and when["factor"] not in factors:
            raise ConfigError(f"Override '{ov['name']}' refers to unknown factor '{when['factor']}'")

    for level in LEVELS:
        dd = config["due_diligence"].get(level)
        if not dd or not {"measures", "review_months"} <= set(dd):
            raise ConfigError(f"due_diligence.{level} needs 'measures' and 'review_months'")
