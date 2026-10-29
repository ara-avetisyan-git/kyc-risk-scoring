# Risk model notes

**Why a weighted additive model?** It is easy to explain to a regulator and to the business: each factor shows exactly
how many points it added. A black-box model would be harder to defend in an inspection.

**Why overrides on top of the score?** Some facts must not be averaged away. A PEP with a clean profile still needs
enhanced due diligence; a sanctions match is a decision, not a score. Overrides can only *raise* the level, never lower it.

**Why is missing data scored high?** Incomplete KYC is itself a risk signal and a common audit finding. Factors that
are not applicable to most customers (e.g. business sector for salaried individuals) use a low `missing` value in the model.

**Validation.** `kyc-score validate` rejects models whose weights do not sum to 1, whose scores leave the scale,
whose bands are not ascending, or whose overrides refer to unknown factors.

**Calibration (not included).** In practice the weights and thresholds should be tested against historical customers
and confirmed cases, approved by management, versioned, and reviewed at least annually.
