#!/usr/bin/env python3
"""The IPA Word memo: docs/executive_summary.md with real customer names, as a Word document.

docs/executive_summary.md is the repository version: customers appear as pseudonyms ('Customer NNN'). IPA gets a
Word memo with the real names, built here, locally, into deliverables/ (gitignored); it is never committed. The memo's
Markdown is made from the repository version in five steps, in order. Each step fails loudly when it finds nothing
to change, and no message names a customer: only pseudonyms, counts and line numbers.
  1. The top note's opening ('Repository version. ... Supporting detail:') becomes the IPA version's note
     (IPA_NOTE); its bullet list stays.
  2. In "Charts by finding", the sentence on pseudonymous charts becomes REAL_CHARTS (matched whitespace-
     insensitively: it wraps across lines).
  3. Every 'Customer NNN' becomes its name (names.substitute, Markdown-escaped). A customer written any other way
     cannot be substituted, so the source is checked first: a plural ('Customers 171 and 029') or a customer's
     bare number next to its pseudonym fails the build. Afterwards no pseudonym of any kind may remain.
  4. Each chart image becomes an absolute path. The five customer charts (CUSTOMER_CHARTS) use their real-name
     PNGs, deliverables/<stem>_REALNAMES.png, drawn by their chart scripts (not redrawn here: a missing one fails).
     Every other chart must draw no customer: one with a real-name variant in deliverables/ fails.
  5. Each chart link [label](../viz/figures/X.png) becomes a link to X's caption in "Charts by finding" (bookmark
     fig_X) when X is drawn there, and plain 'label' otherwise.
pandoc's gfm reader parses the result to a JSON AST: gfm, not pandoc's own markdown, because the source starts its
lists right after a paragraph line (in the update boxes too), which pandoc's markdown reads as running text.
memo_docx.js then lays the AST out as a .docx with docx-js.

Checks on the built document (printed as counts; any failure stops the build and leaves the existing memo as it was):
  - list nesting: pandoc's list items (in order, with depth and kind) match the nesting of the list markers in the
    Markdown, and the document's numbered paragraphs (Word list level and format) match pandoc's items;
  - privacy: no pseudonym in the document's text (pandoc -t plain, and its AST) or anywhere in its XML parts, and
    the substituted names occur in its text exactly as often as they were substituted;
  - images: embedded images = Markdown images, each with its file's exact bytes in word/media; the real memo holds
    the five customer charts' REALNAMES files (sha256) and none of their pseudonymous versions, the twin the
    reverse; every internal link has its bookmark;
  - headings: every Markdown heading is a heading in the document, at the same level and in the same order;
  - numbers: every number token of the memo's text (23.6%, 1,574, 0.73, ...) occurs in the document's text as often
    (a mismatch is reported with the token and its lines in docs/executive_summary.md);
  - the docx skill's validate.py passes (for the real memo only its summary lines are printed: its details can
    quote document text; the twin build shows them).

Twin build (--twin OUT_DIR): the same memo with twin names (names.twin: each customer's placeholder has its real
name's length and word lengths) and the pseudonymous chart PNGs, to check the layout without seeing a real name.

Inputs:
  docs/executive_summary.md                      the repository version (pseudonymous)
  data/private/fx_private_customer_names.csv     real names, through names.real_names() (gitignored)
  viz/figures/<stem>.png                         the charts
  deliverables/<stem>_REALNAMES.png              the five customer charts with real names (real memo only)
  viz/deliverables/memo_docx.js                  AST -> .docx (Node with the docx package)
Outputs:
  deliverables/IPA_Executive_Summary.docx        the real memo; an existing one is first copied to
                                                 deliverables/IPA_Executive_Summary_previous.docx
  OUT_DIR/IPA_Executive_Summary_TWIN.docx        --twin only
Temporary files (the memo's AST and document, the unpacked document) go to a new folder under --tmp (default
deliverables/, which is gitignored) and are deleted at the end.

Requires pandoc 3 and Node with the docx package. The docx skill's scripts/office/validate.py (found under
~/.claude/skills, or set DOCX_VALIDATE to its path) is run when present and skipped, with a note, when not.

Run:  cd /home/user/analytics-lab && python3 -I viz/deliverables/build_memo.py [--twin OUT_DIR] [--tmp DIR]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # python3 -I leaves the script directory off sys.path
import names  # noqa: E402

SOURCE = names.ROOT / 'docs' / 'executive_summary.md'
FIGURES = names.ROOT / 'viz' / 'figures'
MEMO_JS = HERE / 'memo_docx.js'
MEMO = names.DELIVERABLES / 'IPA_Executive_Summary.docx'
PREVIOUS = names.DELIVERABLES / 'IPA_Executive_Summary_previous.docx'
TWIN_MEMO = 'IPA_Executive_Summary_TWIN.docx'
CUSTOMER_CHARTS = ('zac_02_customer_workload', 'fx_06_busiest_customers', 'fx_07_customer_funnel',
                   'fx_10_customer_persistence', 'fx_12_outlier_drivers')  # the charts that draw customers
READER = 'gfm'

NOTE_OPENING = re.compile(r'^> Repository version\..*?Supporting detail:', re.S | re.M)
IPA_NOTE = ('IPA version, with real customer names: for the project team and IPA only. The repository version '
            '(docs/executive_summary.md) uses pseudonyms. Supporting detail, in the project repository:')
CHARTS_SECTION = re.compile(r'^## Charts by finding$.*?(?=^## |\Z)', re.S | re.M)
PSEUDONYMOUS_CHARTS = ('Customer charts use pseudonyms; the real-name variants of zac_02, fx_06, fx_07, fx_10 and '
                       'fx_12 are drawn locally to `deliverables/` and are not committed.')
REAL_CHARTS = 'Customer charts show real customer names.'
IMAGE = re.compile(r'!\[([^\]\n]*)\]\(\.\./viz/figures/(\w+)\.png\)')
CHART_LINK = re.compile(r'(?<!!)\[([^\]\n]+)\]\(\.\./viz/figures/(\w+)\.png\)')
RELATIVE_TARGET = re.compile(r'\]\(((?!#|<?/|https?:|mailto:)[^)\s]*)')  # a link or image target still relative
PLURAL = re.compile(r'\bCustomers \d{3}\b')
NUMBER = re.compile(r'\d+(?:[.,]\d+)*%?')
LIST_MARKER = re.compile(r'([-*+]|\d{1,9}[.)])( +|$)')
QUOTE_PREFIX = re.compile(r'((?:> ?)*)(.*)')
BOOKMARK = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,39}')  # Word's rule for bookmark names
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


class BuildError(Exception):
    """A step or check failed; the message names pseudonyms, counts and line numbers only."""


def fail(message):
    raise BuildError(message) from None  # no chained traceback: it could quote the document


def bookmark(stem):
    mark = f'fig_{stem}'
    if not BOOKMARK.fullmatch(mark):
        fail(f'chart {stem}: no valid Word bookmark name (letters, digits, _; at most 40 characters)')
    return mark


def line_of(text, pos):
    return text.count('\n', 0, pos) + 1


def lines_with(text, pattern):
    return sorted({line_of(text, m.start()) for m in pattern.finditer(text)})


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(cmd, what, redact, **kw):
    """Run a command; on failure report its exit code and its error output with any name replaced."""
    r = subprocess.run([str(c) for c in cmd], capture_output=True, encoding='utf-8', check=False, **kw)
    if r.returncode != 0:
        fail(f'{what} failed (exit {r.returncode}): {redact(r.stderr.strip())[-1500:]}')
    return r.stdout


def redactor(*maps):
    """A function that puts each customer's pseudonym back in place of its name (real or twin), for messages."""
    pairs = set()
    for m in maps:
        for customer, name in m.items():
            for form in {str(name), ' '.join(str(name).split())}:
                if form.strip():
                    pairs.add((form, customer))
    pairs = sorted(pairs, key=lambda p: -len(p[0]))

    def redact(text):
        for name, customer in pairs:
            text = text.replace(name, customer)
        return text
    return redact


