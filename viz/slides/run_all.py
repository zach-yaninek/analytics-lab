#!/usr/bin/env python3
"""Draw every slide chart (viz/slides/sl_*.py) for the IPA meeting deck and report the number checks.

The follow-up charts (sl_18 on, docs/09) print their definitions on the image: each declares TERMS (keys of
followup_terms.terms()), and the definitions check confirms every declared definition was given to
deck_style.definitions() word for word and drawn in full.

Run:  cd /home/user/analytics-lab && python3 -I viz/slides/run_all.py
Writes viz/figures/slides/sl_NN_<name>.png. Raises RuntimeError if any drawn number disagrees with the data or a
follow-up chart leaves out a definition.
"""
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import deck_style as S  # noqa: E402


FIRST_WITH_DEFINITIONS = 18


def definitions_check(module, pngs):
    """Every follow-up chart declares TERMS and prints each definition (term and text) in full."""
    number = int(module.__name__.split('_')[1])
    keys = getattr(module, 'TERMS', None)
    if number < FIRST_WITH_DEFINITIONS:
        return
    S.check(f'{module.__name__}: declares the terms it defines', 1, int(bool(keys)))
    import followup_terms as T

    def norm(x):
        return ' '.join(x.split())
    for png in pngs:
        given, drawn = S.DEFS.get(Path(png), ([], ''))
        for term, text in T.items(keys or []):
            S.check(f'{Path(png).stem}: prints the definition of "{term}"', 1,
                    int((term, text) in given and norm(f'{term}: {text}') in norm(drawn)))


def main(out_dir=S.FIG_DIR):
    written = []
    for path in sorted(HERE.glob('sl_[0-9][0-9]_*.py')):
        module = importlib.import_module(path.stem)
        pngs = module.plot(out_dir=out_dir)
        definitions_check(module, pngs)
        written += pngs
    n_ok = sum(ok for _, ok in S.CHECKS)
    print(f'  {len(written)} slide charts; number checks: {n_ok} pass, {len(S.CHECKS) - n_ok} fail')
    if len(S.CHECKS) - n_ok:
        raise RuntimeError('a number drawn on a slide chart does not match the data, or a definition is missing')
    return written


if __name__ == '__main__':
    main()
