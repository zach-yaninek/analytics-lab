#!/usr/bin/env python3
"""The IPA deck as a PDF with real customer names: the live deck's slides, one per page.

The live deck (the Slides artifact) shows customers as pseudonyms ('Customer NNN'). IPA gets a PDF with the real
names, built here, locally, into deliverables/ (gitignored); it is never committed. It is made from a downloaded copy
of the deck (deck.json and slides/<id>.html) and a map from each image's blob id to its local file, in three steps:
  1. Charts: an image whose file is viz/figures/slides/<stem>.png prints its real-name variant,
     deliverables/slides/<stem>_REALNAMES.png (drawn by viz/slides/run_all.py), when that exists. The swaps are
     listed; --require-swaps names the ones that must happen.
  2. Names: every 'Customer NNN' in every slide (visible text, alt text and speaker notes) becomes its name
     (names.substitute, HTML-escaped). Afterwards no pseudonym of any kind may remain.
  3. deck_pdf.js prints the slides with Chromium, one 1920 x 1080 px page each, after a fit pass that sets text 1 px
     smaller at a time where it no longer fits its box (a longer name in a Key Takeaway, say).
No message names a customer: only pseudonyms, slide ids, file names and counts.

Checks on the built PDF (printed as counts; any failure stops the build and leaves the existing PDF as it was):
  - pages: one per slide, in deck.json's order (each page carries its slide's title in the PDF's text);
  - images: every image loaded (naturalWidth above 0); the swaps made (each variant a different file from its
    pseudonymous chart), and any required one missing;
  - fit: the adjustments made (slide id, tag, from px, to px); no text, box or slide still overflowing;
  - privacy: no pseudonym of any kind in the PDF's text (pdftotext), and on each page the names of the deck's
    customers occur exactly as often as pseudonyms are substituted into that slide's visible text (speaker notes
    removed, attributes ignored). Names are compared with whitespace removed, so a name that wraps across lines
    still counts. Every customer of the deck must have a name (blank or missing fails before anything is built).

Twin build (--twin OUT_DIR): twin names (names.twin: each placeholder has its real name's length and word lengths)
and the twin charts <stem>_TWIN.png from --twin-charts (default OUT_DIR), to check the layout without seeing a real
name; its text must also hold no real name. Pseudonymous build (--pseudo OUT_DIR): the live deck as it is (no names,
the pseudonymous charts), for comparison; its text must hold every visible pseudonym and no real name.

Inputs:
  --deck DIR                                     the deck: deck.json ("order", "title") and slides/<id>.html
  --assets MAP                                   JSON {blob id: local file} for every /_blob/<id> the slides use
                                                 (a relative path is read from the map's folder)
  data/private/fx_private_customer_names.csv     real names, through names.real_names() (gitignored)
  deliverables/slides/<stem>_REALNAMES.png       the real-name slide charts (real build)
  viz/deliverables/deck_pdf.js                   the printer (Node with Playwright)
Outputs:
  deliverables/IPA_Update_Deck_REALNAMES.pdf     the real deck
  OUT_DIR/IPA_Update_Deck_TWIN.pdf               --twin
  OUT_DIR/IPA_Update_Deck_PSEUDO.pdf             --pseudo
Temporary files (the substituted slides, the printed document, the PDF before its checks) go to a new folder under
--tmp (default deliverables/, which is gitignored) and are deleted at the end.

Requires Node with Playwright (Chromium) and poppler's pdfinfo and pdftotext.

Run:  cd /home/user/analytics-lab && python3 -I viz/deliverables/build_deck_pdf.py --deck DIR --assets MAP \\
          [--twin OUT_DIR [--twin-charts DIR] | --pseudo OUT_DIR] [--require-swaps STEM,...] [--tmp DIR]
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # python3 -I leaves the script directory off sys.path
import names  # noqa: E402

DECK_JS = HERE / 'deck_pdf.js'
SLIDE_CHARTS = names.ROOT / 'viz' / 'figures' / 'slides'
REAL_CHARTS = names.DELIVERABLES / 'slides'
REAL_PDF = names.DELIVERABLES / 'IPA_Update_Deck_REALNAMES.pdf'
OUT_NAME = {'twin': 'IPA_Update_Deck_TWIN.pdf', 'pseudo': 'IPA_Update_Deck_PSEUDO.pdf'}
CHART_SUFFIX = {'real': '_REALNAMES', 'twin': '_TWIN'}
LABEL = {'real': 'real names', 'twin': 'twin names and charts: layout check',
         'pseudo': 'pseudonymous, as the live deck: fidelity check'}
BLOB = re.compile(r'/_blob/([0-9a-f]{32})')
TITLE_CHARS = 40  # the page-order check looks for this many characters of each slide's title (whitespace removed)


class BuildError(Exception):
    """A step or check failed; the message names pseudonyms, slide ids, file names and counts only."""


def fail(message):
    raise BuildError(message)


class Checks:
    def __init__(self):
        self.failed = []

    def __call__(self, name, ok, detail):
        print(f'  [{"ok" if ok else "FAIL"}] {name}: {detail}')
        if not ok:
            self.failed.append(name)


class SlideText(HTMLParser):
    """A slide's visible text (its text nodes outside <aside>, <script>, <style> and <title>; attributes are
    ignored) and its title (the first h1 or h2)."""
    HIDDEN = {'aside', 'script', 'style', 'title'}

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts, self.title_parts = [], []
        self.title_tag, self.title_done = None, False
        self.feed(source)
        self.close()
        self.visible = flat(' '.join(self.parts))
        self.title = flat(' '.join(self.title_parts))

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden += 1
        elif tag in ('h1', 'h2') and not self.hidden and self.title_tag is None and not self.title_done:
            self.title_tag = tag

    def handle_endtag(self, tag):
        if tag in self.HIDDEN and self.hidden:
            self.hidden -= 1
        elif tag == self.title_tag:
            self.title_tag, self.title_done = None, True

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
            if self.title_tag:
                self.title_parts.append(data)


def flat(text):
    """Text as compared: NFKC (a ligature reads as its letters), every whitespace run (line breaks too) one space."""
    return ' '.join(unicodedata.normalize('NFKC', text).split())


def bare(text):
    """flat() without any whitespace: a name or title wrapped across lines (or after a hyphen) still matches."""
    return ''.join(unicodedata.normalize('NFKC', text).split())


def redactor(*maps):
    """A function that puts each customer's pseudonym back in place of its name (as given, with whitespace runs as
    one space, or HTML-escaped), for any message that passes on another program's output."""
    pairs = set()
    for m in maps:
        for customer, name in m.items():
            name = str(name)
            for form in {name, ' '.join(name.split()), names.html_escape(name)}:
                if form.strip():
                    pairs.add((form, customer))
    pairs = sorted(pairs, key=lambda p: -len(p[0]))

    def redact(text):
        for name, customer in pairs:
            text = text.replace(name, customer)
        return text
    return redact


