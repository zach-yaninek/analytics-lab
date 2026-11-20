# Changelog

Any change to a definition (the copies in `ipa_trends/definitions/`, the request-type reference, the exposure or
interval rules) bumps the method version and must be followed by `ipa-trends reconcile` on the original files.

## 1.0.0 (2026-11)

First release for IPA's Product & Customer Service analytics team.
- Unplanned tickets per 100 installed machine-months by request group and Category, per reporting period, by
  install cohort, product family and model.
- The rerun frequency is a free parameter: any whole number of months (quarterly by default, monthly as the
  alternative).
- Conservative time-trend call-outs (crude rate ratios adjusted for business days; account bootstrap plus
  between-period variance; one Benjamini-Hochberg correction; a 20% practical threshold; survivorship check;
  data-quality gates) and install-cohort contrasts (crude and same-age ratios must agree).
- Outputs: CSV tables with a stable dashboard key, PNG charts, a self-contained HTML report, a PDF report, email
  text and a manifest; a privacy scan of everything before publication.
- Reconciliation against the committed analysis (fleet, age, family, model, request-type, band, halves, monthly,
  install-cohort and install-year numbers).
