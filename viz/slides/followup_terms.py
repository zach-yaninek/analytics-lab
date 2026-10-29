"""Definitions printed on the follow-up slide charts (sl_18 on; docs/09, docs/10), with the numbers they quote read from
verification/outputs/followups/ (followups_summary.json and the ag_*/rp_* tables), so the wording on every chart is the
same and the numbers are the computed ones.

Each chart declares TERMS (keys below) and calls deck_style.definitions(fig, items(TERMS)); viz/slides/run_all.py
checks that every declared definition is printed. The unplanned-ticket and repeat wording follows
viz/zac_notebook/zac_data.py (UNPLANNED_DEFINITION, REPEAT_DEFINITION), shortened for a slide card.
"""
import json
from functools import lru_cache

import deck_style as S

FU = S.OUT / 'followups'

# Pairing matrices on a slide: the three small groups shown together (the CSVs keep all ten).
MATRIX_GROUPS = ['Door', 'Mechanical', 'Electronics', 'Network', 'No Trouble Found', 'Monitoring', 'Not categorised',
                 'Other']
MATRIX_MAP = {'Software': 'Other', 'Operator error': 'Other', 'Other': 'Other'}
MATRIX_SHORT = {'Door': 'Door', 'Mechanical': 'Mech.', 'Electronics': 'Electr.', 'Network': 'Netw.',
                'No Trouble Found': 'NTF', 'Monitoring': 'Monit.', 'Not categorised': 'No cat.', 'Other': 'Other+'}
MATRIX_ROW = {'Other': 'Other+'}   # row labels: the pooled group (Software, Operator error, Other) reads Other+

# Pairing classes on a slide: the three process classes shown as one segment (the CSVs keep all six). Blues = the
# same problem or group, grays = a different group or a process ticket; adjacent pairs pass the dataviz validator's
# separation checks (normal vision and CVD, delta E >= 25), and every segment carries a direct label.
CLASS4 = ['Same Category', 'Same group, other Category', 'Different group', 'Monitoring, NTF or blank']
CLASS4_OF = {'Same Category': 'Same Category', 'Same group, other Category': 'Same group, other Category',
             'Different group': 'Different group', 'Monitoring involved': 'Monitoring, NTF or blank',
             'No Trouble Found involved': 'Monitoring, NTF or blank', 'Category blank': 'Monitoring, NTF or blank'}
CLASS4_COLOR = {'Same Category': S.BLUE, 'Same group, other Category': S.LIGHT, 'Different group': S.INK2,
                'Monitoring, NTF or blank': '#E3E7EB'}
CLASS4_TEXT = {'Same Category': S.WHITE, 'Same group, other Category': S.INK, 'Different group': S.WHITE,
               'Monitoring, NTF or blank': S.INK}

# The telemetry types sl_22 shows under the models: each spans more than one model (docs/09 §3.6), unlike the
# scrubex2.0 types, which re-label one model each.
CUT_TYPES = ['alex2.0-1', 'alex2.0-3', 'scrubex-7']


@lru_cache(maxsize=1)
def summary():
    return json.loads((FU / 'followups_summary.json').read_text())


