#!/usr/bin/env node
/*
 * Word memo layout: a pandoc JSON AST of the executive summary -> a .docx, built with docx-js.
 *
 * viz/deliverables/build_memo.py prepares the memo's Markdown (real or twin names, absolute image paths, links to
 * chart captions), parses it with pandoc's gfm reader and calls this script, which only lays the document out. It
 * reads no names file, and its error messages name element types, bookmark ids and paths, never document text.
 *
 * Layout: US Letter, 1-inch margins, Arial. Body 10.5 pt in ink #20252B; H1 20 pt and H2 14 pt bold in blue #215F9B,
 * H3 12 pt bold in ink (Word's built-in Heading 1-3 styles, so the navigation pane and a TOC see them).
 *   - Block quotes (the update boxes) become shaded callouts: a one-cell table, fill #EEF3F9 with a blue left border,
 *     so that lists nested 2-4 deep keep their own indents inside one even box (paragraph borders would follow each
 *     list level's indent and draw a stepped edge).
 *   - Lists use Word numbering, never typed bullet characters: one bullet definition (levels 0-5), and one decimal
 *     definition per ordered list, starting at the source's start number, so each list restarts its count.
 *   - Tables get DXA column widths summing to the text width, set on the table and on every cell, and a shaded
 *     header row that repeats on a new page.
 *   - A paragraph holding only an image becomes a bold caption (the alt text, carrying the bookmark named by the
 *     image title, which the chart links point to), kept with the image below it; the image is scaled to the text
 *     width (aspect ratio from the PNG header) and capped in height so caption, image and note fit on one page.
 *   - Inline bold, italic and code (Consolas); links to '#bookmark' become internal links, http(s) links external
 *     hyperlinks; any other link target keeps its text only.
 *   - Header: the memo title; footer: the confidentiality line and "Page X of Y".
 *
 * Inputs:  <ast.json>   pandoc JSON AST (pandoc 3.x; images as absolute paths, each with its bookmark id as title)
 * Outputs: <out.docx>
 *
 * Run (normally through build_memo.py):  node viz/deliverables/memo_docx.js <ast.json> <out.docx>
 */
'use strict';

const fs = require('fs');
const {
  AlignmentType, BookmarkEnd, BookmarkStart, BorderStyle, Document, ExternalHyperlink, Footer, Header, HeadingLevel,
  ImageRun, InternalHyperlink, LevelFormat, LineRuleType, Packer, PageNumber, Paragraph, ShadingType, Tab, Table,
  TableCell, TableRow, TabStopType, TextRun, UnderlineType, WidthType,
} = require('docx');

// Page geometry (DXA: 1440 per inch). docx-js takes image sizes in pixels at 96 per inch.
const PAGE_W = 12240;
const PAGE_H = 15840;
const MARGIN = 1440;
const TEXT_W = PAGE_W - 2 * MARGIN;  // 9360
const PX_PER_IN = 96;
const MAX_IMAGE_IN = 7.4;            // tallest image: leaves room for a heading, the caption and a 3-line note

// Type (sizes in half-points) and colours.
const FONT = 'Arial';
const CODE_FONT = 'Consolas';
const BODY = 21;                     // 10.5 pt
const TABLE_TEXT = 19;               // 9.5 pt
const SMALL = 16;                    // 8 pt: header and footer
const INK = '20252B';
const BLUE = '215F9B';
const MUTED = '5F6B78';
const RULE = 'C8D2DE';
const CALLOUT_FILL = 'EEF3F9';
const HEAD_FILL = 'DCE6F1';

// Spacing (DXA; 20 per point).
const SPACE = {
  para: 120,          // after a body paragraph
  line: 264,          // line spacing, 240ths of a line (1.1); always with lineRule auto, as LibreOffice reads a
                      // missing rule as an exact height (which clips images and overlaps wrapped headings)
  item: 50,           // after a list item
  caption: 240,       // before an image caption
  callout: 120,       // callout padding, top and bottom
};
const LIST_STEP = 360;               // indent per list level
const LIST_HANG = 360;               // hanging indent: room for the bullet or number ('10.' at 10.5 pt is ~290)
const BULLETS = ['•', '◦', '▪'];  // bullet, white bullet, small square, cycled by level
const LEVELS = 6;

