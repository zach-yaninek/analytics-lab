# viz: charts in the IPA style

Every chart in the project, drawn with plain matplotlib in one shared style. You can use the style on your own plots
in one of two ways: a style sheet for a quick restyle, or a helper module that also adds the title band and
footer.

```
viz/
  style/
    ipa.mplstyle        matplotlib style sheet: colours, fonts, grid, spines, legend
    ipa_style.py        the sheet + page layout (title band, footer), palette constants, save()
  high_ticket/          high-ticket-machine charts (docs/05); htm.py = their data and term definitions
  zac_notebook/         Zac's 10 notebook figures, rebuilt in this style; zac_data.py = data and definitions
  slides/               a simplified 16:9 version of every chart for PowerPoint; slides.py = shared page setup
  figures/              rendered PNGs (pseudonymous)
    slides/             the slide versions and speaker_notes.md
  run_all.py            redraw everything and run the checks
```

## Use the style on your own plots

**1. Style sheet only** (one line, works with existing plotting code):

```python
import matplotlib.pyplot as plt
plt.style.use('viz/style/ipa.mplstyle')   # path from the repo root

fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(['A', 'B', 'C'], [12, 7, 3])
ax.grid(axis='y')                          # grid is off by default; switch it on per axis
ax.set_title('Model A has the most tickets')
```

This gives the warm off-white surface, gray ink, hairline grid, no box and no tick marks. Series take the palette
colours in order: blue, orange, aqua, then grays.

**2. Full page layout** (what every chart here uses):

```python
import sys
sys.path.insert(0, 'viz/style')
import ipa_style as S

fig, ax = S.figure(10, 5)                  # the style sheet + constrained layout
ax.barh(['Model C', 'Model B', 'Model A'], [3, 7, 12], height=0.5,
        color=[S.GRAY_LIGHT, S.GRAY_LIGHT, S.BLUE])
S.style_axes(ax, grid='x', baseline='left')
ax.set_xlabel('Unplanned tickets')
S.frame(fig, 'Model A has the most tickets: 12 of 22',            # title: state the finding
        'Unplanned tickets by model, Aug 2025 to Aug 2026.',     # subtitle: population and period
        notes=['Source: my_table.csv.'],                          # footer, muted
        definitions=['Unplanned = every ticket except planned work, cancelled requests and duplicate cases.'])
S.save(fig, 'my_chart.png')                # 150 dpi
```

`frame()` puts the title and subtitle above the plot and the definitions and notes below it. It reserves space for
both, so nothing overlaps the axes. Definitions are drawn first in the footer, in darker ink, one text block each.
The other helpers are `pct()`, `pct_axis()` and `thousands_axis()` for number formats, and `check()` for "this
number on the chart equals that number in the data" assertions.

## Style rules the charts follow

- **Titles state the finding** ("Deposit Door is the most common recorded issue: 16% of unplanned tickets"), not
  the topic. Compute the numbers in the title from the data.
- **Define terms on the chart.** If a chart uses a defined term (chronic outlier, workload-outsized,
  machine-month, unplanned, repeat contact, …), its definition is the first footer line. (Slide versions move the
  definitions to their speaker notes instead; see below.)
- **Emphasis is blue, context is gray.** Colour only what the title talks about.
- **At most three categorical colours:** blue `#2a78d6`, orange `#eb6834`, aqua `#1baf7a`, in that order. They are
  validated as distinguishable on this surface. Aqua is light, so every aqua mark needs a label or legend entry.
- **Ordered values use one hue:** the blue ramp `BLUE_RAMP`, light to dark, as in the heatmaps.
- **Thin marks, labelled directly:** bars about 22 px thick, lines 2 px, value labels at the bar ends instead of
  heavy axes, one axis per chart.
- **Note the source and the caveats** in the muted footer lines.
- **Pseudonyms only** in the repo: Customer NNN, M#####, S#####. A real-name version of a chart goes to
  `deliverables/` (gitignored) and is never committed.

| Token | Hex | Use |
|---|---|---|
| `SURFACE` | `#fcfcfb` | background |
| `INK` / `INK2` / `MUTED` | `#0b0b0b` / `#52514e` / `#898781` | title / subtitle, labels, definitions / ticks, notes |
| `GRID` / `BASE` | `#e1e0d9` / `#c3c2b7` | hairline grid / baseline spine |
| `BLUE` | `#2a78d6` | emphasis, first series |
| `ORANGE`, `AQUA` | `#eb6834`, `#1baf7a` | second and third series |
| `GRAY_LIGHT`, `GRAY` | `#c3c2b7`, `#898781` | context marks |
| `BLUE_RAMP` | `#cde2fb` → `#104281` | ordered values (12 steps) |

## The charts

