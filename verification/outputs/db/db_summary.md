# DB-backed verification summary

Database `ipa_transaction_events_202508_202608.db`; workbook `IPA_CaseHistory_Aug 2025-Aug2026.xlsx`; expected values: Zac's notebook outputs (embedded constants). Generated 2026-10-12 19:46:43 UTC; elapsed 1316.4 s.

Checks: FAIL 1, INFO 6, PASS 65

## Steps

| step | status | seconds | note |
|---|---|---:|---|
| 0 | done | 141.8 | 4 tables, 3 indexes |
| 1 | done | 2.1 | 7183 devices, 695 hosts |
| 2 | done | 2.8 | 6113 matched tickets |
| 3 | done | 1.3 | mapping_summary [16, 31, 83] |
| pass | done | 1144.0 | one pass over transaction_events |
| 4 | done | 9.5 | 418188 groups, 118047569 rows |
| 4b | done | 1.2 | 30 pilot tickets |
| 5 | done | 7.4 | utc |
| 6 | done | 0.5 | ambiguous: utc, local_standard_no_dst |
| 7 | done | 0.0 | 155 differing rows; ingestion test skipped |
| 8 | done | 5.7 | utc (the recorded clock is UTC) |

## Decisions

- **clock_profiles_local**: utc
  - rule: Profiles of transaction_time_local hours by hospital zone. Machine-local wall clock: zone shifts vs Eastern ~0 and Standard-vs-DST shifts ~0. UTC: Central +1, Mountain +2, Pacific +3 (Arizona +3 in DST months, +2 in standard months) and Standard-vs-DST +1 in DST-observing zones. Fixed server wall clock: zone shifts like UTC, Standard-vs-DST 0 except no-DST zones. Tolerance +/-0.5 h; profiles need >= 5,000 rows.
- **clock_profiles_utc**: utc
  - rule: Profiles of transaction_time_utc hours by hospital zone. Machine-local wall clock: zone shifts vs Eastern ~0 and Standard-vs-DST shifts ~0. UTC: Central +1, Mountain +2, Pacific +3 (Arizona +3 in DST months, +2 in standard months) and Standard-vs-DST +1 in DST-observing zones. Fixed server wall clock: zone shifts like UTC, Standard-vs-DST 0 except no-DST zones. Tolerance +/-0.5 h; profiles need >= 5,000 rows.
- **dst_transition**: ambiguous: utc, local_standard_no_dst
  - rule: Hourly counts by local date and transaction_time_local hour, compared with the mean of the two adjacent days. A DST-observing local wall clock has an (almost) empty 02:00-02:59 on the spring-forward day and a ~2x 01:00-01:59 on the fall-back day, but not in Arizona/Hawaii/Saskatchewan. UTC or local standard time: neither occurs anywhere. A single fixed DST wall clock: both occur in every zone, including no-DST zones. Each zone is classified by a Poisson log-likelihood ratio (gap: rate 2% of adjacent days vs 100%; doubled: 200% vs 100%), |LLR| > 3 (~20:1); smaller |LLR| is "unclear" and not scored. For large counts the cut-offs are a ratio of ~0.25 (spring) and ~1.44 (fall).
- **ingestion_offsets**: not run: no ingestion/received timestamp column
- **clock_verdict**: utc (the recorded clock is UTC)
  - rule: intersection of the hypotheses consistent with every test that ran

## Checks (expected vs actual)

