# kyc-risk-scoring

[![CI](https://github.com/ara-avetisyan-git/kyc-risk-scoring/actions/workflows/ci.yml/badge.svg)](https://github.com/ara-avetisyan-git/kyc-risk-scoring/actions)

A transparent, configurable **customer risk scoring** tool for KYC / CDD. Every score can be explained factor by factor,
and the whole risk model lives in one YAML file that a compliance officer can read, challenge and change without touching code.

## How it works

1. Each factor (country, customer type, product, channel, expected volume, business sector) gets a score from 1 to 3.
2. Scores are weighted and scaled to a **0-100 total**; thresholds give *low / medium / high*.
3. **Overrides** apply regardless of the number: a PEP is always high, a high-risk jurisdiction or sector forces high,
   a potential sanctions match is escalated to the MLRO, a confirmed match is rejected.
4. The result carries due-diligence measures (SDD / CDD / EDD), review frequency, approval level and a plain-language explanation.
5. Missing data is scored conservatively: a gap is a risk, not a free pass.

See [docs/MODEL.md](docs/MODEL.md) for the reasoning.

## Install and run

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q

kyc-score validate                                      # check the model (weights sum to 1, scores in range, ...)
kyc-score score --input examples/customers_synthetic.csv --output scored.csv
kyc-score explain --input examples/customers_synthetic.csv --customer-id K005
```

Use your own model with `--config my_model.yaml` (start from `src/kyc_risk_scoring/risk_model.yaml`).

## Input columns

`customer_id`, `customer_type`, `country_of_residence`, `nationality`, `product`, `channel`,
`expected_monthly_volume`, `business_sector`, `pep` (yes/no), `adverse_media` (yes/no),
`sanctions_status` (none / potential / confirmed). It pairs naturally with a name-screening step that produces `sanctions_status`.

## Limitations

- Country lists, weights and bands in the default model are **illustrative**; calibrate them to your own risk assessment.
- Demonstration project, not a production KYC system. Use synthetic data only in this repository.

## License

MIT. Author: Ara Avetisyan, AML/CFT compliance - [LinkedIn](https://www.linkedin.com/in/ara-avetisyan-1795802a)
