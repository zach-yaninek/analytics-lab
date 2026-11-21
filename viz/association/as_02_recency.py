#!/usr/bin/env python3
"""Association chart 2: how far before a ticket its own codes appear (item 3, cumulative presence).

Share of tickets with their Category's code set present within k hours before the ticket (blue), against the same
machine's control window (gray), for k = 30 minutes to 30 days, on the H1 population (mapped tickets on machine types
that log their set). k up to 7 days uses one fixed set of 1,439 tickets (docs/07 A8); 30 days uses the last-10 list
on 1,469. The gap is widest relative to the control in the final hours: that is the excess presence fraction in the
footer (a lower bound on the share of present codes that come from the ticket's fault, if the control is valid).

Inputs:  verification/outputs/assoc/as_recency.csv, as_item4.csv
Output:  viz/figures/as_02_recency.png
Run:     cd /home/user/analytics-lab && python3 -I viz/association/as_02_recency.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'style')]
import numpy as np  # noqa: E402

import assoc  # noqa: E402
import ipa_style as style  # noqa: E402

PNG = 'as_02_recency.png'
LABELS = {0.5: '30 min', 1.0: '1 h', 2.0: '2 h', 6.0: '6 h', 24.0: '1 day', 168.0: '7 days', 720.0: '30 days'}


def plot(out_dir=assoc.FIG_DIR):
    out_dir = Path(out_dir)
    r = assoc.load('recency')
    t = r[r.curve == 'target'].sort_values('k')
    i4 = assoc.load('item4')
    epf = i4[i4.measure == 'excess presence fraction'].set_index('k')
    tight = i4[i4.measure.str.startswith('tightest')].iloc[0]
    for row in t.itertuples():
        style.check(f'as_02 share at k={row.k:g} = n_T / n', row.pT, row.n_T / row.n_pairs, 1e-12)
        if row.k in epf.index:
            style.check(f'as_02 excess fraction at k={row.k:g}', epf.loc[row.k, 'estimate'],
                        (row.pT - row.pC) / row.pT, 1e-9)
    style.check('as_02 shares never fall with k (ticket)', 1, int((np.diff(t.pT) >= 0).all()))
    sens = assoc.load('sensitivities')
    g = sens[sens.variant.str.startswith('S3') & (sens.k == assoc.K7)].h2a.astype(float)
    g_lo, g_hi = float(np.exp(g.min())), float(np.exp(g.max()))
    gd = assoc.load('guard')
    g30 = gd[(gd.outcome == 'target set') & (gd.k == 6.0) & (gd.guard_h == 0.5)].iloc[0]
    first = t.iloc[0]
    mr = assoc.load('match_rates')
    mr = mr[(mr.kind == 'exploratory: target code by look-back') & (mr.unit == 'MICRO (overall)')]
    mr = mr.drop_duplicates(['k', 'side']).set_index(['k', 'side'])
    for (k, side), m in mr.iterrows():
        style.check(f'as_02 precision k={k:g} {side} = true_pos / n_present', m.precision, m.true_pos / m.n_present,
                    1e-12)
    style.check('as_02 look-back recall at 7 days = ticket share at 7 days', t[t.k == assoc.K7].pT.iloc[0],
                mr.loc[(assoc.K7, 'ticket'), 'recall'], 1e-9)
    title = (f'A ticket\'s own codes appear in its final 30 minutes for {first.pT:.0%} of tickets, against '
             f'{first.pC:.0%} of controls')

    fig, ax = style.figure(max(10.5, 0.12 * len(title) + 2 * style.MARGIN), 6.2)
    x = np.arange(len(t), dtype=float)
    line = (t.k <= assoc.K7).to_numpy()  # k <= 7 d: one fixed set of pairs; 30 d: last-10 list, drawn apart
    x[~line] += 1.2  # room for the series names between the 7-day end and the 30-day column
    ax.plot(x[line], 100 * t.pT[line], color=style.BLUE, lw=2, marker='o', ms=6, zorder=3)
    ax.plot(x[line], 100 * t.pC[line], color=style.GRAY, lw=2, marker='o', ms=6, zorder=2)
    ax.scatter(x[~line], 100 * t.pT[~line], s=40, facecolors=style.SURFACE, edgecolors=style.BLUE, linewidths=2,
               zorder=3)
    ax.scatter(x[~line], 100 * t.pC[~line], s=40, facecolors=style.SURFACE, edgecolors=style.GRAY, linewidths=2,
               zorder=2)
    for xi, a, b, lin in zip(x, t.pT, t.pC, line):
        ax.text(xi, 100 * a + 2.5, f'{a:.0%}', ha='center', va='bottom', fontsize=9.5, color=style.INK)
        ax.text(xi, 100 * b - (3 if lin else 4.5), f'{b:.0%}', ha='center', va='top', fontsize=9.5, color=style.INK2)
    xe = x[line][-1] + 0.2
    ax.text(xe, 100 * t.pT[line].iloc[-1], 'Before the ticket', color=style.BLUE, va='center', fontsize=10)
    ax.text(xe, 100 * t.pC[line].iloc[-1], 'Control, 35 days earlier', color=style.INK2, va='center', fontsize=10)
    ax.set_xticks(x)
    ax.set_xticklabels([LABELS[k] if k <= assoc.K7 else '30 days\n(last-10 list)' for k in t.k], color=style.INK2)
    ax.set_xlim(-0.4, x[-1] + 0.6)
    ax.set_ylim(-8, 90)
    style.pct_axis(ax.yaxis)
    style.style_axes(ax, grid='y', baseline='bottom')
    ax.set_xlabel('Code set present within this long before the ticket (or the control\'s end)')
    ax.set_ylabel('Share of tickets')
    note_k = [0.5, 2.0, 24.0, 168.0]
    epf_txt = ', '.join(f'{LABELS[k]} {epf.loc[k, "estimate"]:.2f}' for k in note_k)
    style.frame(
        fig, title,
        f'Tickets whose Category points at a code set, on machine types that log it ({int(first.n_pairs):,} '
        f'tickets; 1,469 at 30 days). The signal is concentrated in the final hours: within 7 days the code set is '
        f'present before {t[t.k == 168].pT.iloc[0]:.0%} of tickets and in {t[t.k == 168].pC.iloc[0]:.0%} of '
        f'controls.',
        definitions=[assoc.TARGET_DEFINITION, assoc.RECENCY_CONTROL_DEFINITION],
        notes=[f'Excess presence fraction (pT - pC) / pT: if the control is valid, at least this share of tickets with the '
               f'codes in that span would not have had them there without whatever led to the ticket: {epf_txt}. It is '
               f'not specific to the Category: codes of unrelated sets give 0.70 at 30 min (exploratory). Whether codes '
               f'match the Category is H2a (chart as_01).',
               f'Up to 7 days the same 1,439 tickets are used at every point (docs/07 A8); the 30-day point uses the last-'
               f'10 list on 1,469. Codes in the final 30 minutes cannot be told apart from the call itself: with them '
               f'dropped from both windows, the set is present within 6 hours before {g30.p_guard:.0%} of tickets and '
               f'{g30.p_control_guard_lo:.0%}-{g30.p_control_guard_hi:.0%} of controls, and the guard bands leave the '
               f'pooled H2a result of chart as_01 at {g_lo:.1f}x to {g_hi:.1f}x.',
               f'For a linker (exploratory; micro-averaged over code sets, so a ticket counts once for each set '
               f'whose codes it shows): of the set-code hits in the final 2 hours, '
               f'{mr.loc[(2.0, "ticket"), "precision"]:.0%} are on tickets whose Category points at that set (control '
               f'windows {mr.loc[(2.0, "control"), "precision"]:.0%}); over 7 days, '
               f'{mr.loc[(assoc.K7, "ticket"), "precision"]:.0%} ({mr.loc[(assoc.K7, "control"), "precision"]:.0%}). '
               f'The short look-back is more precise but finds the codes for fewer tickets (the blue line).',
               assoc.source('recency', 'item4', 'guard', 'match_rates')])
    return [style.save(fig, out_dir / PNG)]


if __name__ == '__main__':
    plot()