# -----------------------------------------------------------------------------------------------------------------
# The five steps: repository Markdown -> the memo's Markdown
# -----------------------------------------------------------------------------------------------------------------
def step_note(md):
    """1. The first block quote's opening becomes the IPA version's note; its bullet list stays."""
    first_quote = next((i for i, line in enumerate(md.splitlines(), 1) if line.startswith('>')), None)
    m = NOTE_OPENING.search(md)
    if m is None or line_of(md, m.start()) != first_quote:
        fail("step 1: the first block quote does not open with 'Repository version. ... Supporting detail:'")
    if any(not line.startswith('>') for line in m.group(0).splitlines()):
        fail('step 1: the note\'s opening runs outside its block quote')
    print(f'  step 1: top note opening ({len(m.group(0).splitlines())} lines) -> the IPA version\'s note')
    return md[:m.start()] + '> ' + IPA_NOTE + md[m.end():]


def step_charts_sentence(md):
    """2. In "Charts by finding", the sentence on pseudonymous charts becomes REAL_CHARTS."""
    section = CHARTS_SECTION.search(md)
    if section is None:
        fail('step 2: no "## Charts by finding" section')
    sentence = re.compile(r'\s+'.join(map(re.escape, PSEUDONYMOUS_CHARTS.split())))
    found = list(sentence.finditer(md, section.start(), section.end()))
    if len(found) != 1:
        fail(f'step 2: the sentence on pseudonymous charts occurs {len(found)} times in "Charts by finding", '
             f'not once')
    m = found[0]
    print(f'  step 2: "Charts by finding" sentence on pseudonymous charts (line {line_of(md, m.start())}) -> '
          f'"{REAL_CHARTS}"')
    return md[:m.start()] + REAL_CHARTS + md[m.end():]


