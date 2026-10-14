#!/usr/bin/env python3
"""Slide version of chart 9 (viz/high_ticket/htm_09_tickets_by_type.py): raw unplanned ticket counts by model and by
telemetry machine type (two figures).

Same bars, order, colours and "Other" bar as the full charts. The value labels keep the counts and drop the shares;
the fleet-size disclaimer, the population and the notes go to the speaker notes.

Outputs: viz/figures/slides/htm_09_tickets_by_model.png
         viz/figures/slides/htm_09_tickets_by_machine_type.png
Run:     cd /home/user/analytics-lab && python3 -I viz/slides/htm_09_tickets_by_type_slide.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# python3 -I leaves the script directory off sys.path
sys.path[:0] = [str(HERE), str(HERE.parent / 'style'), str(HERE.parent / 'high_ticket')]
import numpy as np  # noqa: E402

import htm  # noqa: E402
import htm_09_tickets_by_type as full  # noqa: E402
import ipa_style as style  # noqa: E402
import slides  # noqa: E402


def draw(d, noun, title, subtitle, talk, path):
    shown, rest = d.head(full.N_SHOWN), d.iloc[full.N_SHOWN:]
    labels = shown.value.tolist() + ([f'Other {noun}'] if len(rest) else [])
    counts = shown.unplanned_tickets.tolist() + ([int(rest.unplanned_tickets.sum())] if len(rest) else [])
    colors = [style.BLUE] * full.N_HIGHLIGHT + [style.GRAY_LIGHT] * (len(shown) - full.N_HIGHLIGHT)
    colors += [style.BAR_BACKGROUND] * (len(labels) - len(shown))

    fig, ax = slides.figure()
    y = np.arange(len(labels))[::-1]
    ax.barh(y, counts, height=0.5, color=colors, linewidth=0)
    for yi, n in zip(y, counts):
        ax.text(n + max(counts) * 0.01, yi, f'{n:,}', va='center', ha='left', fontsize=9.5, color=style.INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, color=style.INK2)
    ax.set_ylim(-0.6, len(labels) - 0.4)
    ax.set_xlim(0, max(counts) * 1.1)
    style.style_axes(ax, grid='x', baseline='left')
    style.thousands_axis(ax.xaxis)
    ax.set_xlabel('Unplanned tickets')
    return slides.finish(fig, path, title, subtitle, talk)


def plot(out_dir=slides.FIG_DIR):
    out_dir = Path(out_dir)
    S_all = htm.summary()
    S = S_all['D1_workload']
    period = htm.period_text(S_all, 'case_export_period')
    written = []

    m = full.tickets_by('model')
    total = int(m.unplanned_tickets.sum())
    style.check('slide htm_09 model tickets = D1 tickets', S['tickets'], total)
    top = m.head(full.N_HIGHLIGHT)
    written.append(draw(
        m, 'models',
        f'Three models generate {style.pct(top.unplanned_tickets.sum() / total, 0)} of unplanned tickets',
        f'Raw unplanned ticket counts by model, {period}',
        [full.disclaimer('model') + ' The number of installed machines per model is not in the data (model is '
         'recorded only on tickets), so per-machine rates by model cannot be computed directly.',
         f'Population: all {total:,} unplanned tickets on {S["machines"]:,} ticketed machines (case-export serials); '
         f'planned work, cancelled and duplicate cases excluded. Blue = the three models with the most tickets; '
         f'Other = the {len(m) - full.N_SHOWN} models with the fewest.',
         full.proxy_note(top.value.tolist())],
        out_dir / 'htm_09_tickets_by_model.png'))

    t = full.tickets_by('machine_type')
    unmatched = int(t.loc[t.value == full.NOT_MATCHED, 'unplanned_tickets'].sum())
    t = t[t.value != full.NOT_MATCHED]
    matched = int(t.unplanned_tickets.sum())
    style.check('slide htm_09 machine-type tickets = D1 tickets', S['tickets'], matched + unmatched)
    top = t.head(full.N_HIGHLIGHT)
    written.append(draw(
        t, 'types',
        f'Three telemetry types generate {style.pct(top.unplanned_tickets.sum() / matched, 0)} of device-matched '
        f'tickets',
        f'Raw unplanned ticket counts by telemetry machine type, {period}',
        [full.disclaimer('type') + ' Chart 10 adjusts for this: ticket rates per 100 machine-months by telemetry '
         'type.',
         f'Population: the {matched:,} unplanned tickets whose serial matches a telemetry device; {unmatched:,} '
         f'tickets on machines not matched to a device are left out. Blue = the three types with the most tickets; '
         f'Other = the {len(t) - full.N_SHOWN} types with the fewest.'],
        out_dir / 'htm_09_tickets_by_machine_type.png'))
    return written


if __name__ == '__main__':
    plot()