const HEADER_TEXT = 'Service Tickets & Telemetry: Executive Summary (IPA version)';
const FOOTER_TEXT = 'Confidential: contains IPA customer names. For the project team and IPA only.';
const NEW_PAGE_BEFORE = new Set(['Charts by finding']);  // H2 sections that start on a new page
const BOOKMARK_ID = /^[A-Za-z][A-Za-z0-9_]{0,39}$/;      // Word's bookmark-name rule

const NO_BORDER = { style: BorderStyle.NONE, size: 0, color: 'auto' };
const NO_BORDERS = {
  top: NO_BORDER, bottom: NO_BORDER, left: NO_BORDER, right: NO_BORDER,
  insideHorizontal: NO_BORDER, insideVertical: NO_BORDER,
};
const HAIRLINE = { style: BorderStyle.SINGLE, size: 4, color: RULE };
let bookmarks = 0;  // numeric bookmark ids (docx-js's Bookmark class gives every bookmark id 1)

// Numbering definitions, filled while the blocks are converted: one per ordered list, one shared for bullets.
const numbering = [{
  reference: 'bullets',
  levels: Array.from({ length: LEVELS }, (_, i) => ({
    level: i,
    format: LevelFormat.BULLET,
    text: BULLETS[i % BULLETS.length],
    alignment: AlignmentType.LEFT,
    style: {
      paragraph: { indent: { left: LIST_STEP * (i + 1), hanging: LIST_HANG } },
      run: { font: FONT, color: BLUE },
    },
  })),
}];

function orderedReference(start) {
  const reference = `ordered${numbering.length}`;
  numbering.push({
    reference,
    levels: Array.from({ length: LEVELS }, (_, i) => ({
      level: i,
      format: LevelFormat.DECIMAL,
      text: `%${i + 1}.`,
      start,
      alignment: AlignmentType.LEFT,
      style: {
        paragraph: { indent: { left: LIST_STEP * (i + 1), hanging: LIST_HANG } },
        run: { font: FONT, color: BLUE, bold: true },
      },
    })),
  });
  return reference;
}

// ---------------------------------------------------------------------------------------------------------------
// Inline content: pandoc inlines -> text segments with a format -> runs (adjacent segments with the same format and
// link merged into one run).
// ---------------------------------------------------------------------------------------------------------------
function flatten(inlines, fmt, out) {
  for (const el of inlines) {
    switch (el.t) {
      case 'Str': out.push({ text: el.c, fmt }); break;
      case 'Space':
      case 'SoftBreak': out.push({ text: ' ', fmt }); break;
      case 'LineBreak': out.push({ br: true, fmt }); break;
      case 'Emph': flatten(el.c, { ...fmt, italics: true }, out); break;
      case 'Strong': flatten(el.c, { ...fmt, bold: true }, out); break;
      case 'Strikeout': flatten(el.c, { ...fmt, strike: true }, out); break;
      case 'Underline': flatten(el.c, { ...fmt, underline: true }, out); break;
      case 'Superscript': flatten(el.c, { ...fmt, superScript: true }, out); break;
      case 'Subscript': flatten(el.c, { ...fmt, subScript: true }, out); break;
      case 'SmallCaps': flatten(el.c, { ...fmt, smallCaps: true }, out); break;
      case 'Span': flatten(el.c[1], fmt, out); break;
      case 'Code': out.push({ text: el.c[1], fmt: { ...fmt, code: true } }); break;
      case 'Quoted': {
        const [open, close] = el.c[0].t === 'SingleQuote' ? ['‘', '’'] : ['“', '”'];
        out.push({ text: open, fmt });
        flatten(el.c[1], fmt, out);
        out.push({ text: close, fmt });
        break;
      }
      case 'Link': flatten(el.c[1], { ...fmt, link: el.c[2][0] }, out); break;
      case 'Image': throw new Error('an image inside running text (only an image on its own line is supported)');
      default: throw new Error(`unsupported inline element ${el.t}`);
    }
  }
  return out;
}

const fmtKey = (f) => JSON.stringify([f.bold, f.italics, f.code, f.strike, f.underline, f.superScript, f.subScript,
  f.smallCaps, f.link]);