def paragraphs(text):
    """(first line, text) of each paragraph or list item: split at blank lines and at list markers."""
    out, start, buf = [], 1, []
    for i, line in enumerate(text.splitlines(), 1):
        body = QUOTE_PREFIX.match(line).group(2)
        if not body.strip() or LIST_MARKER.match(body, len(body) - len(body.lstrip(' '))):
            if buf:
                out.append((start, '\n'.join(buf)))
            buf, start = ([], i + 1) if not body.strip() else ([line], i)
        else:
            buf.append(line)
    if buf:
        out.append((start, '\n'.join(buf)))
    return out


def customer_forms(source):
    """Customers written so that names.substitute cannot replace them: plurals, and a customer's bare number in a
    paragraph that names the customer (e.g. '... Customer 029 ... 029 is the busiest'). Returns messages."""
    problems = []
    plural = lines_with(source, PLURAL)
    if plural:
        problems.append(f'{len(plural)} plural customer reference(s) ("Customers NNN ...") on line(s) '
                        f'{", ".join(map(str, plural))}')
    for first, text in paragraphs(source):
        numbers = {m.group(1) for m in names.PSEUDONYM.finditer(text)}
        rest = names.PSEUDONYM.sub('Customer ###', text)
        for number in sorted(numbers):
            for m in re.finditer(rf'(?<![\w.,]){number}(?!\w|[.,]\d)', rest):
                problems.append(f'Customer {number} written as a bare "{number}" on line '
                                f'{first + rest.count(chr(10), 0, m.start())}')
    return problems