def load_assets(path):
    """{blob id: absolute local file} from the asset map."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as err:
        fail(f'asset map {path}: {err}')
    return {blob: (path.parent / f).resolve() for blob, f in raw.items()}


def choose_files(assets, used, mode, twin_charts):
    """The file each image prints: a slide chart's real-name (or twin) variant when it exists, else its own file.

    Returns ({blob: file}, {swapped chart stem: (its own file, the variant)}, every slide-chart stem the deck uses).
    """
    files, swaps, charts = {}, {}, set()
    for blob in sorted(used):
        f = assets[blob]
        if f.parent == SLIDE_CHARTS and f.suffix == '.png':
            charts.add(f.stem)
            if mode in CHART_SUFFIX:
                variant = (REAL_CHARTS if mode == 'real' else twin_charts) / f'{f.stem}{CHART_SUFFIX[mode]}.png'
                if variant.is_file():
                    files[blob] = variant
                    swaps[f.stem] = (f, variant)
                    continue
        files[blob] = f
    return files, dict(sorted(swaps.items())), sorted(charts)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_printer(work, pdf, redact):
    """deck_pdf.js on the working copy; returns its report (printed as counts and slide ids)."""
    r = subprocess.run(['node', str(DECK_JS), str(work), str(work / 'assets.json'), str(pdf)], capture_output=True,
                       encoding='utf-8')
    report = None
    lines = r.stdout.strip().splitlines()
    if lines:
        try:
            report = json.loads(lines[-1])
        except ValueError:
            report = None
    if report:
        img = report.get('images') or {}
        icons = ', '.join(f'{k} {v}' for k, v in sorted(report.get('icons', {}).items())) or 'none'
        print(f'  step 3: printed {report.get("sections")} sections for {report.get("slides")} slides; images '
              f'{img.get("loaded")} of {img.get("count")} loaded; icons drawn: {icons}; {report.get("shapes")} '
              f'header dots')
    if report and r.returncode != 0:  # on success the checks below list the fit adjustments
        for f in (report.get('images') or {}).get('failed', []):
            print(f'    image not loaded: slide {f["slide"]}, {redact(f["file"])}')
        fit = report.get('fit') or {}
        for a in fit.get('adjustments', []):
            print(f'    fit: slide {a["slide"]} <{a["tag"]}> {a["from"]:g} -> {a["to"]:g} px')
        for u in fit.get('unresolved', []):
            sizes = f' ({u["from"]:g} -> {u["to"]:g} px)' if 'from' in u else ''
            print(f'    fit FAILED: slide {u["slide"]} <{u["tag"]}>{sizes}: {u["why"]}')
        for e in report.get('errors', []):
            print(f'    printer error: {redact(e)}')
    if r.returncode != 0 or not report:
        fail(f'deck_pdf.js failed (exit {r.returncode}): {redact(r.stderr.strip())[-1500:] or "see the report above"}')
    return report


def pdf_pages(pdf):
    """Page count (pdfinfo) and each page's text (pdftotext, in memory only)."""
    info = subprocess.run(['pdfinfo', str(pdf)], capture_output=True, encoding='utf-8')
    m = re.search(r'^Pages:\s+(\d+)', info.stdout, re.M)
    if info.returncode != 0 or not m:
        fail(f'pdfinfo could not read the PDF (exit {info.returncode})')
    text = subprocess.run(['pdftotext', '-enc', 'UTF-8', str(pdf), '-'], capture_output=True, encoding='utf-8')
    if text.returncode != 0:
        fail(f'pdftotext could not read the PDF (exit {text.returncode})')
    pages = int(m.group(1))
    return pages, text.stdout.split('\f')[:pages]  # pdftotext ends every page with a form feed