function textRun(seg, ctx, text) {
  const f = seg.fmt;
  const size = ctx.size || BODY;
  return new TextRun({
    text,
    break: seg.br ? 1 : undefined,
    bold: f.bold || ctx.bold || undefined,
    italics: f.italics || ctx.italics || undefined,
    strike: f.strike || undefined,
    underline: f.underline ? {} : undefined,
    superScript: f.superScript || undefined,
    subScript: f.subScript || undefined,
    smallCaps: f.smallCaps || undefined,
    font: f.code ? CODE_FONT : undefined,
    size: f.code ? size - 2 : ctx.size,
    color: ctx.color,
    style: f.link && isLinkTarget(f.link) ? 'Hyperlink' : undefined,
  });
}

const isLinkTarget = (url) => url.startsWith('#') || /^(https?|mailto):/i.test(url);

function runs(inlines, ctx, fmt = {}) {
  const segs = flatten(inlines, fmt, []);
  const groups = [];
  for (const seg of segs) {
    const last = groups[groups.length - 1];
    if (last && !seg.br && fmtKey(last.fmt) === fmtKey(seg.fmt)) last.text += seg.text;
    else groups.push({ ...seg, text: seg.text || '' });
  }
  const out = [];
  for (let i = 0; i < groups.length;) {
    const link = groups[i].fmt.link;
    if (!link || !isLinkTarget(link)) { out.push(textRun(groups[i], ctx, groups[i].text)); i += 1; continue; }
    const children = [];
    for (; i < groups.length && groups[i].fmt.link === link; i += 1) {
      children.push(textRun(groups[i], ctx, groups[i].text));
    }
    if (link.startsWith('#')) {
      const anchor = link.slice(1);
      if (!BOOKMARK_ID.test(anchor)) throw new Error(`link to an invalid bookmark id ${anchor}`);
      out.push(new InternalHyperlink({ anchor, children }));
    } else {
      out.push(new ExternalHyperlink({ link, children }));
    }
  }
  return out;
}

function plain(inlines) {
  return flatten(inlines, {}, []).map((s) => (s.br ? ' ' : s.text)).join('');
}

// ---------------------------------------------------------------------------------------------------------------
// Blocks. Converters return specs ({ p: paragraph options } or { el: a built table }) so that spacing can still be
// adjusted (the last item of a list, the last paragraph of a callout) before the paragraphs are built.
// ---------------------------------------------------------------------------------------------------------------
function paragraphInlines(inlines) {
  // Two emphasised lines written one under the other (the date line and the team line) stay separate lines.
  return inlines.map((el, i) => (el.t === 'SoftBreak' && inlines[i - 1] && inlines[i - 1].t === 'Emph'
    && inlines[i + 1] && inlines[i + 1].t === 'Emph' ? { t: 'LineBreak' } : el));
}

function isImageParagraph(b) {
  if (!b || (b.t !== 'Para' && b.t !== 'Plain')) return false;
  const content = b.c.filter((el) => !['Space', 'SoftBreak', 'LineBreak'].includes(el.t));
  return content.length === 1 && content[0].t === 'Image';
}

function blocks(list, ctx) {
  const out = [];
  list.forEach((b, i) => {
    const next = list[i + 1];
    switch (b.t) {
      case 'Para':
      case 'Plain':
        if (isImageParagraph(b)) {
          const keepWithNote = Boolean(next && (next.t === 'Para' || next.t === 'Plain') && !isImageParagraph(next));
          out.push(...figure(b.c.find((el) => el.t === 'Image'), ctx, keepWithNote));
        } else {
          // A heading's lead-in stays with the chart right after it, so the section starts on the chart's page.
          const leadIn = i > 0 && list[i - 1].t === 'Header' && isImageParagraph(next);
          out.push({
            p: {
              children: runs(paragraphInlines(b.c), ctx),
              keepNext: leadIn || undefined,
              spacing: { after: ctx.after ?? SPACE.para },
            },
          });
        }
        break;
      case 'Header': out.push(heading(b)); break;
      case 'BulletList':
      case 'OrderedList': out.push(...listBlock(b, ctx, 0)); break;
      case 'BlockQuote': out.push(...callout(b.c, ctx)); break;
      case 'Table': out.push(...table(b, ctx)); break;
      case 'Div': out.push(...blocks(b.c[1], ctx)); break;
      case 'HorizontalRule':
        out.push({
          p: { children: [], border: { bottom: { ...HAIRLINE, space: 1 } }, spacing: { after: SPACE.para } },
        });
        break;
      case 'CodeBlock':
        for (const line of b.c[1].split('\n')) {
          out.push({
            p: {
              children: [new TextRun({ text: line, font: CODE_FONT, size: (ctx.size || BODY) - 2 })],
              spacing: { after: 0 },
            },
          });
        }
        break;
      default: throw new Error(`unsupported block element ${b.t}`);
    }
  });
  return out;
}