def step_names(md, customer_names, source):
    """3. Every 'Customer NNN' becomes its name; returns (md, substitutions, the pseudonyms substituted)."""
    problems = customer_forms(source)
    if problems:
        fail('step 3: customers written in a form that cannot be substituted (write each as "Customer NNN") in '
             'docs/executive_summary.md: ' + '; '.join(problems))
    used = names.found(md)
    if not used:
        fail('step 3: no "Customer NNN" to substitute')
    try:
        md, count = names.substitute(md, customer_names, escape=names.md_escape)
    except KeyError as err:  # names pseudonyms only
        fail(f'step 3: {err.args[0]}')
    left = names.pseudonyms_left(md)
    if left:
        fail(f'step 3: {left} pseudonym(s) left after substitution')
    print(f'  step 3: {count} pseudonyms -> names ({len(used)} customers: {", ".join(used)}); 0 pseudonyms left')
    return md, count, used


def step_images(md, real):
    """4. Chart images -> absolute paths (the real memo's customer charts: their REALNAMES PNGs).

    Returns (md, embedded stems in order, image files in order)."""
    stems, files = [], []

    def put(m):
        alt, stem = m.groups()
        variant = names.DELIVERABLES / f'{stem}_REALNAMES.png'
        if stem in CUSTOMER_CHARTS:
            path = variant if real else FIGURES / f'{stem}.png'
        elif variant.exists():
            fail(f'step 4: {stem} has a real-name variant in deliverables/ but is not in CUSTOMER_CHARTS')
        else:
            path = FIGURES / f'{stem}.png'
        if not path.exists():
            fail(f'step 4: chart {path.relative_to(names.ROOT)} not found')
        stems.append(stem)
        files.append(path)
        return f'![{alt}](<{path}> "{bookmark(stem)}")'
    md = IMAGE.sub(put, md)
    if not stems:
        fail('step 4: no chart images')
    if len(set(stems)) != len(stems):
        fail('step 4: a chart is drawn twice (its caption bookmark would not be unique)')
    customer = [s for s in stems if s in CUSTOMER_CHARTS]
    print(f'  step 4: {len(stems)} chart images -> absolute paths; {len(customer)} customer charts '
          f'({"REALNAMES" if real else "pseudonymous"} PNGs), {len(stems) - len(customer)} without customers')
    return md, stems, files


def step_links(md, embedded):
    """5. Chart links -> links to the chart's caption when it is drawn in "Charts by finding", else plain text."""
    counts = Counter()

    def put(m):
        label, stem = m.groups()
        if stem in embedded:
            counts['internal'] += 1
            return f'[{label}](#{bookmark(stem)})'
        counts['plain'] += 1
        return label
    md = CHART_LINK.sub(put, md)
    if not counts:
        fail('step 5: no chart links')
    relative = RELATIVE_TARGET.findall(md)
    if relative:
        fail(f'step 5: {len(relative)} link or image target(s) still relative, which a Word document cannot '
             f'follow: {", ".join(relative[:5])}')
    print(f'  step 5: {sum(counts.values())} chart links -> {counts["internal"]} links to a chart caption, '
          f'{counts["plain"]} plain text')
    return md, counts['internal']


# -----------------------------------------------------------------------------------------------------------------
# Reading the Markdown, the AST and the document for the checks
# -----------------------------------------------------------------------------------------------------------------
def markdown_list_items(md):
    """(depth, kind) of each list item from the list markers' indentation, by CommonMark's rule: an item nests in
    the open item whose content column its marker reaches. A block quote, a heading, a table row, or an unindented
    line after a blank line closes the lists."""
    items, open_items, quote, blank = [], [], None, False
    for line in md.splitlines():
        prefix, body = QUOTE_PREFIX.match(line).groups()
        if prefix.replace(' ', '') != quote:
            open_items, quote = [], prefix.replace(' ', '')
        if not body.strip():
            blank = True
            continue
        indent = len(body) - len(body.lstrip(' '))
        marker = LIST_MARKER.match(body, indent)
        if marker:
            while open_items and indent < open_items[-1]:
                open_items.pop()
            items.append((len(open_items), 'number' if marker.group(1)[0].isdigit() else 'bullet'))
            open_items.append(indent + len(marker.group(1)) + max(1, len(marker.group(2))))
        elif body.startswith(('#', '|')) or (blank and open_items and indent < open_items[0]):
            open_items = []
        blank = False
    return items


