#!/usr/bin/env python3
"""Draw every chart in viz/: the high-ticket-machine charts and Zac's notebook figures, all in the IPA style, then
their slide versions.

Run:  cd /home/user/analytics-lab && python3 -I viz/run_all.py
Each section also runs on its own (viz/high_ticket/run_all.py, viz/zac_notebook/run_all.py, viz/slides/run_all.py),
and so does each chart script. Figures go to viz/figures/, slide versions and their speaker notes to
viz/figures/slides/; real-name variants go to deliverables/ (gitignored).
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'style'))
import ipa_style as style  # noqa: E402  (the module the sections draw with; its TEXTS feed the slides' title check)


def section(name):
    """Import <name>/run_all.py under a unique module name (every section has a run_all.py)."""
    spec = importlib.util.spec_from_file_location(f'{name}_run_all', HERE / name / 'run_all.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    written, texts = [], {}
    for name in ('high_ticket', 'zac_notebook'):
        written += section(name).main()
        texts.update({p.name: strings for p, strings in style.TEXTS.items()})
    written += section('slides').main(full_texts=texts)
    print(f'viz: {len(written)} figures in total')
    return written


if __name__ == '__main__':
    main()
    sys.exit(0)
