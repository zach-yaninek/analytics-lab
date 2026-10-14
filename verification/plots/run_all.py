#!/usr/bin/env python3
"""Draw every high-ticket-machine chart (verification/plots/htm_*.py) and check them.

Run:  cd /home/user/analytics-lab && python3 -I verification/plots/run_all.py
      (verification/high_ticket_machines.py calls main() at the end of a normal run.)
Each chart script also runs on its own, e.g.  python3 -I verification/plots/htm_03_observed_vs_expected.py

Writes (150 dpi PNG):
  verification/outputs/figures/htm_NN_<name>.png   pseudonymous (Customer NNN, M#####, models, categories)
  deliverables/htm_chronic_outliers_by_customer_REALNAMES.png   real customer names (gitignored; chart 7 only)

Checks, after drawing:
  1. consistency: values recomputed from the CSVs agree with htm_summary.json (style.check calls in the charts);
  2. definitions: every figure that mentions chronic outliers carries the chronic-outlier definition, and every
     figure that mentions workload-outsized machines carries a definition of it;
  3. privacy: no real customer name or serial (from the gitignored private tables) is drawn on a pseudonymous figure.
A failed definition or privacy check raises RuntimeError.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd  # noqa: E402

import style  # noqa: E402

CHARTS = ['htm_01_concentration_curve', 'htm_02_tickets_per_machine', 'htm_03_observed_vs_expected',
          'htm_04_model_mix', 'htm_05_episode_followups', 'htm_06_pre_ticket',
          'htm_07_chronic_outliers_by_customer', 'htm_08_chronic_categories_heatmap', 'htm_09_tickets_by_type',
          'htm_10_ticket_rate_by_machine_type']


def _flat(text):
    return ' '.join(text.split())


def definition_problems(texts):
    """Figures (path -> drawn strings) that use a term without its definition. Returns a list of messages."""
    chronic_def, outsized_def = _flat(style.chronic_definition()), _flat(style.outsized_definition())
    problems = []
    for path, strings in texts.items():
        flat = [_flat(s) for s in strings]
        others = [s.lower() for s in flat if s not in (chronic_def, outsized_def)]
        has_chronic_def, has_outsized_def = chronic_def in flat, outsized_def in flat
        if any('chronic' in s for s in others) and not has_chronic_def:
            problems.append(f'{path.name}: mentions chronic outliers without the definition')
        # The chronic-outlier definition defines workload-outsized inline, so either definition is enough.
        if any('outsized' in s for s in others) and not (has_outsized_def or has_chronic_def):
            problems.append(f'{path.name}: mentions workload-outsized machines without a definition')
    return problems


def privacy_scan(paths):
    """Count real customer names / serials (from the gitignored private tables) that appear in any text drawn on
    the given figures. Returns None when the private tables are absent. Never prints the matched strings."""
    files = [style.PRIVATE / 'htm_private_customer_names.csv', style.PRIVATE / 'htm_private_outsized_machines.csv']
    if not all(f.exists() for f in files):
        return None
    pn, pm = (pd.read_csv(f) for f in files)
    real = set(pn.real_account_name.dropna().astype(str))
    real |= set(pm.real_serial.dropna().astype(str)) | set(pm.customer_real_name.dropna().astype(str))
    for col in ('real_account_modal', 'real_accounts_all'):
        for v in pm[col].dropna().astype(str):
            real |= {x.strip() for x in v.split(' | ')}
    real = {r for r in real if len(r) >= 4 and not r.isdigit()}  # short / all-digit strings collide with counts
    return sum(sum(r in '\n'.join(style.TEXTS.get(p, [])) for r in real) for p in paths)


def main(out_dir=style.FIG_DIR, private=True):
    out_dir = Path(out_dir)
    print(f'Plots -> {out_dir} ...')
    style.CHECKS.clear()
    style.TEXTS.clear()
    written = []
    for name in CHARTS:
        module = importlib.import_module(name)
        if name == 'htm_07_chronic_outliers_by_customer':
            written += module.plot(out_dir=out_dir, private=private)
        else:
            written += module.plot(out_dir=out_dir)

    n_ok = sum(ok for _, ok in style.CHECKS)
    print(f'  {len(written)} figures; CSV-vs-summary consistency checks: {n_ok} pass, '
          f'{len(style.CHECKS) - n_ok} warn')
    problems = definition_problems({p: style.TEXTS[p] for p in written})
    print(f'  definition check: {len(written) - len({m.split(":")[0] for m in problems})} of {len(written)} figures '
          f'define the terms they use ({"PASS" if not problems else "FAIL"})')
    for m in problems:
        print(f'    {m}')
    leaks = privacy_scan([p for p in written if p.parent == out_dir])
    if leaks is not None:
        print(f'  privacy scan of pseudonymous figures: {leaks} real name/serial strings found '
              f'({"PASS" if leaks == 0 else "FAIL"})')
    if problems:
        raise RuntimeError('a figure uses a term it does not define')
    if leaks:
        raise RuntimeError('a pseudonymous figure contains a real customer name or serial')
    return written


if __name__ == '__main__':
    main()