def ast_list_items(blocks, depth=0, out=None):
    """(depth, kind) of each list item in a pandoc AST, in document order (lists in quotes and tables included)."""
    out = [] if out is None else out
    for b in blocks:
        t, c = b['t'], b.get('c')
        if t in ('BulletList', 'OrderedList'):
            for item in (c if t == 'BulletList' else c[1]):
                out.append((depth, 'bullet' if t == 'BulletList' else 'number'))
                ast_list_items(item, depth + 1, out)
        elif t == 'BlockQuote':
            ast_list_items(c, depth, out)
        elif t == 'Div':
            ast_list_items(c[1], depth, out)
        elif t == 'Table':
            for cell in table_cells(c):
                ast_list_items(cell, depth, out)
    return out


def table_cells(c):
    """The block lists of every cell of a pandoc table (head, bodies, foot)."""
    _, _, _, head, bodies, foot = c
    rows = head[1] + [r for body in bodies for r in body[2] + body[3]] + foot[1]
    return [cell[4] for row in rows for cell in row[1]]


def ast_text(blocks, alt=True):
    """Text of pandoc blocks, a line per paragraph; link targets left out, image alt text only when alt."""
    lines = []

    def inline(xs):
        out = []
        for x in xs:
            t, c = x['t'], x.get('c')
            if t == 'Str':
                out.append(c)
            elif t in ('Space', 'SoftBreak', 'LineBreak'):
                out.append(' ')
            elif t in ('Code', 'Math', 'RawInline'):
                out.append(c[1])
            elif t in ('Emph', 'Strong', 'Strikeout', 'Underline', 'SmallCaps', 'Superscript', 'Subscript'):
                out.append(inline(c))
            elif t in ('Link', 'Span', 'Cite', 'Quoted'):
                out.append(inline(c[1]))
            elif t == 'Image':
                out.append(inline(c[1]) if alt else '')
            elif t == 'Note':
                block(c)
        return ''.join(out)

    def block(bs):
        for b in bs:
            t, c = b['t'], b.get('c')
            if t in ('Para', 'Plain'):
                lines.append(inline(c))
            elif t == 'Header':
                lines.append(inline(c[2]))
            elif t == 'BulletList':
                for item in c:
                    block(item)
            elif t == 'OrderedList':
                for item in c[1]:
                    block(item)
            elif t == 'BlockQuote':
                block(c)
            elif t == 'Div':
                block(c[1])
            elif t == 'Table':
                for cell in table_cells(c):
                    block(cell)
            elif t == 'CodeBlock':
                lines.append(c[1])
            elif t == 'LineBlock':
                lines.extend(inline(x) for x in c)
            elif t == 'Figure':
                block(c[1][1])
                block(c[2])
    block(blocks)
    return '\n'.join(lines)


def headings(blocks):
    return [(b['c'][0], ' '.join(ast_text([b]).split())) for b in blocks if b['t'] == 'Header']


def docx_list_items(part):
    """(Word list level, kind) of each numbered paragraph of the document, in order."""
    doc = ElementTree.fromstring(part('word/document.xml'))
    numbering = ElementTree.fromstring(part('word/numbering.xml'))
    formats = {a.get(W + 'abstractNumId'): {lvl.get(W + 'ilvl'): lvl.find(W + 'numFmt').get(W + 'val')
                                             for lvl in a.iter(W + 'lvl')}
               for a in numbering.iter(W + 'abstractNum')}
    abstract = {n.get(W + 'numId'): n.find(W + 'abstractNumId').get(W + 'val') for n in numbering.iter(W + 'num')}
    items = []
    for p in doc.iter(W + 'p'):
        numpr = p.find(f'{W}pPr/{W}numPr')
        if numpr is not None:
            level = numpr.find(W + 'ilvl').get(W + 'val')
            fmt = formats[abstract[numpr.find(W + 'numId').get(W + 'val')]][level]
            items.append((int(level), 'bullet' if fmt == 'bullet' else 'number'))
    return items


