#!/usr/bin/env python3
"""Draw every slide chart (viz/slides/sl_*.py) for the IPA meeting deck and report the number checks.

Run:  cd /home/user/analytics-lab && python3 -I viz/slides/run_all.py
Writes viz/figures/slides/sl_NN_<name>.png. Raises RuntimeError if any drawn number disagrees with the data.
"""
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import deck_style as S  # noqa: E402


def main(out_dir=S.FIG_DIR):
    written = []
    for path in sorted(HERE.glob('sl_[0-9][0-9]_*.py')):
        written += importlib.import_module(path.stem).plot(out_dir=out_dir)
    n_ok = sum(ok for _, ok in S.CHECKS)
    print(f'  {len(written)} slide charts; number checks: {n_ok} pass, {len(S.CHECKS) - n_ok} fail')
    if len(S.CHECKS) - n_ok:
        raise RuntimeError('a number drawn on a slide chart does not match the data')
    return written


if __name__ == '__main__':
    main()
