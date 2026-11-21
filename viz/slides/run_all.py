#!/usr/bin/env python3
"""Draw every slide chart (viz/slides/sl_*.py) for the IPA meeting deck and report the number checks.

The follow-up charts (sl_18 on, docs/09) print their definitions on the image: each declares TERMS (keys of
followup_terms.terms()), and the definitions check confirms every declared definition was given to
deck_style.definitions() word for word and drawn in full.

The customer charts (those whose plot() takes private: sl_06, sl_07) also draw a real-name variant when private=True
and the gitignored name table exists. The privacy scan then counts the real names (viz/deliverables/names.py) drawn on
the pseudonymous charts in out_dir; it prints the count, never a name.

Run:  cd /home/user/analytics-lab && python3 -I viz/slides/run_all.py
Writes viz/figures/slides/sl_NN_<name>.png and, for the customer charts, deliverables/slides/sl_NN_<name>_REALNAMES.png
(gitignored; never commit). Raises RuntimeError if any drawn number disagrees with the data, a follow-up chart leaves
out a definition, or a pseudonymous chart shows a real name.
"""
import importlib
import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'deliverables')]  # python3 -I leaves the script directory off sys.path
import deck_style as S  # noqa: E402
import names  # noqa: E402


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


def privacy_scan(paths):
    """How many real customer names are drawn on the given charts (whitespace runs, line breaks included, read as one
    space): a count, never the names. None when the gitignored name table is absent."""
    real = names.real_names()
    if real is None:
        return None
    flat = {k: ' '.join(str(v).split()) for k, v in real.items()}
    return names.names_found('\n'.join(' '.join(t.split()) for p in paths for t in S.TEXTS.get(Path(p), [])), flat)


def main(out_dir=S.FIG_DIR, private=True):
    out_dir = Path(out_dir)
    written = []
    for path in sorted(HERE.glob('sl_[0-9][0-9]_*.py')):
        module = importlib.import_module(path.stem)
        if 'private' in inspect.signature(module.plot).parameters:
            pngs = module.plot(out_dir=out_dir, private=private)
        else:
            pngs = module.plot(out_dir=out_dir)
        definitions_check(module, pngs)
        written += pngs
    charts = [p for p in written if Path(p).parent == out_dir]  # the pseudonymous charts; real-name ones go elsewhere
    if len(written) > len(charts):
        print(f'  {len(written) - len(charts)} real-name variants written to deliverables/slides/ (gitignored)')
    leaks = privacy_scan(charts)
    if leaks is None:
        print('  privacy scan skipped: data/private/fx_private_customer_names.csv not found')
    else:
        print(f'  privacy scan of the {len(charts)} pseudonymous charts: {leaks} real names found '
              f'({"PASS" if leaks == 0 else "FAIL"})')
    n_ok = sum(ok for _, ok in S.CHECKS)
    print(f'  {len(charts)} slide charts; number checks: {n_ok} pass, {len(S.CHECKS) - n_ok} fail')
    if leaks:
        raise RuntimeError('a pseudonymous slide chart contains a real customer name')
    if len(S.CHECKS) - n_ok:
        raise RuntimeError('a number drawn on a slide chart does not match the data, or a definition is missing')
    return written


if __name__ == '__main__':
    main()
