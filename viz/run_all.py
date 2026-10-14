#!/usr/bin/env python3
"""Draw every chart in viz/: the high-ticket-machine charts and Zac's notebook figures, all in the IPA style.

Run:  cd /home/user/analytics-lab && python3 -I viz/run_all.py
Each section also runs on its own (viz/high_ticket/run_all.py, viz/zac_notebook/run_all.py), and so does each chart
script. Figures go to viz/figures/; real-name variants go to deliverables/ (gitignored).
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def section(name):
    """Import <name>/run_all.py under a unique module name (both sections have a run_all.py)."""
    spec = importlib.util.spec_from_file_location(f'{name}_run_all', HERE / name / 'run_all.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    written = []
    for name in ('high_ticket', 'zac_notebook'):
        written += section(name).main()
    print(f'viz: {len(written)} figures in total')
    return written


if __name__ == '__main__':
    main()
    sys.exit(0)
