#!/usr/bin/env python3
"""Slide chart 29 (follow-up to slide 5): what kind of ticket follows, model by model and type by type?

Pairing classes per unit (docs/09 §5 B6, §12 items 4 and 6), in two panels: by model (left) and by telemetry type
(right). Rows: the units with 50+ repeats within 30 days, in descending repeats, then the rest pooled ('Other 24
models', 'Other 15 telemetry types': the count is every unit with eligible index tickets and no row of its own, as on
sl_28, so both charts' units add up to every model and type in rp_pairs.csv); on the right, after a small gap, 'No
device match' and 'Unknown', which are not telemetry types (italic labels). Each row is a 100% bar of its repeats by
class, the six classes shown as four segments as on sl_27 (followup_terms.CLASS4: Monitoring, No Trouble Found or a
blank Category involved is one light-gray segment, outlined in BASE because its fill is close to white), 2 pt white
gaps between segments, and a whole-percent label in every segment whose share reads 7% or more. Row label: the unit
and its repeats. Text in INK2 as on sl_27. Descriptive: the mixes are not tested across units (B6).

Input:  verification/outputs/followups/rp_class_mix.csv, rp_pairs.csv, rp_by_type.csv, followups_summary.json
Output: viz/figures/slides/sl_29_class_mix.png (full card, tall)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

import deck_style as S  # noqa: E402
import followup_terms as T  # noqa: E402
from sl_24_repeat_pairings_7d import pct_drawn, pct_text, text_width_pt  # noqa: E402
from sl_28_repeat_offenders import NOT_A_TYPE, check_repeat_term, check_telemetry_term  # noqa: E402

PNG = 'sl_29_class_mix.png'
TERMS = ['classes', 'class_units', 'repeat', 'telemetry_type']
PANELS = [('By model', 'model', 'model', 'Other models', 'models'),
          ('By telemetry type', 'telemetry type', 'telemetry_type', 'Other telemetry types', 'telemetry types')]
MIN_LABEL = 7                 # segments whose share reads 7% or more carry their whole-percent label
ROW_GAP = 0.5                 # extra row units before the rows that are not telemetry types
BAR = 0.8                     # bar height, row units
EDGE = 2.0                    # white gap between segments, points (as sl_27)
OUTLINE = 0.8                 # BASE outline of the light segment and its legend key, points (as sl_27)
LIGHT_SEG = 'Monitoring, NTF or blank'
ROW_FONT = S.TICK             # row labels, as sl_27
TICK_PAD = 6                  # row labels: points left of the plot


def plot(out_dir=S.FIG_DIR):
    s = T.summary()
    b, defs = s['facts']['part_b'], s['definitions']
    cm = pd.read_csv(T.FU / 'rp_class_mix.csv')
    p = pd.read_csv(T.FU / 'rp_pairs.csv')
    bt = pd.read_csv(T.FU / 'rp_by_type.csv')
    not_types = sorted(bt.telemetry_type[bt.vs_fleet == NOT_A_TYPE])
    S.check('sl_29 the rows that are not telemetry types: No device match and Unknown', 1,
            int(not_types == ['No device match', 'Unknown']))
    S.check('sl_29 the six classes = the summary', 1, int(sorted(cm.pair_class.unique()) == sorted(defs['classes'])))
    S.check('sl_29 the six classes collapse to the four segments', 1,
            int(set(cm.pair_class) <= set(T.CLASS4_OF) and sorted(set(T.CLASS4_OF.values())) == sorted(T.CLASS4)))
    S.check('sl_29 the light segment is a CLASS4 segment', 1, int(LIGHT_SEG in T.CLASS4))
    S.check('sl_29 two unit kinds', 1, int(sorted(cm.unit_kind.unique()) == ['model', 'telemetry type']))
    rep = p[p.repeat_30]
    S.check('sl_29 every repeat has a class (rp_pairs)', 0, int(rep.pair_class.isna().sum()))

    panels = []
    for title, kind, col, pooled, plural in PANELS:
        tag = f'sl_29 {title.lower()}'
        d = cm[cm.unit_kind == kind]
        counts = d.pivot_table(index='unit', columns='pair_class', values='pairs', aggfunc='sum').reindex(
            columns=defs['classes'])
        repeats = d.groupby('unit').repeats.agg(['min', 'max'])
        S.check(f'{tag}: one repeats count per unit', 0, int((repeats['min'] != repeats['max']).sum()))
        repeats = repeats['min'].rename('repeats')
        S.check(f'{tag}: six classes per unit', 0, int(counts.isna().to_numpy().sum()))
        S.check(f'{tag}: each unit\'s classes sum to its repeats', 0,
                int((counts.sum(axis=1) - repeats.reindex(counts.index)).abs().max()))
        S.check(f'{tag}: shares = pairs / repeats', 0, float((d.share - d.pairs / d.repeats).abs().max()), 1e-6)
        S.check(f'{tag}: the units hold every repeat', b['repeats_30'], int(repeats.sum()))

        # The same table from the pairs: units with 50+ repeats (and, for types, the two that are not types) named,
        # the rest pooled.
        n = rep.groupby(col).size()
        own = (n >= defs['min_repeats_class_mix']) | n.index.isin(not_types if col == 'telemetry_type' else [])
        unit_of = rep[col].where(rep[col].map(own), pooled)
        recount = pd.crosstab(unit_of, rep.pair_class).reindex(index=counts.index, columns=defs['classes'],
                                                              fill_value=0)
        S.check(f'{tag}: every cell = rp_pairs.csv', 0, int((recount - counts).abs().to_numpy().max()))
        S.check(f'{tag}: the units = rp_pairs.csv\'s units with 50+ repeats, the rest pooled', 1,
                int(sorted(unit_of.unique()) == sorted(counts.index)))

        named = repeats.drop([pooled] + [u for u in not_types if u in repeats.index])
        S.check(f'{tag}: the named units have 50+ repeats', 1, int((named >= defs['min_repeats_class_mix']).all()))
        order = named.reset_index().sort_values(['repeats', 'unit'], ascending=[False, True]).unit.tolist()
        rows = [(float(i), u, 'unit') for i, u in enumerate(order)] + [(float(len(order)), pooled, 'pooled')]
        if col == 'telemetry_type':
            rows += [(len(rows) + ROW_GAP + i, u, 'not a type')
                     for i, u in enumerate(sorted(not_types, key=lambda u: -repeats[u]))]
        S.check(f'{tag}: every unit drawn once', len(counts), len(rows))
        # The pooled row's label gives the units it holds: every unit with eligible index tickets (rp_pairs.csv)
        # and no row of its own, those without a repeat included, as on sl_28.
        units_all = set(p[col])
        rest = units_all - set(named.index) - set(not_types)
        S.check(f'{tag}: the pooled units have under 50 repeats (zero for {len(rest - set(n.index))})', 1,
                int(all(n.get(u, 0) < defs['min_repeats_class_mix'] for u in rest)))
        S.check(f'{tag}: the pooled units\' repeats = the pooled row', repeats[pooled],
                int(sum(n.get(u, 0) for u in rest)))
        name = {u: u for _, u, _ in rows}
        name[pooled] = f'Other {len(rest)} {plural}'
        S.check(f'{tag}: {name[pooled]} = the units with eligible index tickets and no row of their own', len(rest),
                int(re.search(r'Other (\d+) ', name[pooled]).group(1)))
        S.check(f'{tag}: named + pooled + not types = every unit in rp_pairs.csv', len(units_all),
                len(named) + len(rest) + (len(not_types) if col == 'telemetry_type' else 0))
        c4 = pd.DataFrame({c: counts[[k for k, v in T.CLASS4_OF.items() if v == c]].sum(axis=1) for c in T.CLASS4})
        panels.append((title, rows, repeats, c4, name))
    S.check('sl_29 by model: 7 models and Other models', 8, len(panels[0][1]))
    S.check('sl_29 by telemetry type: 8 types, Other telemetry types, No device match, Unknown', 11,
            len(panels[1][1]))

    fig, ax0 = S.figure(S.FULL_TALL)
    ax0.remove()
    axes = fig.subplots(1, 2)
    fig.get_layout_engine().set(wspace=0.1)
    y_max = max(y for _, rows, _, _, _ in panels for y, _, _ in rows)
    seg_labels = []                                   # (name, label, its segment)
    for ax, (title, rows, repeats, c4, name) in zip(axes, panels):
        tag = f'sl_29 {title.lower()}'
        labels = []
        for y, u, kind in rows:
            n = int(repeats[u])
            share = c4.loc[u] / n
            S.check(f'{tag} {u}: the four segments sum to 100%', 1, float(share.sum()), 1e-12)
            left = 0.0
            for c in T.CLASS4:
                w = 100 * share[c]
                if w == 0:                    # an empty class (Unknown has no same-group pair): no segment
                    continue
                light = c == LIGHT_SEG
                bar = ax.barh(y, w, left=left, height=BAR, color=T.CLASS4_COLOR[c],
                              edgecolor=S.BASE if light else 'none', linewidth=OUTLINE if light else 0, zorder=2)[0]
                if left > 0:                  # the white gap between segments, over the light segment's outline
                    ax.plot([left, left], [y - BAR / 2, y + BAR / 2], color=S.WHITE, lw=EDGE,
                            solid_capstyle='projecting', zorder=2.5)
                txt = pct_text(share[c])
                S.check(f'{tag} {u} {c}: labelled = reads {MIN_LABEL}% or more', int(pct_drawn(txt) >= MIN_LABEL),
                        int(share[c] >= (MIN_LABEL - 0.5) / 100))
                if pct_drawn(txt) >= MIN_LABEL:
                    S.check(f'{tag} {u} {c} label {txt}', 100 * c4.loc[u, c] / n, pct_drawn(txt), 0.5)
                    t = ax.text(left + w / 2, y, txt, ha='center', va='center_baseline', fontsize=S.SMALL,
                                color=T.CLASS4_TEXT[c], zorder=3)
                    seg_labels.append((f'{tag} {u} {c}', t, bar))
                left += w
            label = f'{name[u]} ({n:,})'
            S.check(f'{tag} {u} row label repeats', n,
                    int(re.search(r'\(([\d,]+)\)$', label).group(1).replace(',', '')))
            labels.append((label, kind))
        ax.set_yticks([y for y, _, _ in rows])
        ax.set_yticklabels([x for x, _ in labels], fontsize=ROW_FONT)
        ax.tick_params(axis='y', pad=TICK_PAD)
        for t, (_, kind) in zip(ax.get_yticklabels(), labels):
            t.set_color(S.INK2)
            t.set_style('italic' if kind == 'not a type' else 'normal')
        ax.set_ylim(y_max + 0.6, -0.6)
        ax.set_xlim(0, 100)
        ax.set_xticks([0, 25, 50, 75, 100])          # as sl_27
        S.pct_axis(ax.xaxis)
        S.style_axes(ax, grid=None, baseline=None)          # the bars hide a grid; the labels carry the values
        ax.set_xlabel('Share of repeats')
        label_w = max(text_width_pt(fig, x, ROW_FONT) for x, _ in labels) + TICK_PAD
        ax.annotate(title, xy=(0, 1), xycoords='axes fraction', xytext=(-label_w, 6), textcoords='offset points',
                    ha='left', va='bottom', fontsize=S.FONT, weight='bold', color=S.INK)

    handles = [Patch(facecolor=T.CLASS4_COLOR[c], edgecolor=S.BASE if c == LIGHT_SEG else 'none',
                     linewidth=OUTLINE if c == LIGHT_SEG else 0, label=c) for c in T.CLASS4]
    legend = fig.legend(handles=handles, loc='outside upper center', ncol=len(handles), handlelength=1.4,
                        handleheight=0.9, handletextpad=0.5, columnspacing=1.8, borderaxespad=0.15, fontsize=S.SMALL)

    # The definitions' numbers.
    t = T.terms()
    m = re.search(r'with (\d+)\+ repeats within (\d+) days', t['class_units'][1])
    S.check('sl_29 definition: 50+ repeats = the protocol minimum', defs['min_repeats_class_mix'], int(m.group(1)))
    S.check('sl_29 definition: repeats within 30 days', 0, int((rep.gap_days > int(m.group(2))).sum()))
    check_repeat_term('sl_29', p)
    check_telemetry_term('sl_29', p)
    S.definitions(fig, T.items(TERMS))

    # On the layout as saved: every segment label inside its segment, clear of the white gaps; the legend inside
    # the image and clear of the panel labels.
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    edge = EDGE * fig.dpi / 72
    for label_name, txt, bar in seg_labels:
        a, seg = txt.get_window_extent(renderer=r), bar.get_window_extent(renderer=r)
        S.check(f'{label_name}: label inside its segment', 1, int(a.x0 >= seg.x0 + edge and a.x1 <= seg.x1 - edge))
    leg = legend.get_window_extent(renderer=r)
    heads = [x.get_window_extent(renderer=r) for ax in axes for x in ax.texts if x.get_text().startswith('By ')]
    S.check('sl_29 legend inside the image, clear of the panel labels', 1,
            int(leg.x0 >= 0 and leg.x1 <= fig.bbox.x1 and leg.y1 <= fig.bbox.y1
                and not any(leg.overlaps(h) for h in heads)))
    return [S.save(fig, Path(out_dir) / PNG)]


if __name__ == '__main__':
    plot()
