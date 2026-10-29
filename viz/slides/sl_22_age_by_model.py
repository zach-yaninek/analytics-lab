#!/usr/bin/env python3
"""Slide chart 22 (follow-up to slide 4): the request-type mix of under-4 and 4+ machines, model by model.

Heat table (docs/09 §4 A5): the six models with 30+ unplanned tickets in each age group, then, below a divider, the
three telemetry types that add information beyond model (§3.6: alex2.0-1 and alex2.0-3 each span four alEx models,
scrubex-7 is part of LVRR-WP). One row per age group: tickets, the rate per 100 installed machine-months (models
only; telemetry types have no installed months, §10), then each request group's share of the row's tickets (Rest =
Software, Operator error, Other and Not categorised), shaded white to blue, and the within-model mix test's
Benjamini-Hochberg q once per pair (bold = q < 0.05).

Input:  verification/outputs/followups/ag_by_model.csv, ag_by_type.csv, ag_support.csv, followups_summary.json
Output: viz/figures/slides/sl_22_age_by_model.png (full card, tall)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402
from sl_24_repeat_pairings_7d import GAP, cell_color, pct_drawn, pct_text, text_color  # noqa: E402

PNG = 'sl_22_age_by_model.png'
TERMS = ['by_model', 'telemetry_type', 'under4']
TYPES = ['alex2.0-1', 'alex2.0-3', 'scrubex-7']        # the telemetry types that split a model (docs/09 §3.6)
AGES = ['Under 4', '4+']
SHOWN = ['Door', 'Mechanical', 'Electronics', 'Network', 'No Trouble Found', 'Monitoring']
REST = ['Software', 'Operator error', 'Other', 'Not categorised']
COLS = SHOWN + ['Rest']

# Layout, in inches across the card and row units down it.
X_AGE, X_TICKETS, X_RATE = 1.80, 3.45, 4.75            # age label (left), tickets and rate (right edges)
X_CELLS, CELL_W = 5.00, 1.50                           # share cells: left edge, width
X_MIX = X_CELLS + len(COLS) * CELL_W + 0.95            # mix test (centre)
WIDTH = 17.3
HEAD, SECTION, FOOT = 1.15, 1.3, 0.2                   # header band, section band, bottom margin; row units


def q_text(q):
    """A q-value to two significant figures: 'q = 0.0015', 'q = 0.21'. Returns the text and half its last digit."""
    d = 1 - int(np.floor(np.log10(q)))
    return f'q = {q:.{d}f}', 0.5 * 10.0 ** -d


def plot(out_dir=S.FIG_DIR):
    bm = pd.read_csv(T.FU / 'ag_by_model.csv')
    bt = pd.read_csv(T.FU / 'ag_by_type.csv')
    sup = pd.read_csv(T.FU / 'ag_support.csv')
    defs = T.summary()['definitions']
    groups = defs['groups']
    S.check('sl_22 the ten request groups = shown + Rest', 1, int(sorted(groups) == sorted(SHOWN + REST)))

    # The models: 30+ tickets in each age group (ag_support's shown_by_model), in the CSV's order.
    models = list(dict.fromkeys(bm.model))
    S.check('sl_22 six models', 6, len(models))
    S.check('sl_22 models = ag_support shown_by_model', 1,
            int(sorted(models) == sorted(sup[sup.shown_by_model].model.unique())))
    S.check('sl_22 every model has 30+ tickets in each age group', 1,
            int(bm.tickets.min() >= defs['min_shown_tickets']))
    bt = bt[bt.telemetry_type.isin(TYPES)]
    for t in TYPES:
        S.check(f'sl_22 {t} is a shown telemetry type (30+ tickets in each age group)', 1,
                int(len(bt[bt.telemetry_type == t]) == 2 and bt[bt.telemetry_type == t].shown.all()
                    and bt[bt.telemetry_type == t].tickets.min() >= defs['min_shown_tickets']))

    blocks = [('model', m, bm[bm.model == m].set_index('age_group').reindex(AGES)) for m in models]
    blocks += [('type', t, bt[bt.telemetry_type == t].set_index('age_group').reindex(AGES)) for t in TYPES]

    fig, ax = S.figure(S.FULL_TALL)
    ys = {}                                            # (kind, name) -> top of its under-4 row
    y = HEAD
    for kind, name, _ in blocks:
        if (kind, name) == ('type', TYPES[0]):
            y += SECTION
        ys[(kind, name)] = y
        y += 2
    height = y

    # Header.
    hy = HEAD / 2
    kw = dict(va='center_baseline', fontsize=S.SMALL, color=S.INK2)
    ax.text(X_TICKETS, hy, 'Tickets', ha='right', **kw)
    ax.text(X_RATE, hy, 'Rate per 100', ha='right', **kw)
    for j, c in enumerate(COLS):
        ax.text(X_CELLS + (j + 0.5) * CELL_W, hy, c, ha='center', **kw)
    ax.text(X_MIX, hy, 'Mix test', ha='center', **kw)
    ax.plot([0, WIDTH], [HEAD, HEAD], color=S.BASE, lw=1.0, solid_capstyle='butt', zorder=2)

    for kind, name, d in blocks:
        top = ys[(kind, name)]
        tag = f'sl_22 {name}'
        # The shares behind every cell: each group's tickets over the row's tickets, = the CSV's share columns.
        n_groups = d[[f'tickets_{g}' for g in groups]].sum(axis=1)
        S.check(f'{tag} group tickets add up to the tickets (both rows)', 0,
                int((n_groups - d.tickets).abs().max()))
        share = pd.DataFrame({g: d[f'tickets_{g}'] / d.tickets for g in groups})
        S.check(f'{tag} shares = tickets / row tickets (both rows, ten groups)', 0,
                float((share - d[[f'share_{g}' for g in groups]].set_axis(groups, axis=1)).abs().to_numpy().max()),
                1e-6)
        share['Rest'] = share[REST].sum(axis=1)
        for r, age in enumerate(AGES):
            yc = top + r + 0.5
            row = d.loc[age]
            S.check(f'{tag} {age} shown shares and Rest sum to 1', 1, float(share.loc[age, COLS].sum()), 1e-9)
            if r == 0:
                ax.text(0, yc, name, ha='left', va='center_baseline', fontsize=S.TICK, color=S.INK)
            ax.text(X_AGE, yc, age, ha='left', **kw)
            ticket_txt = f'{int(row.tickets):,}'
            S.check(f'{tag} {age} tickets', row.tickets, int(ticket_txt.replace(',', '')))
            ax.text(X_TICKETS, yc, ticket_txt, ha='right', va='center_baseline', fontsize=S.SMALL, color=S.INK)
            if kind == 'model':
                rate_txt = f'{row.rate_per_100:.1f}'
                S.check(f'{tag} {age} rate per 100 = 100 x tickets / months', row.rate_per_100,
                        100 * row.tickets / row.months, 1e-4)
                S.check(f'{tag} {age} rate per 100 drawn', row.rate_per_100, float(rate_txt), 0.05)
            else:
                rate_txt = '–'
            ax.text(X_RATE, yc, rate_txt, ha='right', va='center_baseline', fontsize=S.SMALL,
                    color=S.INK if kind == 'model' else S.INK2)
            for j, c in enumerate(COLS):
                v = share.loc[age, c]
                bg = cell_color(v)
                ax.add_patch(Rectangle((X_CELLS + j * CELL_W, top + r), CELL_W, 1, facecolor=bg, edgecolor=S.WHITE,
                                       linewidth=GAP, zorder=1))
                txt = pct_text(v)
                csv_share = row[f'share_{c}'] if c != 'Rest' else sum(row[f'share_{g}'] for g in REST)
                S.check(f'{tag} {age} {c} share', 100 * csv_share, pct_drawn(txt), 0.5 + 5e-4)  # CSV: 6 dp
                ax.text(X_CELLS + (j + 0.5) * CELL_W, yc, txt, ha='center', va='center_baseline',
                        fontsize=S.SMALL, color=text_color(bg), zorder=3)
        # The mix test, once per pair: q (Benjamini-Hochberg over the models, or over the telemetry types).
        q = d.mix_q.iloc[0]
        S.check(f'{tag} one mix test for both rows', 0, abs(d.mix_q.iloc[0] - d.mix_q.iloc[1]))
        S.check(f'{tag} mix differs = q < 0.05', int(bool(d.mix_differs.iloc[0])), int(q < 0.05))
        qt, tol = q_text(q)
        S.check(f'{tag} mix test q', q, float(qt.split('=')[1]), tol)
        sig = q < 0.05
        ax.text(X_MIX, top + 1, qt, ha='center', va='center_baseline', fontsize=S.SMALL,
                color=S.INK if sig else S.INK2, weight='bold' if sig else 'normal')
        # Thin rule under each pair, except the last of a block (the divider or the bottom follows).
        last = (kind, name) in (('model', models[-1]), ('type', TYPES[-1]))
        if not last:
            ax.plot([0, WIDTH], [top + 2, top + 2], color=S.GRID, lw=1.0, solid_capstyle='butt', zorder=2)

    # The divider and the section label above the telemetry types.
    ty = ys[('type', TYPES[0])]
    ax.plot([0, WIDTH], [ty - SECTION, ty - SECTION], color=S.BASE, lw=1.0, solid_capstyle='butt', zorder=2)
    ax.text(0, ty - SECTION / 2 + 0.05, 'Telemetry types that split a model', ha='left', va='center_baseline',
            fontsize=S.SMALL, color=S.INK2, style='italic')

    ax.set_xlim(0, WIDTH)
    ax.set_ylim(height + FOOT, 0)
    ax.axis('off')

    # The definitions' numbers.
    t = T.terms()
    m = re.search(r'models with (\d+)\+ tickets in each age group', t['by_model'][1])
    S.check('sl_22 definition: models with 30+ tickets in each age group', defs['min_shown_tickets'], int(m.group(1)))
    m = re.search(r'\((<1), (1-2) and (2-4) years\)', t['under4'][1])
    S.check('sl_22 definition: under 4 = the bands <1, 1-2 and 2-4', 1,
            int(list(m.groups()) == defs['young_bands']))
    S.definitions(fig, T.items(TERMS))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