| Script | Figure |
|---|---|
| `high_ticket/htm_01_concentration_curve.py` | How concentrated tickets are across devices, against chance |
| `high_ticket/htm_02_tickets_per_machine.py` | Tickets per machine, with the workload-outsized threshold |
| `high_ticket/htm_03_observed_vs_expected.py` | Observed vs expected tickets per device, by outlier class |
| `high_ticket/htm_04_model_mix.py` | Model mix of workload-outsized vs other machines |
| `high_ticket/htm_05_episode_followups.py` | Follow-up tickets within 3, 7 and 14 days |
| `high_ticket/htm_06_pre_ticket.py` | Telemetry in the 30 days before tickets (two figures) |
| `high_ticket/htm_07_chronic_outliers_by_customer.py` | Chronic outliers by customer (+ real-name variant) |
| `high_ticket/htm_08_chronic_categories_heatmap.py` | Top ticket categories for each chronic outlier |
| `high_ticket/htm_09_tickets_by_type.py` | Raw ticket counts by model and by telemetry type (two figures) |
| `high_ticket/htm_10_ticket_rate_by_machine_type.py` | Tickets per 100 machine-months by telemetry type |
| `zac_notebook/zac_01_missing_fields.py` | Missing values per ticket field |
| `zac_notebook/zac_02_customer_workload.py` | Customers with the most tickets (+ real-name variant) |
| `zac_notebook/zac_03_model_workload.py` | Models with the most tickets |
| `zac_notebook/zac_04_issue_mix.py` | Most frequent recorded categories, unplanned tickets |
| `zac_notebook/zac_05_machine_type_rates.py` | Ticket rate per 100 active machine-months by machine type |
| `zac_notebook/zac_06_monthly_rates.py` | Monthly ticket and fault-code rates |
| `zac_notebook/zac_07_repeat_contact.py` | Repeat contact within 30 days, ten highest-volume models |
| `zac_notebook/zac_08_customer_concentration.py` | How concentrated tickets are across customers |
| `zac_notebook/zac_09_model_issue_heatmap.py` | Category mix of each model's unplanned tickets |
| `zac_notebook/zac_10_repeat_composition.py` | What repeat contacts are made of |

The `htm_*` charts read the outputs of `verification/high_ticket_machines.py`. The `zac_*` charts read the
committed reproductions of Zac's tables:
- `verification/outputs/repro_sql_*.csv`: his case-export SQL, run verbatim;
- `verification/outputs/db/db_*.csv`: his telemetry SQL, re-run on the full database.

Neither set needs the database. Only the real-name variants read the gitignored workbook.

## Slide versions

`slides/` redraws every chart above as a less busy version for PowerPoint, on the assumption that the presenter says
the definitions and caveats aloud. Each `slides/<chart>_slide.py` reads the same data and keeps the full chart's
title (the finding), marks, colours and fonts. What changes:

- **16:9 page** (10 × 5.625 in, 200 dpi): every slide scales the same when it fills a slide, so text sizes match
  across the deck.
- **One-line subtitle**: what is plotted, and when.
- **No footer**: no definitions, notes or sources on the chart. They go to `figures/slides/speaker_notes.md`, which
  lists for each slide the definitions and caveats its full chart prints, with the numbers computed from the data.
- **Fewer labels in the plot**: no counts in legends and axis labels, value labels without the secondary number
  (e.g. counts but not shares), secondary annotations dropped. Each script's docstring says what it leaves out.
- **Fewer rows where a slide cannot hold them**: chart 7 shows the customers with 3 or more chronic outliers (the full
  chart: 2 or more), chart 8 the 10 chronic outliers with the most tickets (the full chart: 30).

The slides keep the full charts' file names, in `figures/slides/`. The full charts remain the reference: when a
number on a slide is questioned, the full chart's footer has the answer.

`slides/run_all.py` checks the numbers as the full charts do, and also that every slide's title is drawn on its full
chart (so both state the same finding with the same numbers), that every term a slide uses is defined in its speaker
notes, and that no real customer name appears on a pseudonymous slide or in the notes. The real-name variants of
charts 7 and zac_02 go to `deliverables/` (gitignored) with the privacy warning as a muted footer line.

To change the page size or resolution for a different slide layout, edit `WIDTH`, `HEIGHT` and `DPI` in
`slides/slides.py`; `S.save(fig, path, dpi=...)` takes the resolution for any chart.

## Running

```bash
python3 -I viz/run_all.py                                  # every chart, then the checks
python3 -I viz/high_ticket/run_all.py                      # one section
python3 -I viz/zac_notebook/zac_04_issue_mix.py            # one chart
python3 -I viz/slides/run_all.py                           # the slide versions and their speaker notes
python3 -I viz/slides/zac_04_issue_mix_slide.py            # one slide
```

Each section's `run_all.py` runs three checks:
- **Numbers:** numbers drawn on the charts match the data (`check()` calls).
- **Definitions:** every chart that uses a defined term draws its definition.
- **Privacy:** no real customer name or serial appears on a pseudonymous figure.

A failed definition or privacy check stops the run with an error. The slides section runs the same three checks,
with the speaker notes standing in for the footer, plus the title check described under Slide versions.

**Requirements:** Python 3.12+, pandas, numpy and matplotlib. The real-name variants also need openpyxl and the
workbook in `data/raw/`.