function heading(b) {
  const [level, , inlines] = b.c;
  if (level > 3) throw new Error(`heading level ${level} (only 1-3 are styled)`);
  const kind = [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3][level - 1];
  return {
    p: {
      heading: kind,
      children: runs(inlines, {}),
      pageBreakBefore: level === 2 && NEW_PAGE_BEFORE.has(plain(inlines).trim()) ? true : undefined,
    },
  };
}

function listBlock(b, ctx, level) {
  if (level >= LEVELS) throw new Error(`list nested deeper than ${LEVELS} levels`);
  const ordered = b.t === 'OrderedList';
  const items = ordered ? b.c[1] : b.c;
  const reference = ordered ? orderedReference(b.c[0][0]) : 'bullets';
  const out = [];
  for (const item of items) {
    item.forEach((blk, j) => {
      if (j === 0) {
        if (blk.t !== 'Plain' && blk.t !== 'Para') throw new Error(`list item starting with ${blk.t}`);
        out.push({
          p: {
            children: runs(blk.c, ctx),
            numbering: { reference, level },
            spacing: { after: SPACE.item },
          },
        });
      } else if (blk.t === 'BulletList' || blk.t === 'OrderedList') {
        out.push(...listBlock(blk, ctx, level + 1));
      } else if (blk.t === 'Plain' || blk.t === 'Para') {
        // A further paragraph of the item: aligned with the item's text, no marker.
        out.push({
          p: {
            children: runs(blk.c, ctx),
            indent: { left: LIST_STEP * (level + 1) },
            spacing: { before: SPACE.item, after: SPACE.item },
          },
        });
      } else {
        throw new Error(`unsupported block ${blk.t} inside a list item`);
      }
    });
  }
  if (level === 0 && out.length) {
    const last = out[out.length - 1].p;
    last.spacing = { ...last.spacing, after: ctx.after ?? SPACE.para };
  }
  return out;
}

function spacer() {
  // Keeps two tables apart (Word joins adjacent tables) and spaces the text after a table: 6 pt exactly.
  return { p: { children: [], spacing: { before: 0, after: 0, line: 120, lineRule: LineRuleType.EXACT } } };
}

function build(specs) {
  return specs.map((s) => (s.el ? s.el : new Paragraph(s.p)));
}

function callout(content, ctx) {
  const inner = blocks(content, { ...ctx, after: 60 });
  if (!inner.length) return [];
  const last = inner[inner.length - 1];
  if (last.p) last.p.spacing = { ...last.p.spacing, after: 0 };
  const cell = new TableCell({
    children: build(inner),
    width: { size: TEXT_W, type: WidthType.DXA },
    shading: { fill: CALLOUT_FILL, type: ShadingType.CLEAR, color: 'auto' },
    margins: { top: SPACE.callout, bottom: SPACE.callout, left: 240, right: 200 },
    borders: {
      top: NO_BORDER, bottom: NO_BORDER, right: NO_BORDER,
      left: { style: BorderStyle.SINGLE, size: 24, color: BLUE },
    },
  });
  const box = new Table({
    rows: [new TableRow({ children: [cell] })],
    width: { size: TEXT_W, type: WidthType.DXA },
    columnWidths: [TEXT_W],
    borders: NO_BORDERS,
  });
  return [{ el: box }, spacer()];
}

function cellText(cell) {
  return cell[4].map((b) => (b.t === 'Plain' || b.t === 'Para' ? plain(b.c) : '')).join(' ');
}