| step | check | expected | actual | status |
|---|---|---|---|---|
| 0 | ingestion/received timestamp column found | null | null | INFO |
| 0 | transaction_codes rows | 49 | 49 | PASS |
| 0 | database SHA-256 equals Zac's verified checksum | "7aa5d423bb381db2e1ab60c3dc95ca986e0e1140a4b41140ac3ea101382244d0" | "7aa5d423bb381db2e1ab60c3dc95ca986e0e1140a4b41140ac3ea101382244d0" | PASS |
| 1 | devices rows | 7183 | 7183 | PASS |
| 1 | device ids unique after clean() | true | true | PASS |
| 2 | record_quality.cases | 7471 | 7471 | PASS |
| 2 | record_quality.distinct_cases | 7471 | 7471 | PASS |
| 2 | record_quality.customers | 845 | 845 | PASS |
| 2 | record_quality.case_machines | 3773 | 3773 | PASS |
| 2 | record_quality.models | 31 | 31 | PASS |
| 2 | record_quality.first_opened | "2025-08-01 07:22:00" | "2025-08-01 07:22:00" | PASS |
| 2 | record_quality.last_opened | "2026-08-31 17:45:00" | "2026-08-31 17:45:00" | PASS |
| 2 | linkage.cases | 7471 | 7471 | PASS |
| 2 | linkage.matched_cases | 6113 | 6113 | PASS |
| 2 | linkage.matched_machines | 3041 | 3041 | PASS |
| 2 | linkage.matched_pct | 81.82 | 81.82 | PASS |
| 3 | model_type_mapping_head: printed rows reproduced | "15/15" | "15/15" | PASS |
| 3 | mapping_summary: Case models spanning more than one telemetry type | 16 | 16 | PASS |
| 3 | mapping_summary: Customers spanning more than one observed host | 31 | 31 | PASS |
| 3 | mapping_summary: Hosts linked to more than one case customer | 83 | 83 | PASS |
| 3 | pandas re-implementation equals Zac SQL mapping_summary | [16, 31, 83] | [16, 31, 83] | PASS |
| 4b | pilot extraction: per-ticket indexed queries == rows collected in the scan | true | true | PASS |
| 4 | telemetry_month_code groups | 418188 | 418188 | PASS |
| 4 | atomic transactions represented | 118047569 | 118047569 | PASS |
| 4 | rows with local string IS NOT utc string (clocks_differ) | 155 | 155 | PASS |
| 4 | missing_time (utc NULL or local date NULL) | 0 | 0 | PASS |
| 4 | rows with NULL local date | 0 | 0 | PASS |
| 4 | rows whose local date differs from the date part of the local time string | null | 0 | INFO |
| 4 | telemetry device ids absent from Zac serialmap (raw, unclean ids) | 0 | 0 | PASS |
| 4 | row total: month-code aggregation == hour aggregation (independent query) | 118047569 | 118047569 | PASS |
| 4 | every code total reconciles to an independent COUNT(*) GROUP BY code | true | true | PASS |
| 4 | coverage.first_transaction_date | "2025-08-01" | "2025-08-01" | PASS |
| 4 | coverage.last_transaction_date | "2026-08-28" | "2026-08-28" | PASS |
| 4 | coverage.represented_transactions | 118047569 | 118047569 | PASS |
| 4 | coverage.transacting_machines | 6951 | 6951 | PASS |
| 4 | bucket total: Door issue | 2212968 | 2212968 | PASS |
| 4 | bucket total: Electronics/software/comms | 45235 | 45235 | PASS |
| 4 | bucket total: Incomplete transaction | 473188 | 473188 | PASS |
| 4 | bucket total: Malformed | 6 | 6 | PASS |
| 4 | bucket total: Mechanical fault | 844284 | 844284 | PASS |
| 4 | bucket total: Operational status | 268236 | 268236 | PASS |
| 4 | bucket total: Stock-out | 3236592 | 3236592 | PASS |
| 4 | bucket total: Success | 110166059 | 110166059 | PASS |
| 4 | bucket total: Undefined | 4959 | 4959 | PASS |
| 4 | bucket total: User behavior | 796042 | 796042 | PASS |
| 4 | non-success transactions | 7881510 | 7881510 | PASS |
| 4 | non-success % | 6.68 | 6.68 | PASS |
| 4 | narrow fault transactions | 889519 | 889519 | PASS |
| 4 | narrow faults per 1,000 | 7.54 | 7.54 | PASS |
| 4 | narrow faults per 1,000 excluding code 05 | 7.43 | 7.43 | PASS |
| 4 | comparison_cohort: printed rows reproduced | "2/2" | "2/2" | PASS |
| 4 | ticket_cohort_exclusions: Included in comparison | 4916 | 4916 | PASS |
| 4 | ticket_cohort_exclusions: Missing host | 48 | 48 | PASS |
| 4 | ticket_cohort_exclusions: No device match | 1203 | 1203 | PASS |
| 4 | ticket_cohort_exclusions: No transactions in ticket month | 479 | 479 | PASS |
| 4 | ticket_cohort_exclusions: Shared/internal host | 18 | 18 | PASS |
| 4 | machine_type_rates: printed rows reproduced | "15/15" | "15/15" | PASS |
| 4 | rate numerator == directly linked eligible tickets | 4916 | 4916 | PASS |
| 4 | overall comparison rate per 100 active machine-months | 7.11 | 7.11 | PASS |
| 4 | monthly_comparison: printed rows reproduced | "12/12" | "12/12" | PASS |
| 4b | pilot non-success events extracted | 4736 | 4736 | PASS |
| 4b | pilot_scenario_summary: printed rows reproduced | "3/3" | "3/3" | PASS |
| 4b | pilot_offset0: printed rows reproduced | "30/30" | "30/30" | PASS |
| 4b | pilot_last_codes_head: printed rows reproduced | "15/15" | "0/15" | FAIL |
| 4b | pilot: tickets with >=3 non-success events / with a repeated code in the last three | {"tickets_with_3": 26, "with_repeated_codes": 25} | {"tickets_with_3": 26, "with_repeated_codes": 25} | PASS |
| 5 | hour profiles (transaction_time_local) | null | "utc" | INFO |
| 6 | DST-transition days | null | "ambiguous: utc, local_standard_no_dst" | INFO |
| 7 | rows with local IS NOT utc (dumped) | 155 | 155 | PASS |
| 7 | dumped rows == clocks_differ total from the aggregation | 155 | 155 | PASS |
| 7 | ingestion offsets | null | "not run: no ingestion/received timestamp column" | INFO |
| 8 | combined clock verdict (intersection of all clock tests) | null | "utc" | INFO |
| 8 | database file unchanged (size, mtime) | true | true | PASS |