def and_list(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + ' and ' + xs[-1]


def models_list(models):
    """and_list with a shared first word said once: 'alEx LC-D, LC-S, MC-D and MC-S'."""
    first = {m.split(' ', 1)[0] for m in models}
    if len(models) > 1 and len(first) == 1 and all(' ' in m for m in models):
        return f"{first.pop()} {and_list(m.split(' ', 1)[1] for m in models)}"
    return and_list(models)


def type_spans():
    """'alex2.0-1 and alex2.0-3 each span ...; scrubex-7 spans ...': the models of each CUT_TYPES type's ticketed
    machines (ag_by_type.csv), types with the same models named together."""
    bt = __import__('pandas').read_csv(FU / 'ag_by_type.csv')
    spans = {}
    for ty in CUT_TYPES:
        models = tuple(sorted({m for v in bt.models[bt.telemetry_type == ty].dropna() for m in v.split('; ')}))
        spans.setdefault(models, []).append(ty)
    return '; '.join(f"{and_list(tys)} {'each span' if len(tys) > 1 else 'spans'} {models_list(models)}"
                     for models, tys in spans.items())


def signed(x):
    """A whole number with its sign, the minus typographic: '+15', '−11'."""
    return f'{x:+.0f}'.replace('-', '−')


def same_wo_process():
    """Same Category as a share of the repeats in each of the first three gap bins, leaving out the three process
    classes (Monitoring, No Trouble Found or a blank Category involved): sl_27's light-gray segment."""
    c = __import__('pandas').read_csv(FU / 'rp_classes.csv')
    out = []
    for b in ('1 day or less', 'over 1 to 7 days', 'over 7 to 30 days'):
        x = c[c.gap_bin == b].set_index('pair_class').pairs
        content = x.reindex(['Same Category', 'Same group, other Category', 'Different group']).sum()
        out.append(x['Same Category'] / content)
    return out


def p_text(p, n_perm):
    """A permutation p-value as printed: below the smallest reachable value it reads '< 0.001'."""
    floor = 1 / (n_perm + 1)
    return '< 0.001' if p < 1.5 * floor else f'= {p:.3f}' if p < 0.01 else f'= {p:.2f}'


def terms():
    s = summary()
    f = s['facts']
    sup, a, b, sh = f['support'], f['part_a'], f['part_b'], f['shuffle']
    pd = __import__('pandas')
    gaps = pd.read_csv(FU / 'rp_same_by_gap.csv')
    far = gaps[gaps.gap_bin.isin(['over 90 to 180 days', 'over 180 days'])]
    usual = far.same_category_pairs.sum() / far.pairs.sum()
    lab = sh['label_permutation']
    adj = pd.read_csv(FU / 'ag_type_adjusted.csv')
    cat = adj[(adj.variant == 'primary') & (adj.level == 'category') & (adj.significant == True)]  # noqa: E712
    crosses = cat.type[(cat.share_ratio_lo <= 1) & (cat.share_ratio_hi >= 1)].tolist()
    dec = pd.read_csv(FU / 'ag_decomposition.csv')
    und = int(dec.within_model_age_undefined_draws.max())
    out_g = dec[dec.level == 'group'].outside_support_tickets
    inst = pd.read_csv(FU / 'ag_install_pooled.csv', dtype={'install': str})
    u4_2022 = inst[(inst.category == 'All unplanned tickets') & (inst.install == '2022')].under4_share_of_machines
    n_sup = len(sup['support_models'])
    und_h = int(pd.read_csv(FU / 'ag_halves.csv').change_undefined_draws.max())
    nb = f"{s['n_boot']:,}"
    return {
        'under4': ('Under 4 / 4+', "the machine's age at the midpoint of its months on IPA's list (Aug 2025 to Aug "
                   '2026); under 4 = the first three bars of slide 4 (<1, 1-2 and 2-4 years)'),
        'rate': ('Rate', 'unplanned tickets (all but planned work, cancelled requests and duplicates; No Trouble Found '
                 'stays in) per 100 installed machine-months: 6,750 tickets on 8,946 listed machines'),
        'request_group': ('Request type', "the ticket's Category grouped by IPA's Trouble Code; Monitoring = the "
                          "help desk's “Monitoring – Daily/Poll” tickets; Not categorised = no Category (under the "
                          'Electronics, Network, Software and Operator Error codes a blank Category keeps that group)'),
        'crude': ('Not adjusted for model', 'most under-4 machines are 2.0 models, so this mixes age with design'),
        'share_ratio': ('Share ratio', "a type's share of under-4 machines' tickets ÷ its share of 4+ machines' "
                        f"tickets of the same model, pooled over the {len(sup['support_models'])} models with 100+ "
                        f"machine-months in each age group ({100 * sup['under4_share_support']:.0f}% of under-4 and "
                        f"{100 * sup['plus4_share_support']:.0f}% of 4+ tickets; Mantel-Haenszel); 1 = same mix; "
                        'Not categorised is left out'),
        'interval': ('Bar', '95% interval, bootstrap over accounts (2,000 draws)'),
        'perm_test': ('Test', 'under-4 and 4+ labels shuffled among machines of the same model, 2,000 times: the mix '
                      f"differs overall (p {p_text(a['global_p'], s['n_perm'])}); blue = differs after "
                      'Benjamini-Hochberg (q < 0.05)'),
        'cat_test': ('Tested', 'only Categories in groups that differ (' + ', '.join(
            g for g in a['groups_significant'] if g not in ('Monitoring', 'No Trouble Found')) + '), with the same '
                     'shuffle; blue = differs after Benjamini-Hochberg within its group (q < 0.05); open = not tested'
                     + ('. The test shuffles machines while the bar resamples accounts, so a blue bar can cross 1 ('
                        + and_list(crosses) + ')' if crosses else '')),
        'interval_within': ('Bar', f'95% interval of the dot, bootstrap over accounts ({nb} draws; the {und} in which '
                            'a model has no 4+ machine-months are left out)'),
        'interval_halves': ('Bar', f'95% interval, bootstrap over accounts ({nb} draws; the {und_h} in which a model '
                            "has no 4+ machine-months are left out); bold = the change's interval excludes 0"),
        'extra': ('Extra tickets', "under-4 machines' tickets minus what their months give at 4+ machines' rates "
                  f"({a['extra_tickets']:,.0f} in all). Ring: all; dot and the numbers on the right: within model, at "
                  f"each model's own 4+ rate on the {len(sup['support_models'])} models with "
                  f"{s['definitions']['min_support_months']}+ "
                  'machine-months in each age group; the gap: model mix, plus tickets on models outside the '
                  f"comparison ({a['extra_outside_support']:.0f} in all; {signed(out_g.min())} to "
                  f'{signed(out_g.max())} by group)'),
        'by_model': ('Cell', "share of the row's tickets (Rest = Software, Operator error, Other and Not "
                     'categorised); models with 30+ tickets in each age group'),
        'rate_model': ('Rate per 100', 'unplanned tickets per 100 installed machine-months; – for telemetry types, '
                       'which have no installed months until the database extract'),
        'mix_test': ('Mix test', 'under-4 and 4+ labels shuffled among machines of the same model (for a telemetry '
                     f"type: of the same telemetry type and model), {s['n_perm']:,} times; Benjamini-Hochberg q, "
                     'bold = q < 0.05'),
        'telemetry_type_cut': ('Telemetry type', "the clearView machine type of the device matched to the machine's "
                               'tickets; ' + type_spans()),
        'telemetry_type': ('Telemetry type', 'the clearView type of the matched device; scrubex2.0-2, -3, -4 and -5 '
                           'are LVD-Remote-2.0, LVRR-WP-2.0, MV-2.0 and SV-48-2.0; No device match and Unknown (blank '
                           'type) are not types'),
        'halves': ('Gap', 'extra tickets per 100 under-4 machine-months within model, first half (Aug 2025 to 14 Feb '
                   '2026) vs second (15 Feb to Aug 2026); Categories picked by a rule fixed in advance: the largest '
                   'within-model excess over the year'),
        'fix_proof': ('Reading', 'a narrowing gap fits a fix; proving one needs the dates of design or firmware '
                      'changes'),
        'repeat': ('Repeat', 'the next unplanned ticket on the same machine opens within 30 days (7-day: within 7) of '
                   f"an eligible index ticket opened before 2 Aug 2026 ({b['eligible']:,}); not necessarily a failed "
                   'repair'),
        'pairing': ('Cell', "share of the row's repeats whose next ticket is in the column's group (outlined: same "
                    "group; blank: none); row label: repeats and the share of that group's tickets that repeat"),
        'pairing7': ('Cell', "share of the row's repeats whose next ticket is in the column's group (outlined: same "
                     "group; blank: none); row label: 7-day repeats and the share of that group's tickets that repeat "
                     'within 7 days'),
        'pairing_panel': ('Cell', "share of the row's repeats whose next ticket is in the column's group (outlined: "
                          "same group; blank: none; italic: fewer than 5 pairs); n = the row's repeats"),
        'rest_panel': ('Rest', 'Network, Software, Operator error, Other and Not categorised together; NTF = No '
                       'Trouble Found'),
        'pairs_gap': ('Pairs', f'{int(gaps.pairs.sum()):,} pairs of unplanned tickets on one machine, consecutive or '
                      'not, each with a recorded Category (No Trouble Found counts, Monitoring does not); 90+ days '
                      'apart: the usual mix'),
        'label_test': ('Test', f"Categories shuffled across each machine's own tickets, {s['n_perm']:,} times: of the "
                       f"{sh['pairs']:,} repeats (next ticket within 30 days) with both Categories recorded, neither "
                       f"Monitoring, on the {sh['machines']} machines with 2+ such repeats, "
                       f"{100 * sh['observed_share']:.0f}% share it vs {100 * lab['null_share']:.0f}% by chance (their "
                       f"own mix, not the {100 * usual:.0f}% line; p {p_text(lab['p'], s['n_perm'])})"),
        'interval_line': ('Line on each bar', f'95% interval, bootstrap over accounts ({nb} draws)'),
        'classes_gap': ('Without light gray', 'same Category is ' + and_list(
            f'{100 * x:.0f}%' for x in same_wo_process()) + ' of the repeats in the top three rows'),
        'one_day': ('1 day or less†', 'may include duplicate tickets for one call that were not marked as duplicates'),
        'classes': ('Class', 'the first that applies: a Monitoring ticket, No Trouble Found (NTF) or a blank Category '
                    'involved (light gray); same Category; same group, other Category; different group. '
                    'Group = the request type (Door, Mechanical, Electronics, Network, Software, Operator error or '
                    'Other)'),
        'repeat7': ('7-day repeat', 'the next unplanned ticket on the same machine opens within 7 days of an index '
                    f"ticket opened before 2 Aug 2026 ({b['repeats_7']:,} of {b['eligible']:,}); not necessarily a "
                    'failed repair'),
        'other_groups': ('Other+', 'Software, Operator error and Other; No cat. = Not categorised: no Category, '
                         'outside the Electronics, Network, Software and Operator Error codes; NTF = No Trouble Found'),
        'install_rate': ('Rate', "unplanned tickets of the type per 100 installed machine-months (Aug 2025 to Aug "
                         f"2026) on the {n_sup} models with 100+ machine-months in each age group, by the machine's "
                         f"install year; vertical line: 95% interval, bootstrap over accounts ({nb} draws)"),
        'install_band': ('Shaded', 'install years whose machines are under 4 at the midpoint of their months on '
                         f"IPA's list: the first three bars of slide 4 ({100 * float(u4_2022.iloc[0]):.0f}% of 2022 "
                         'installs)'),
        'install_ratio': ('2022-23 vs 2024-26', "the 2022-23 cohort's rate ÷ the 2024-26 cohort's, with its 95% "
                          'interval from the same bootstrap; bold = the interval excludes 1. Cohorts grouped after '
                          'the review (docs/09 §12): descriptive'),
        'install_reading': ('Reading', 'in one year of data, install year and age move together: a peak on 2022-23 '
                            'installs fits a problem in that production or a failure peak at 2-4 years; earlier '
                            "tickets or IPA's change dates would tell which"),
        'share_ratio_cat': ('Share ratio', "a Category's share of under-4 machines' tickets \u00f7 its share of 4+ "
                            "machines' tickets of the same model (Mantel-Haenszel over "
                            f"{len(sup['support_models'])} models); the 12 most frequent Categories"),
        'repeat_interval': ('Line', f'95% interval of the repeat rate, bootstrap over accounts ({nb} draws)'),
        'share_repeats': ('Share', f"of all {b['repeats_30']:,} repeats; models (or types) with 100+ eligible index "
                          'tickets, the rest pooled'),
        'class_units': ('Rows', 'models (or telemetry types) with 50+ repeats within 30 days (repeats in brackets), '
                        'the rest pooled; No device match and Unknown shown apart; descriptive, not tested'),
        'matrix_models': ('Models', 'the four with the most repeats within 30 days; every model and telemetry type '
                          'is in rp_model_matrices.csv'),
        'random_timing': ('Random timing', "the repeat rate if each machine's tickets fell at random over its own "
                          'months in the period; it rises with tickets per machine'),
        'srr': ('Ratio', "observed ÷ random-timing repeats, relative to the fleet's "
                f"{b['fleet_observed_over_expected_30']:.2f}: " + (
                    'none differs after Benjamini-Hochberg (q < 0.05)' if not (b['models_above'] or b['models_below'])
                    else 'blue = above the fleet, navy = below (interval excludes 1, Benjamini-Hochberg q < 0.05)')
                + '; in brackets: not tested (the pooled rows, and the light-gray rows, which are not types)'),
    }


def items(keys):
    t = terms()
    return [t[k] for k in keys]
