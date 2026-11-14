#!/usr/bin/env python3
"""Draw every report figure, check its numbers, scan its text, and write the report's Figures section.

Each figure supports one paragraph of the report's Results, in the same order, and that paragraph ends with
(Figure~\\ref{LABEL}). This draws the figures into report/figures/ (PDF, SVG and PNG), runs every figure's checks
against the committed outputs and the report's text, scans every drawn string for identifiers (pseudonym patterns
always; IPA's real names and numbers too when IPA's files are in data/raw/), and writes report/ipa_figures.tex from
the figures' captions.

Run: cd /home/user/analytics-lab && python3 -I viz/report/run_all.py
"""
import importlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import report_style as S  # noqa: E402

ORDER = ['fig01_ownership', 'fig02_high_ticket', 'fig03_repeats', 'fig04_rates', 'fig05_customers',
         'fig06_persistence', 'fig07_clock', 'fig08_first_look', 'fig09_association', 'fig10_request_types',
         'fig11_pairings', 'fig12_electronics', 'fig13_verification']
TEX = S.ROOT / 'report' / 'ipa_figures.tex'
PSEUDONYM = re.compile(r'\b(?:T|S|M)\d{5}\b|\bCustomer \d{3}\b')

HEADER = r"""% The report's Figures section, written by viz/report/run_all.py from each figure script's caption; edit the
% captions in viz/report/figNN_*.py and re-run it. Each figure supports one Results paragraph, which ends with
% (Figure~\ref{...}). Needs \usepackage{graphicx} in the preamble; the PDFs are in figures/ beside this file.
% The float settings below let up to three figures share a page; they apply from here to the end of the document.
\renewcommand{\topfraction}{0.95}
\renewcommand{\bottomfraction}{0.95}
\renewcommand{\textfraction}{0.05}
\renewcommand{\floatpagefraction}{0.85}
\setcounter{topnumber}{3}
\setcounter{bottomnumber}{3}
\setcounter{totalnumber}{4}

\section{Figures}
"""
ENTRY = r"""
\begin{figure}[!htbp]
  \centering\small
  \includegraphics[width=\linewidth]{figures/%(name)s.pdf}
  \caption[%(short)s]{%(caption)s}
  \label{%(label)s}
\end{figure}
"""


def privacy_scan():
    """Pseudonym patterns in any drawn string (the figures carry no unit labels), then real identifiers if IPA's
    files are present."""
    flagged = {stem: [t for t in texts if PSEUDONYM.search(t)] for stem, texts in S.TEXTS.items()}
    n_pseudo = sum(len(v) for v in flagged.values())
    S.check('privacy: no pseudonym or unit label drawn on any figure', 0, n_pseudo)
    sys.path.insert(0, str(S.ROOT / 'verification'))
    import common  # noqa: E402
    if not (common.XLS.exists() and common.EQUIPMENT.exists()):
        print('  (IPA files not present: real-identifier scan skipped)')
        return
    import pandas as pd  # noqa: E402
    import fleet_exposure as FX  # noqa: E402
    import followups as F  # noqa: E402
    maps = common.extend_maps(common.build_maps(common.load_raw(common.XLS)), common.load_equipment(common.EQUIPMENT))
    real = F.real_sets(maps, common.EQUIPMENT)
    texts = [t for v in S.TEXTS.values() for t in v if not re.fullmatch(r'[\d.,%–\-+×x\s$()]*', t)]
    hits = sum(FX.text_leaks(pd.DataFrame({'text': texts}), real).values())
    S.check('privacy: no real name or identifier drawn on any figure', 0, hits)


def main():
    entries = []
    for name in ORDER:
        mod = importlib.import_module(name)
        assert mod.NAME == name, f'{name}: NAME is {mod.NAME}'
        before = len(S.CHECKS)
        caption = mod.plot()
        n = len(S.CHECKS) - before
        bad = sum(not ok for _, ok, _ in S.CHECKS[before:])
        print(f'  {name}: {n - bad}/{n} checks pass')
        # 'vs. ' would get LaTeX's wider sentence-ending space; a tie keeps the normal one
        entries.append({'name': name, 'short': mod.SHORT, 'caption': caption.replace('vs. ', 'vs.~'),
                        'label': mod.LABEL})
    privacy_scan()
    TEX.write_text(HEADER + ''.join(ENTRY % e for e in entries) + '\n\\clearpage\n')
    print(f'  wrote {TEX.relative_to(S.ROOT)} ({len(entries)} figures)')
    return 1 if S.summary() else 0


if __name__ == '__main__':
    sys.exit(main())