## Output files

Public (pseudonymous): db_schema_master.csv, db_schema_columns.csv, db_schema_indexes.csv, db_schema_resolution.csv, db_value_formats.csv, db_sqlite_stat1.csv, db_row_counts.csv, db_devices_summary.csv, db_devices_machine_types.csv, db_devices_status.csv, db_devices_type_by_status.csv, db_codes_buckets.csv, db_record_quality.csv, db_linkage.csv, db_unmatched_profile.csv, db_unmatched_near_match.csv, db_model_type_mapping.csv, db_model_type_mapping_head_vs_expected.csv, db_customer_host_audit.csv, db_mapping_summary_variants.csv, db_host_level.csv, db_host_class_fleet_share.csv, db_accounts_per_host.csv, db_hosts_per_account.csv, db_query_plans.csv, db_telemetry_by_month.csv, db_telemetry_date_coverage.csv, db_telemetry_buckets.csv, db_telemetry_code_totals.csv, db_comparison_cohort.csv, db_comparison_cohort_vs_expected.csv, db_ticket_cohort_exclusions.csv, db_machine_type_rates.csv, db_machine_type_rates_vs_expected.csv, db_monthly_comparison.csv, db_monthly_comparison_vs_expected.csv, db_pilot_window_counts.csv, db_pilot_scenario_summary.csv, db_pilot_scenario_summary_vs_expected.csv, db_pilot_offset0_vs_expected.csv, db_pilot_last_distinct_codes.csv, db_pilot_last_codes_head_vs_expected.csv, db_clock_devices_by_zone.csv, db_clock_hypotheses_local.csv, db_clock_hypotheses_utc.csv, db_clock_hour_profiles.csv, db_clock_shift_estimates.csv, db_clock_hour_by_zone_month.csv, db_date_time_mismatch_by_zone_hour.csv, db_dst_transition_hourly.csv, db_dst_transition_metrics.csv, db_clock_differ_rows.csv, db_clock_differ_summary.csv

Private (--private, not for commit): 7 files.