function columnWidths(rows, n) {
  // Columns of short entries (a row number) get a fixed narrow width; the others share the rest in proportion to
  // their text, at least 1,800 DXA each. The widths sum to the text width exactly.
  const NARROW = 560;
  const MIN_WIDE = 1800;
  const total = Array(n).fill(0);
  const longest = Array(n).fill(0);
  for (const row of rows) {
    row[1].forEach((cell, j) => {
      const len = cellText(cell).length;
      total[j] += len;
      longest[j] = Math.max(longest[j], len);
    });
  }
  const narrow = longest.map((len) => len <= 4);
  const wideSum = total.reduce((s, t, j) => s + (narrow[j] ? 0 : t), 0) || 1;
  const room = TEXT_W - NARROW * narrow.filter(Boolean).length;
  const widths = total.map((t, j) => (narrow[j] ? NARROW : Math.max(MIN_WIDE, Math.round(room * t / wideSum))));
  const wide = widths.map((w, j) => (narrow[j] ? -1 : w));
  widths[wide.indexOf(Math.max(...wide))] += TEXT_W - widths.reduce((s, w) => s + w, 0);
  return widths;
}

function table(tb, ctx) {
  const [, , colspecs, head, bodies, foot] = tb.c;
  const n = colspecs.length;
  const headRows = head[1];
  const bodyRows = bodies.flatMap((body) => [...body[2], ...body[3]]);
  const rows = [...headRows, ...bodyRows, ...foot[1]];
  const widths = columnWidths(rows, n);
  if (widths.reduce((s, w) => s + w, 0) !== TEXT_W) throw new Error('table column widths do not sum to the text width');
  const makeRow = (row, isHead) => new TableRow({
    tableHeader: isHead || undefined,
    cantSplit: true,
    children: row[1].map((cell, j) => {
      if (cell[2] !== 1 || cell[3] !== 1) throw new Error('table cells spanning rows or columns are not supported');
      return new TableCell({
        children: build(blocks(cell[4], { ...ctx, size: TABLE_TEXT, bold: isHead, after: 0 })),
        width: { size: widths[j], type: WidthType.DXA },
        shading: isHead ? { fill: HEAD_FILL, type: ShadingType.CLEAR, color: 'auto' } : undefined,
        margins: { top: 70, bottom: 70, left: 100, right: 100 },
      });
    }),
  });
  const grid = new Table({
    rows: [...headRows.map((r) => makeRow(r, true)), ...bodyRows.map((r) => makeRow(r, false)),
      ...foot[1].map((r) => makeRow(r, false))],
    width: { size: TEXT_W, type: WidthType.DXA },
    columnWidths: widths,
    borders: {
      top: HAIRLINE, bottom: HAIRLINE, left: HAIRLINE, right: HAIRLINE, insideHorizontal: HAIRLINE,
      insideVertical: HAIRLINE,
    },
  });
  return [{ el: grid }, spacer()];
}

function pngSize(data, file) {
  const signature = '89504e470d0a1a0a';
  if (data.length < 24 || data.subarray(0, 8).toString('hex') !== signature
      || data.subarray(12, 16).toString('latin1') !== 'IHDR') throw new Error(`not a PNG: ${file}`);
  return { width: data.readUInt32BE(16), height: data.readUInt32BE(20) };
}

function figure(image, ctx, keepWithNote) {
  const [, alt, [src, id]] = image.c;
  if (!BOOKMARK_ID.test(id)) throw new Error(`image without a valid bookmark id as its title: ${src}`);
  if (!fs.existsSync(src)) throw new Error(`image not found: ${src}`);
  const data = fs.readFileSync(src);
  const px = pngSize(data, src);
  let width = Math.round(TEXT_W / 1440 * PX_PER_IN);
  let height = Math.round(width * px.height / px.width);
  const maxHeight = Math.round(MAX_IMAGE_IN * PX_PER_IN);
  if (height > maxHeight) {
    width = Math.round(maxHeight * px.width / px.height);
    height = maxHeight;
  }
  const altText = plain(alt);
  bookmarks += 1;
  return [
    {
      p: {
        children: [new BookmarkStart(id, bookmarks), ...runs(alt, ctx, { bold: true }), new BookmarkEnd(bookmarks)],
        keepNext: true,
        keepLines: true,
        spacing: { before: SPACE.caption, after: 80 },
      },
    },
    {
      p: {
        children: [new ImageRun({
          type: 'png',
          data,
          transformation: { width, height },
          altText: { name: id, title: altText, description: altText },
        })],
        alignment: AlignmentType.CENTER,
        keepNext: keepWithNote || undefined,
        spacing: { after: 80, line: 240, lineRule: LineRuleType.AUTO },  // single: 1.1 would pad a tall image
      },
    },
  ];
}

