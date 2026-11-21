#!/usr/bin/env python3
"""Draw Zac's 10 notebook figures in the IPA style (viz/zac_notebook/zac_*.py) and check them.

Run:  cd /home/user/analytics-lab && python3 -I viz/zac_notebook/run_all.py
Each chart script also runs on its own, e.g.  python3 -I viz/zac_notebook/zac_04_issue_mix.py

Writes (150 dpi PNG):
  viz/figures/zac_NN_<name>.png                          pseudonymous (Customer NNN, models, categories)
  deliverables/zac_02_customer_workload_REALNAMES.png    real customer names (gitignored; needs the workbook)

Checks, after drawing:
  1. consistency: values stated on the charts agree with the same values recomputed from the tables (style.check);
  2. definitions: every figure that uses a defined term (unplanned tickets, active machine-months, repeat contact,
     provisional fault codes) draws its definition;
  3. privacy: no real account name (from the gitignored workbook) is drawn on a pseudonymous figure.
A failed definition or privacy check raises RuntimeError.
"""
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]  # python3 -I leaves the script directory off sys.path
import ipa_style as style  # noqa: E402
import zac_data  # noqa: E402

CHARTS = ['zac_01_missing_fields', 'zac_02_customer_workload', 'zac_03_model_workload', 'zac_04_issue_mix',
          'zac_05_machine_type_rates', 'zac_06_monthly_rates', 'zac_07_repeat_contact',
          'zac_08_customer_concentration', 'zac_09_model_issue_heatmap', 'zac_10_repeat_composition']


def _flat(text):
    return ' '.join(text.split())


def definition_problems(texts):
    """Figures (path -> drawn strings) that use a term without drawing its definition."""
    terms = [('unplanned', zac_data.UNPLANNED_DEFINITION), ('active machine-month', zac_data.ACTIVE_MONTH_DEFINITION),
             ('repeat', zac_data.REPEAT_DEFINITION), ('fault code', zac_data.fault_code_definition())]
    defs = {_flat(d) for _, d in terms}
    problems = []
    for path, strings in texts.items():
        flat = [_flat(s) for s in strings]
        others = [s.lower() for s in flat if s not in defs]
        for word, definition in terms:
            if any(word in s for s in others) and _flat(definition) not in flat:
                problems.append(f'{path.name}: uses "{word}" without its definition')
    return problems


def privacy_scan(paths):
    """Count real account names drawn on the given figures; None without the workbook. Never prints names."""
    real = zac_data.real_strings()
    if real is None:
        return None
    return sum(sum(r in '\n'.join(style.TEXTS.get(p, [])) for r in real) for p in paths)


def main(out_dir=zac_data.FIG_DIR, private=True):
    out_dir = Path(out_dir)
    print(f'Zac notebook plots -> {out_dir} ...')
    style.CHECKS.clear()
    style.TEXTS.clear()
    written = []
    for name in CHARTS:
        module = importlib.import_module(name)
        if name == 'zac_02_customer_workload':
            written += module.plot(out_dir=out_dir, private=private)
        else:
            written += module.plot(out_dir=out_dir)

    n_ok = sum(ok for _, ok in style.CHECKS)
    print(f'  {len(written)} figures; consistency checks: {n_ok} pass, {len(style.CHECKS) - n_ok} warn')
    problems = definition_problems({p: style.TEXTS[p] for p in written})
    print(f'  definition check: {"PASS" if not problems else "FAIL"}')
    for m in problems:
        print(f'    {m}')
    leaks = privacy_scan([p for p in written if p.parent == out_dir])
    if leaks is not None:
        print(f'  privacy scan of pseudonymous figures: {leaks} real names found ({"PASS" if leaks == 0 else "FAIL"})')
    if problems:
        raise RuntimeError('a figure uses a term it does not define')
    if leaks:
        raise RuntimeError('a pseudonymous figure contains a real customer name')
    return written


if __name__ == '__main__':
    main()