def find_validator():
    if os.environ.get('DOCX_VALIDATE'):
        path = Path(os.environ['DOCX_VALIDATE'])
    else:
        found = sorted((Path.home() / '.claude' / 'skills').glob('**/docx/scripts/office/validate.py'))
        path = found[0] if found else None
    return path if path is not None and path.is_file() else None


def validate(docx, tmp, real, redact):
    """Run the docx skill's validate.py on the unpacked document. Returns (passed, lines to print), or (None, [])
    when validate.py is not found."""
    script = find_validator()
    if script is None:
        return None, []
    unpacked = tmp / 'unpacked.docx'  # a folder named .docx: validate.py reads the type from the suffix
    with zipfile.ZipFile(docx) as z:
        z.extractall(unpacked)
    code = ('import runpy, sys; sys.path.insert(0, sys.argv[1]); sys.argv = sys.argv[2:]; '
            'runpy.run_path(sys.argv[0], run_name="__main__")')
    r = subprocess.run([sys.executable, '-I', '-c', code, str(script.parent), str(script), str(unpacked)],
                       capture_output=True, encoding='utf-8', check=False)
    passed = r.returncode == 0 and 'All validations PASSED' in r.stdout
    lines = [redact(line) for line in (r.stdout + r.stderr).splitlines() if line.strip()]
    if real:  # details can quote document text: keep the summary lines
        lines = [line for line in lines if line.lstrip().startswith(('PASSED', 'FAILED', 'All validations'))]
    return passed, lines


# -----------------------------------------------------------------------------------------------------------------
# Build
# -----------------------------------------------------------------------------------------------------------------
class Checks:
    def __init__(self):
        self.failed = []

    def __call__(self, name, ok, detail):
        print(f'  [{"ok" if ok else "FAIL"}] {name}: {detail}')
        if not ok:
            self.failed.append(name)