def found(text, name_map):
    """How many times the map's names occur in text, compared with whitespace removed (a count, never a name)."""
    return names.names_found(bare(text), {k: b for k, v in name_map.items() if (b := bare(str(v)))})


def build(mode, deck_dir, assets_path, out_dir=None, twin_charts=None, require=(), tmp_parent=None):
    deck_dir = Path(deck_dir)
    try:
        deck = json.loads((deck_dir / 'deck.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as err:
        fail(f'{deck_dir / "deck.json"}: {err}')
    order = deck.get('order') or fail('deck.json has no "order"')
    if len(set(order)) != len(order):
        fail('deck.json\'s "order" lists a slide twice')
    slides = {}
    for sid in order:
        path = deck_dir / 'slides' / f'{sid}.html'
        if not path.is_file():
            fail(f'slide {sid}: {path} not found')
        slides[sid] = path.read_text(encoding='utf-8')
    assets = load_assets(assets_path)
    used = {blob for source in slides.values() for blob in BLOB.findall(source)}
    unmapped = sorted(used - set(assets))
    if unmapped:
        fail(f'{len(unmapped)} image blob(s) not in the asset map: {", ".join(unmapped)}')
    absent = sorted(blob for blob in used if not assets[blob].is_file())
    if absent:
        fail(f'{len(absent)} mapped image file(s) not found, for blob(s) {", ".join(absent)}')

    real_names = names.real_names()
    customers = sorted({c for source in slides.values() for c in names.PSEUDONYM.findall(source)})
    if mode != 'pseudo':
        if real_names is None:
            fail(f'{names.NAMES_FILE.relative_to(names.ROOT)} not found: no names for the deck')
        unusable = [c for c in customers if not isinstance(real_names.get(c), str) or not real_names[c].strip()]
        if unusable:  # absent, blank or not text (an empty cell reads as NaN, which substitute() would print)
            fail(f'{len(unusable)} customer(s) of the deck without a usable name: {", ".join(unusable)}')
    twin_names = names.twin(real_names) if real_names else None
    customer_names = {'real': real_names, 'twin': twin_names}.get(mode)
    redact = redactor(*(m for m in (real_names, twin_names) if m))
    print(f'IPA deck PDF ({LABEL[mode]}): {len(order)} slides from {deck_dir}')

    # 1. Charts
    files, swaps, charts = choose_files(assets, used, mode, Path(twin_charts or out_dir or '.'))
    unknown = sorted(set(require) - set(charts))
    if unknown:
        fail(f'--require-swaps: {", ".join(unknown)} not among the deck\'s slide charts')
    same = [stem for stem, (own, variant) in swaps.items() if sha256(own) == sha256(variant)]
    if same:
        fail(f'{", ".join(same)}: the {CHART_SUFFIX[mode][1:]} file is the pseudonymous chart byte for byte')
    if mode != 'pseudo':
        print(f'  step 1: {len(files)} image files; {len(swaps)} slide chart(s) -> their {CHART_SUFFIX[mode][1:]} '
              f'variant: {", ".join(swaps) or "none"}')
    if mode == 'twin':
        real_only = [s for s in charts if (REAL_CHARTS / f'{s}_REALNAMES.png').is_file() and s not in swaps]
        if real_only:
            print(f'    note: {len(real_only)} chart(s) with a real-name variant but no twin chart, shown '
                  f'pseudonymous in the twin deck: {", ".join(real_only)}')

    # 2. Names
    printed, expected, titles = {}, {}, {}
    n_sub = 0
    for sid in order:
        source = slides[sid]
        shown = SlideText(source).visible
        if mode == 'pseudo':
            printed[sid], expected[sid] = source, names.pseudonyms_left(shown)
        else:
            try:
                printed[sid], n = names.substitute(source, customer_names, escape=names.html_escape)
            except KeyError as err:
                fail(f'slide {sid}: {err.args[0]}')
            n_sub += n
            expected[sid] = len(names.PSEUDONYM.findall(shown))  # the substitutions that land in visible text
            # visible text catches a pseudonym split by markup; the unescaped HTML one in attributes or notes
            after, whole = SlideText(printed[sid]).visible, flat(html.unescape(printed[sid]))
            left_shown, left_all = names.pseudonyms_left(after), names.pseudonyms_left(whole)
            if left_shown or left_all:
                kinds = sorted({p for text in (after, whole)
                                for p in names.PSEUDONYM.findall(text) + names.OTHER_PSEUDONYMS.findall(text)})
                fail(f'slide {sid}: pseudonyms left after substitution, {left_shown} in visible text and {left_all} in '
                     f'the HTML (split by markup or entities, or not a customer): {", ".join(kinds)}')
        titles[sid] = bare(SlideText(printed[sid]).title)
    if mode != 'pseudo':
        print(f'  step 2: {n_sub} pseudonyms -> names ({len(customers)} customers: {", ".join(customers)}); '
              f'{sum(expected.values())} in visible text; 0 pseudonyms left')

    tmp_parent = Path(tmp_parent) if tmp_parent else names.DELIVERABLES
    tmp_parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='deck_', dir=tmp_parent))
    try:
        (work / 'slides').mkdir()
        for sid in order:
            (work / 'slides' / f'{sid}.html').write_text(printed[sid], encoding='utf-8')
        (work / 'deck.json').write_text(json.dumps({'title': deck.get('title', ''), 'order': order}),
                                        encoding='utf-8')
        (work / 'assets.json').write_text(json.dumps({b: str(f) for b, f in files.items()}), encoding='utf-8')
        pdf = work / (REAL_PDF.name if mode == 'real' else OUT_NAME[mode])

        # 3. Print
        report = run_printer(work, pdf, redact)
        n_pages, page_text = pdf_pages(pdf)

        check = Checks()
        check('pages', n_pages == len(order) == len(page_text), f'{n_pages} pages for {len(order)} slides')
        misplaced = [sid for sid, text in zip(order, page_text) if titles[sid][:TITLE_CHARS] not in bare(text)]
        check('page order', len(page_text) == len(order) and not misplaced,
              f'{len(order) - len(misplaced)} of {len(order)} pages carry their slide\'s title'
              + (f'; not found: {", ".join(misplaced)}' if misplaced else ''))
        img = report['images']
        check('images', img['count'] == img['loaded'] and not img['failed'],
              f'{img["loaded"]} of {img["count"]} images loaded ({len(files)} files)')
        fit = report['fit']
        check('fit', not fit['unresolved'],
              f'{fit["checked"]} text elements checked; {len(fit["adjustments"])} set smaller'
              + ''.join(f'; {a["slide"]} <{a["tag"]}> {a["from"]:g}->{a["to"]:g} px' for a in fit['adjustments']))
        if mode != 'pseudo':
            missing = sorted(set(require) - set(swaps))
            check('swaps', not missing,
                  f'{len(swaps)} made ({", ".join(swaps) or "none"}), each a different file from its pseudonymous '
                  f'chart; required {len(require)}' + (f'; MISSING: {", ".join(missing)}' if missing else ''))

        if mode == 'pseudo':
            seen = {sid: names.pseudonyms_left(flat(text)) for sid, text in zip(order, page_text)}
            off = [sid for sid in order if seen.get(sid) != expected[sid]]
            check('pseudonyms', not off, f'{sum(seen.values())} in the PDF text, {sum(expected.values())} in the '
                  f'slides\' visible text' + (f'; differ on {", ".join(off)}' if off else ''))
        else:
            left = names.pseudonyms_left(flat('\n'.join(page_text)))
            check('privacy: pseudonyms', left == 0, f'{left} pseudonyms in the PDF text')
            # the deck's own customers: another customer's name inside one of theirs would inflate a full-table count
            deck_names = {c: customer_names[c] for c in customers}
            seen = {sid: found(text, deck_names) for sid, text in zip(order, page_text)}
            off = [f'{sid} ({seen.get(sid)} vs {expected[sid]})' for sid in order if seen.get(sid) != expected[sid]]
            check('privacy: names', not off,
                  f'{sum(seen.values())} names in the PDF text, {sum(expected.values())} substituted into visible '
                  f'text ({", ".join(f"{sid} {n}" for sid, n in expected.items() if n) or "none"})'
                  + (f'; differ on {", ".join(off)}' if off else ''))
        if mode != 'real' and real_names:
            leaks = found('\n'.join(page_text), real_names)
            check('privacy: real names', leaks == 0, f'{leaks} real names in the PDF text')
        if check.failed:
            fail(f'{len(check.failed)} check(s) failed: {", ".join(check.failed)}; '
                 + ('the existing PDF is unchanged' if mode == 'real' else 'no PDF written'))

        out = REAL_PDF if mode == 'real' else Path(out_dir) / OUT_NAME[mode]
        out.parent.mkdir(parents=True, exist_ok=True)
        part = out.with_name(out.name + '.part')
        shutil.copyfile(pdf, part)
        os.replace(part, out)
        print(f'  wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {n_pages} pages)')
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--deck', metavar='DIR', required=True, help='the deck: deck.json and slides/<id>.html')
    parser.add_argument('--assets', metavar='MAP', required=True, help='JSON {blob id: local file} for its images')
    which = parser.add_mutually_exclusive_group()
    which.add_argument('--twin', metavar='OUT_DIR', help=f'build the twin deck (twin names and charts) into '
                       f'OUT_DIR/{OUT_NAME["twin"]} instead of the real deck')
    which.add_argument('--pseudo', metavar='OUT_DIR', help=f'build the pseudonymous deck (as live) into '
                       f'OUT_DIR/{OUT_NAME["pseudo"]} instead of the real deck')
    parser.add_argument('--twin-charts', metavar='DIR', help='folder of the twin slide charts <stem>_TWIN.png '
                        '(default: the --twin OUT_DIR)')
    parser.add_argument('--require-swaps', metavar='STEMS', default='',
                        help='comma-separated slide-chart stems that must print their real-name (or twin) variant')
    parser.add_argument('--tmp', metavar='DIR', help='folder for the temporary build folder (default: deliverables/)')
    args = parser.parse_args()
    require = [s.strip() for s in args.require_swaps.split(',') if s.strip()]
    if args.twin_charts and not args.twin:
        parser.error('--twin-charts goes with --twin')
    if require and args.pseudo:
        parser.error('--require-swaps goes with the real or the twin build')
    mode = 'twin' if args.twin else 'pseudo' if args.pseudo else 'real'
    try:
        build(mode, args.deck, args.assets, out_dir=args.twin or args.pseudo, twin_charts=args.twin_charts,
              require=require, tmp_parent=args.tmp)
    except BuildError as err:
        print(f'FAILED: {err}')
        sys.exit(1)


if __name__ == '__main__':
    main()
