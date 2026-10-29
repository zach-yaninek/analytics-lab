#!/usr/bin/env python3
"""Slide chart 25 (follow-up to slide 5): what type is the next ticket in a 30-day repeat?

Pairing matrix at group level (docs/09 §5 B1), the same chart as sl_24 for the 30-day window: rows = the index
ticket's request type, columns = the type of its next ticket, for the 1,574 index tickets whose next unplanned ticket
opens within 30 days. Software, Operator error and Other are pooled as Other (followup_terms.MATRIX_MAP). Cell = share
of the row's repeats (each row sums to 100%), shaded white to blue, the diagonal (same group) outlined in navy. Row
label: the row's repeats and the share of that group's eligible index tickets that repeat. The drawing and its checks
are sl_24's pairing_figure().

Input:  verification/outputs/followups/rp_pairs.csv (one row per eligible index ticket), rp_matrix.csv,
        rp_index_type.csv, followups_summary.json
Output: viz/figures/slides/sl_25_repeat_pairings_30d.png (half card, tall)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402
import sl_24_repeat_pairings_7d as P  # noqa: E402

PNG = 'sl_25_repeat_pairings_30d.png'
TERMS = ['repeat', 'pairing', 'other_groups']


def plot(out_dir=S.FIG_DIR):
    fig = P.pairing_figure(30, 'sl_25')
    S.definitions(fig, T.items(TERMS))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