def check_document(docx, tmp, *, md, ast, stems, files, n_sub, used, customer_names, internal, real, redact):
    """Run the checks on the built document; returns the names of the failed checks."""
    check = Checks()
    with zipfile.ZipFile(docx) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    part = parts.__getitem__

    # List nesting: Markdown markers -> pandoc's AST -> Word's numbered paragraphs.
    md_items, ast_items, docx_items = markdown_list_items(md), ast_list_items(ast['blocks']), docx_list_items(part)
    depth_counts = Counter(d for d, _ in ast_items)
    check('list nesting, Markdown markers = pandoc AST', md_items == ast_items,
          f'{len(md_items)} and {len(ast_items)} list items; items by depth '
          + ', '.join(f'{d}: {n}' for d, n in sorted(depth_counts.items())))
    first_diff = next((i for i, (a, b) in enumerate(zip(ast_items, docx_items)) if a != b), None)
    check('list levels, pandoc AST = document', ast_items == docx_items,
          f'{len(docx_items)} numbered paragraphs' + (f'; first difference at item {first_diff + 1}'
                                                      if first_diff is not None else ''))

    # Privacy: pseudonyms and names in the document.
    plain = run(['pandoc', '-f', 'docx', '-t', 'plain', '--wrap=none', docx], 'pandoc (docx -> plain)', redact)
    doc_ast = json.loads(run(['pandoc', '-f', 'docx', '-t', 'json', docx], 'pandoc (docx -> json)', redact))
    doc_text = ast_text(doc_ast['blocks'], alt=False)
    xml_left = sum(names.pseudonyms_left(data.decode('utf-8', 'replace')) for n, data in parts.items()
                   if n.endswith(('.xml', '.rels')))
    check('no pseudonyms in the document', names.pseudonyms_left(plain) == 0 == names.pseudonyms_left(doc_text)
          and xml_left == 0, f'{names.pseudonyms_left(plain)} in pandoc -t plain, '
          f'{names.pseudonyms_left(doc_text)} in its AST text, {xml_left} in its XML parts')
    substituted = {c: ' '.join(str(customer_names[c]).split()) for c in used}
    found_plain = names.names_found(' '.join(plain.split()), substituted)
    found_ast = names.names_found(' '.join(doc_text.split()), substituted)
    check('names in the document = substitutions', found_plain == n_sub == found_ast,
          f'{n_sub} substituted; found {found_plain} in pandoc -t plain, {found_ast} in its AST text')

    # Images.
    media = {sha256(data) for n, data in parts.items() if n.startswith('word/media/')}
    drawings = part('word/document.xml').decode('utf-8').count('<w:drawing>')
    check('embedded images = Markdown images', drawings == len(stems),
          f'{drawings} images in the document, {len(stems)} in the Markdown')
    missing = [f.name for f in files if sha256(f.read_bytes()) not in media]
    check('each image embedded byte for byte', not missing,
          f'{len(files) - len(missing)} of {len(files)} image files found in word/media by sha256')
    real_png = [names.DELIVERABLES / f'{s}_REALNAMES.png' for s in CUSTOMER_CHARTS]
    pseudo_png = [FIGURES / f'{s}.png' for s in CUSTOMER_CHARTS]
    want, avoid = (real_png, pseudo_png) if real else (pseudo_png, real_png)
    n_want = sum(sha256(p.read_bytes()) in media for p in want)
    n_avoid = sum(p.exists() and sha256(p.read_bytes()) in media for p in avoid)
    check('customer charts', n_want == len(CUSTOMER_CHARTS) and n_avoid == 0,
          f'{n_want} of {len(CUSTOMER_CHARTS)} {"REALNAMES" if real else "pseudonymous"} PNGs in word/media '
          f'(sha256), {n_avoid} {"pseudonymous" if real else "REALNAMES"} ones')
    doc = ElementTree.fromstring(part('word/document.xml'))
    marks = {b.get(W + 'name') for b in doc.iter(W + 'bookmarkStart')}
    anchors = [h.get(W + 'anchor') for h in doc.iter(W + 'hyperlink') if h.get(W + 'anchor')]
    check('internal links have their bookmark', len(anchors) == internal and set(anchors) <= marks,
          f'{len(anchors)} internal links ({internal} expected) to {len(set(anchors))} charts; '
          f'{len(set(anchors) - marks)} without a bookmark')

    # Headings.
    md_heads, doc_heads = headings(ast['blocks']), headings(doc_ast['blocks'])
    first_diff = next((i for i, (a, b) in enumerate(zip(md_heads, doc_heads)) if a != b), None)
    check('headings, Markdown = document', md_heads == doc_heads,
          f'{len(doc_heads)} headings in the document, {len(md_heads)} in the Markdown (levels '
          + ', '.join(f'{lvl}: {n}' for lvl, n in sorted(Counter(lvl for lvl, _ in md_heads).items())) + ')'
          + (f'; first difference at heading {first_diff + 1}' if first_diff is not None else ''))

    # Number tokens.
    src_tokens = Counter(NUMBER.findall(ast_text(ast['blocks'])))
    doc_tokens = Counter(NUMBER.findall(doc_text))
    source_lines = SOURCE.read_text(encoding='utf-8').splitlines()
    differ = sorted(set(src_tokens) | set(doc_tokens), key=lambda t: (src_tokens[t] - doc_tokens[t], t))
    differ = [t for t in differ if src_tokens[t] != doc_tokens[t]]
    check('number tokens, memo text = document text', not differ,
          f'{sum(src_tokens.values())} tokens ({len(src_tokens)} distinct) in the memo text, '
          f'{sum(doc_tokens.values())} in the document')
    for t in differ[:20]:
        where = [str(i) for i, line in enumerate(source_lines, 1) if t in NUMBER.findall(line)]
        print(f'      "{t}": {src_tokens[t]} in the memo text, {doc_tokens[t]} in the document; '
              f'docs/executive_summary.md line(s) {", ".join(where[:12]) or "none"}')

    # Word validity.
    passed, lines = validate(docx, tmp, real, redact)
    if passed is None:
        print("  validate.py: skipped (the docx skill's scripts/office/validate.py was not found; set DOCX_VALIDATE "
              'to its path to run it)')
        return check.failed
    check('validate.py', passed, lines[-1].strip() if lines else 'no output')
    if not passed:
        for line in lines[:40]:
            print(f'      {line}')
    return check.failed