// ---------------------------------------------------------------------------------------------------------------
// Document
// ---------------------------------------------------------------------------------------------------------------
function memo(ast) {
  const body = build(blocks(ast.blocks, {}));
  const small = { size: SMALL, color: MUTED };
  const text = {
    run: { font: FONT, size: BODY, color: INK },
    paragraph: { spacing: { after: SPACE.para, line: SPACE.line, lineRule: LineRuleType.AUTO }, widowControl: true },
  };
  return new Document({
    title: HEADER_TEXT,
    creator: 'Roper IPA × MIT Analytics Lab',
    lastModifiedBy: 'Roper IPA × MIT Analytics Lab',
    description: 'Built by viz/deliverables/build_memo.py from docs/executive_summary.md',
    styles: {
      // A Normal style like the document defaults: docx-js bases its heading styles on 'Normal' but defines none,
      // and pandoc's docx reader (the build's checks) then sees no headings.
      // The header and footer style: LibreOffice reads the page-number fields' size and colour from the paragraph's
      // style, not from the run that holds them.
      paragraphStyles: [{ id: 'Normal', name: 'Normal', quickFormat: true, ...text },
        { id: 'MemoMargin', name: 'Memo Header and Footer', basedOn: 'Normal', run: { size: SMALL, color: MUTED },
          paragraph: { spacing: { after: 0 } } }],
      default: {
        document: text,
        heading1: {
          run: { font: FONT, size: 40, bold: true, color: BLUE },
          paragraph: {
            spacing: { before: 0, after: 120, line: 240, lineRule: LineRuleType.AUTO },
            keepNext: true,
            keepLines: true,
            outlineLevel: 0,
          },
        },
        heading2: {
          run: { font: FONT, size: 28, bold: true, color: BLUE },
          paragraph: { spacing: { before: 360, after: 120 }, keepNext: true, keepLines: true, outlineLevel: 1 },
        },
        heading3: {
          run: { font: FONT, size: 24, bold: true, color: INK },
          paragraph: { spacing: { before: 280, after: 100 }, keepNext: true, keepLines: true, outlineLevel: 2 },
        },
        hyperlink: { run: { color: BLUE, underline: { type: UnderlineType.SINGLE, color: BLUE } } },
      },
    },
    numbering: { config: numbering },
    sections: [{
      properties: {
        page: {
          size: { width: PAGE_W, height: PAGE_H },
          margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN, header: 720, footer: 720 },
        },
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            style: 'MemoMargin',
            alignment: AlignmentType.RIGHT,
            border: { bottom: { ...HAIRLINE, space: 4 } },
            children: [new TextRun({ text: HEADER_TEXT, ...small })],
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            style: 'MemoMargin',
            tabStops: [{ type: TabStopType.RIGHT, position: TEXT_W }],
            children: [
              new TextRun({ text: FOOTER_TEXT, ...small }),
              new TextRun({
                children: [new Tab(), 'Page ', PageNumber.CURRENT, ' of ', PageNumber.TOTAL_PAGES],
                ...small,
              }),
            ],
          })],
        }),
      },
      children: body,
    }],
  });
}

async function main() {
  const [astPath, outPath] = process.argv.slice(2);
  if (!astPath || !outPath) throw new Error('usage: node memo_docx.js <ast.json> <out.docx>');
  const ast = JSON.parse(fs.readFileSync(astPath, 'utf8'));
  if (!Array.isArray(ast.blocks)) throw new Error('not a pandoc JSON AST');
  fs.writeFileSync(outPath, await Packer.toBuffer(memo(ast)));
}

main().catch((err) => {
  process.stderr.write(`memo_docx.js: ${err.message}\n`);
  process.exit(1);
});
