#!/usr/bin/env python3
"""Draw every fleet-exposure chart (viz/fleet_exposure/fx_*.py) and check them.

Run:  cd /home/user/analytics-lab && python3 -I viz/fleet_exposure/run_all.py
Each chart script also runs on its own, e.g.  python3 -I viz/fleet_exposure/fx_02_rate_by_model.py

Writes (150 dpi PNG):
  viz/figures/fx_NN_<name>.png                pseudonymous (Customer NNN, S#####, models, types, categories)
  deliverables/fx_NN_<name>_REALNAMES.png     real customer names (gitignored; customer charts only)

Checks, after drawing:
  1. consistency: numbers drawn on the charts agree with the CSVs and fx_summary.json (style.check calls);
  2. definitions: every figure that uses a defined term carries its definition (DEFINED_TERMS below);
  3. privacy: no real account name or address (from the gitignored raw files) is drawn on a pseudonymous figure.
A failed definition or privacy check raises RuntimeError.
"""
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import fleet  # noqa: E402
import ipa_style as style  # noqa: E402

CHARTS = ['fx_01_fleet_vs_ticket_share', 'fx_02_rate_by_model', 'fx_03_rate_by_age', 'fx_04_rate_by_coverage',
          'fx_05_rate_by_telemetry_type', 'fx_06_busiest_customers', 'fx_07_customer_funnel',
          'fx_08_customer_concentration', 'fx_09_model_persistence', 'fx_10_customer_persistence',
          'fx_11_machine_persistence', 'fx_12_outlier_drivers']
PRIVATE_CHARTS = {'fx_06_busiest_customers', 'fx_07_customer_funnel', 'fx_10_customer_persistence',
                  'fx_12_outlier_drivers'}


def _flat(text):
    return ' '.join(text.split())


def defined_terms():
    """(term that triggers the check, lower-case) -> the definitions any one of which must be drawn."""
    S = fleet.summary()
    return {
        'installed machine-month': [fleet.installed_month_definition(S)],
        'unplanned': [fleet.unplanned_definition()],
        'expected': [fleet.expected_definition(S)],
        'str': [fleet.STR_DEFINITION],
        'standardised ticket ratio': [fleet.STR_DEFINITION],
        'age-standardised': [fleet.AGE_STD_DEFINITION],
        'consistent': [fleet.consistent_definition(S)],
        'flagged': [fleet.flagged_customer_definition(S), fleet.flagged_machine_definition(S),
                    fleet.consistent_definition(S)],
        'funnel': [fleet.funnel_definition(S)],
        'telemetry machine-month': [fleet.span_month_definition()],
    }


def definition_problems(texts):
    """Figures (path -> drawn strings) that use a term without its definition. Returns a list of messages."""
    terms = {k: [_flat(d) for d in v] for k, v in defined_terms().items()}
    every_def = {d for v in terms.values() for d in v}
    problems = []
    for path, strings in texts.items():
        flat = [_flat(s) for s in strings]
        others = [s for s in flat if s not in every_def]
        for term, defs in terms.items():
            if term == 'str':
                used = any(w.strip('(),.:;') == 'STR' for s in others for w in s.split())
            else:
                used = any(term in s.lower() for s in others)
            if used and not any(d in flat for d in defs):
                problems.append(f'{path.name}: uses "{term}" without its definition')
    return problems


def privacy_scan(paths):
    """Count real account names / addresses drawn on the given figures (None if the raw files are absent).
    Never prints the matched strings."""
    real = fleet.real_strings()
    if not real:
        return None
    return sum(sum(r in '\n'.join(style.TEXTS.get(p, [])) for r in real) for p in paths)


def main(out_dir=fleet.FIG_DIR, private=True):
    out_dir = Path(out_dir)
    print(f'Plots -> {out_dir} ...')
    style.CHECKS.clear()
    style.TEXTS.clear()
    written = []
    for name in CHARTS:
        module = importlib.import_module(name)
        if name in PRIVATE_CHARTS:
            written += module.plot(out_dir=out_dir, private=private)
        else:
            written += module.plot(out_dir=out_dir)

    n_ok = sum(ok for _, ok in style.CHECKS)
    print(f'  {len(written)} figures; consistency checks: {n_ok} pass, {len(style.CHECKS) - n_ok} warn')
    problems = definition_problems({p: style.TEXTS[p] for p in written})
    print(f'  definition check: {len(written) - len({m.split(":")[0] for m in problems})} of {len(written)} figures '
          f'define the terms they use ({"PASS" if not problems else "FAIL"})')
    for m in problems:
        print(f'    {m}')
    leaks = privacy_scan([p for p in written if p.parent == out_dir])
    if leaks is not None:
        print(f'  privacy scan of pseudonymous figures: {leaks} real name/address strings found '
              f'({"PASS" if leaks == 0 else "FAIL"})')
    if problems:
        raise RuntimeError('a figure uses a term it does not define')
    if leaks:
        raise RuntimeError('a pseudonymous figure contains a real customer name or address')
    if len(style.CHECKS) - n_ok:
        raise RuntimeError('a number drawn on a chart does not match the data')
    return written


if __name__ == '__main__':
    main()