def build(twin_dir=None, tmp_parent=None):
    real = twin_dir is None
    real_names = names.real_names()
    if real_names is None:
        fail(f'{names.NAMES_FILE.relative_to(names.ROOT)} not found: no names for the memo')
    twin_names = names.twin(real_names)
    customer_names = real_names if real else twin_names
    redact = redactor(real_names, twin_names)
    print(f'IPA memo ({"real names" if real else "twin names and pseudonymous charts: layout check"})')
    tmp = None
    try:
        source = SOURCE.read_text(encoding='utf-8')
        md = step_note(source)
        md = step_charts_sentence(md)
        md, n_sub, used = step_names(md, customer_names, source)
        md, stems, files = step_images(md, real)
        md, internal = step_links(md, set(stems))
        print(f'  charts embedded: {", ".join(stems)}')

        tmp_parent = Path(tmp_parent) if tmp_parent else names.DELIVERABLES
        tmp_parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix='memo_', dir=tmp_parent))
        ast_json = run(['pandoc', '-f', READER, '-t', 'json'], f'pandoc ({READER} -> json)', redact, input=md)
        ast = json.loads(ast_json)
        (tmp / 'memo.json').write_text(ast_json, encoding='utf-8')
        docx = tmp / 'memo.docx'
        run(['node', MEMO_JS, tmp / 'memo.json', docx], 'memo_docx.js', redact)
        failed = check_document(docx, tmp, md=md, ast=ast, stems=stems, files=files, n_sub=n_sub, used=used,
                                customer_names=customer_names, internal=internal, real=real, redact=redact)
        if failed:
            fail(f'{len(failed)} check(s) failed: {", ".join(failed)}; '
                 + ('the existing memo is unchanged' if real else 'no twin written'))
        if real:
            out = MEMO
            if out.exists():
                shutil.copy2(out, PREVIOUS)
                print(f'  previous memo copied to {PREVIOUS.relative_to(names.ROOT)}')
        else:
            out = Path(twin_dir) / TWIN_MEMO
            out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(docx, out)
        print(f'  wrote {out} ({out.stat().st_size / 1e6:.1f} MB)')
        return out
    except BuildError:
        raise
    except Exception as err:  # noqa: BLE001  its message could quote the document: report it with pseudonyms
        frame = traceback.extract_tb(err.__traceback__)[-1]
        fail(f'{type(err).__name__} at {Path(frame.filename).name}:{frame.lineno}: {redact(str(err))[:500]}')
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--twin', metavar='OUT_DIR', help='build the twin memo (twin names, pseudonymous charts) '
                        f'into OUT_DIR/{TWIN_MEMO} instead of the real memo')
    parser.add_argument('--tmp', metavar='DIR', help='folder for the temporary build folder (default: deliverables/)')
    args = parser.parse_args()
    try:
        build(args.twin, args.tmp)
    except BuildError as err:
        print(f'FAILED: {err}')
        sys.exit(1)


if __name__ == '__main__':
    main()
