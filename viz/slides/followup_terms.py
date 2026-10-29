"""Definitions printed on the follow-up slide charts (sl_18 on; docs/09, docs/10), with the numbers they quote read from
verification/outputs/followups/followups_summary.json, so the wording on every chart is the same and the numbers are
the computed ones.

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
                'No Trouble Found': 'NTF', 'Monitoring': 'Monit.', 'Not categorised': 'No cat.', 'Other': 'Other'}

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


@lru_cache(maxsize=1)
def summary():
    return json.loads((FU / 'followups_summary.json').read_text())


def p_text(p, n_perm):
    """A permutation p-value as printed: below the smallest reachable value it reads '< 0.001'."""
    floor = 1 / (n_perm + 1)
    return '< 0.001' if p < 1.5 * floor else f'= {p:.3f}' if p < 0.01 else f'= {p:.2f}'


def terms():
    s = summary()
    f = s['facts']
    sup, a, b, sh = f['support'], f['part_a'], f['part_b'], f['shuffle']
    gaps = __import__('pandas').read_csv(FU / 'rp_same_by_gap.csv')
    lab = sh['label_permutation']
    return {
        'under4': ('Under 4 / 4+', "the machine's age at the midpoint of its months on IPA's list (Aug 2025 to Aug "
                   '2026); under 4 = the first three bars of slide 4 (<1, 1-2 and 2-4 years)'),
        'rate': ('Rate', 'unplanned tickets (all but planned work, cancelled requests and duplicates; No Trouble Found '
                 'stays in) per 100 installed machine-months: 6,750 tickets on 8,946 listed machines'),
        'request_group': ('Request type', "the ticket's Category grouped by IPA's Trouble Code; Monitoring = the "
                          "help desk's “Monitoring – Daily/Poll” tickets; Not categorised = no Category"),
        'crude': ('Not adjusted for model', 'most under-4 machines are 2.0 models, so this mixes age with design'),
        'share_ratio': ('Share ratio', "a type's share of under-4 machines' tickets ÷ its share of 4+ machines' "
                        f"tickets of the same model, pooled over the {len(sup['support_models'])} models with 100+ "
                        f"machine-months in each age group ({100 * sup['under4_share_support']:.0f}% of under-4 and "
                        f"{100 * sup['plus4_share_support']:.0f}% of 4+ tickets; Mantel-Haenszel); 1 = same mix"),
        'interval': ('Bar', '95% interval, bootstrap over accounts (2,000 draws)'),
        'perm_test': ('Test', 'under-4 and 4+ labels shuffled among machines of the same model, 2,000 times: the mix '
                      f"differs overall (p {p_text(a['global_p'], s['n_perm'])}); blue = differs after "
                      'Benjamini-Hochberg (q < 0.05)'),
        'cat_test': ('Tested', 'only Categories in groups that differ (' + ', '.join(
            g for g in a['groups_significant'] if g not in ('Monitoring', 'No Trouble Found')) + '); open = not tested'),
        'extra': ('Extra tickets', "under-4 machines' tickets minus what their months would give at 4+ machines' "
                  f"rates ({a['extra_tickets']:,.0f} in all). Ring: all of it; dot: the part within model (each "
                  "model's own 4+ rate); the gap is model mix, plus a few tickets on models outside the comparison"),
        'by_model': ('Cell', "share of the row's tickets; models with 30+ tickets in each age group. Mix test: labels "
                     "shuffled among the model's machines, Benjamini-Hochberg"),
        'telemetry_type': ('Telemetry type', "the clearView machine type of the device matched to the machine's "
                           'tickets; scrubex2.0-2, -3, -4 and -5 are LVD-Remote-2.0, LVRR-WP-2.0, MV-2.0 and '
                           'SV-48-2.0'),
        'halves': ('Gap', 'extra tickets per 100 under-4 machine-months within model, first half (Aug 2025 to 14 Feb '
                   '2026) vs second (15 Feb to Aug 2026); Categories picked by a rule fixed in advance: the largest '
                   'within-model excess over the year'),
        'fix_proof': ('Reading', 'a narrowing gap fits a fix but does not prove one: that needs the dates of design or '
                      'firmware changes'),
        'repeat': ('Repeat', 'the next unplanned ticket on the same machine opens within 30 days (7-day: within 7) of '
                   f"an index ticket opened before 2 Aug 2026 ({b['eligible']:,}); not necessarily a failed repair"),
        'pairing': ('Cell', "share of the row's repeats whose next ticket is of the column's type; row label: repeats "
                    "and the share of that type's tickets that repeat"),
        'pairs_gap': ('Pairs', 'every two unplanned tickets on one machine with a recorded Category, monitoring '
                      f"excluded ({int(gaps.pairs.sum()):,} pairs), by days apart; pairs 90+ days apart show the "
                      "machine's usual mix"),
        'label_test': ('Test', "each machine's Categories shuffled across its own tickets, 2,000 times: repeat pairs "
                       f"share a Category {100 * sh['observed_share']:.0f}% of the time vs "
                       f"{100 * lab['null_share']:.0f}% by chance (p {p_text(lab['p'], s['n_perm'])})"),
        'classes': ('Class', 'the first that applies: a Monitoring ticket, No Trouble Found or a blank Category '
                    'involved (one gray segment); same Category; same group, other Category; different group'),
        'repeat7': ('7-day follow-up', 'the next unplanned ticket on the same machine opens within 7 days of an index '
                    f"ticket opened before 2 Aug 2026 ({b['repeats_7']:,} of {b['eligible']:,}); not necessarily a "
                    'failed repair'),
        'other_groups': ('Other', 'Software, Operator error and Other together; No cat. = no Category; NTF = No '
                         'Trouble Found'),
        'share_ratio_cat': ('Share ratio', "a Category's share of under-4 machines' tickets \u00f7 its share of 4+ "
                            "machines' tickets of the same model (Mantel-Haenszel over "
                            f"{len(sup['support_models'])} models); the 12 most frequent Categories"),
        'support': ('Within model', "each model's own 4+ rate, on the "
                    f"{len(sup['support_models'])} models with 100+ machine-months in each age group"),
        'repeat_interval': ('Bar', '95% interval of the repeat rate, bootstrap over accounts (2,000 draws)'),
        'share_repeats': ('Share', f"of all {b['repeats_30']:,} repeats; models (or types) with 100+ eligible index "
                          'tickets, the rest pooled'),
        'class_units': ('Rows', 'models (or telemetry types) with 50+ repeats within 30 days; the rest pooled'),
        'matrix_models': ('Models', 'the four with the most repeats within 30 days; every model and telemetry type '
                          'is in rp_model_matrices.csv'),
        'random_timing': ('Random timing', "the repeat rate if each machine's tickets fell at random over its own "
                          'months in the period; it rises with tickets per machine'),
        'srr': ('Beyond chance', "observed ÷ random-timing repeats, relative to the fleet's "
                f"{b['fleet_observed_over_expected_30']:.2f}: " + (
                    'none differs after Benjamini-Hochberg (q < 0.05)' if not (b['models_above'] or b['models_below'])
                    else 'blue = above the fleet, navy = below (interval excludes 1, Benjamini-Hochberg q < 0.05)')),
    }


def items(keys):
    t = terms()
    return [t[k] for k in keys]
