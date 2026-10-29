#!/usr/bin/env node
/*
 * The IPA deck as a PDF: every slide of a deck folder, in deck.json order, printed by Chromium (Playwright) on one
 * 1920 x 1080 px page each.
 *
 * viz/deliverables/build_deck_pdf.py prepares a working copy of the deck (names substituted, chart files chosen) and
 * calls this script, which only lays the slides out and prints them. It reads no names file, and its messages and
 * report name slide ids, tags, icon names, blob ids and file names, never slide text.
 *
 * The slides are the live deck's HTML: each file is one <section> of 1920 x 1080 px with absolutely positioned
 * children and inline styles. The deck runtime's own elements are stood in for here:
 *   - <x-shape kind="ellipse"> (the header's section dots): a block with border-radius 50%; any other kind fails;
 *   - <x-icon name=...> (data and next-steps slides): an inline SVG of the same size and style, stroked in
 *     currentColor on a 24-unit grid (ICONS, drawn for this deck); an unknown name fails;
 *   - <aside> (speaker notes): not printed;
 *   - images src="/_blob/<id>": file:// URLs of the files the asset map gives; every image must load (naturalWidth
 *     above 0) before printing.
 * The CSS reset is the layout-check renderer's: margin and padding 0, border-box sizing, collapsed table borders.
 *
 * Fit pass, before printing (in print media): each p, h1, h2 and h3 must lie inside its parent box, every box
 * around it and the slide (bounding rectangles, 1 px tolerance) and must not overflow itself (scrollWidth and
 * scrollHeight against clientWidth and clientHeight + 1). Text that does not fit is set 1 px smaller until it does,
 * down to a floor: 20 px for text up to 28 px, 40 px for titles (h1, h2), three quarters of the size for other large
 * text. Each change is reported as {slide, tag, from, to} (px). Text still overflowing at its floor, a box of fixed
 * height (inline style) whose content overflows it, or a slide whose content runs off the page fails the build.
 *
 * Inputs:  <deck_dir>     deck.json ("order": slide ids, "title") and slides/<id>.html
 *          <assets.json>  {blob id: path of the local file} for every /_blob/<id> the slides use
 * Outputs: <out.pdf>      one 1920 x 1080 px page per slide (not written when a check fails)
 *          stdout         the report, one JSON line: counts, icons, fit adjustments, failures (ids only)
 * The combined document is written next to the PDF as <out>.html for printing and deleted afterwards (kept with
 * --keep-html). Exit status 1 when any check fails.
 *
 * Run (normally through build_deck_pdf.py):
 *   node viz/deliverables/deck_pdf.js <deck_dir> <assets.json> <out.pdf> [--keep-html]
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

const WIDTH = 1920;
const HEIGHT = 1080;
const BLOB = /\/_blob\/([0-9a-f]{32})/g;

const CSS = `
@page { size: ${WIDTH}px ${HEIGHT}px; margin: 0 }
html, body { margin: 0 }
* { margin: 0; padding: 0; box-sizing: border-box }
body { background: #FFFFFF; -webkit-print-color-adjust: exact; print-color-adjust: exact }
section { position: relative; width: ${WIDTH}px; height: ${HEIGHT}px; overflow: hidden; break-after: page }
section:last-of-type { break-after: auto }
aside { display: none }
x-shape { display: block }
x-shape[kind="ellipse"] { border-radius: 50% }
table { border-collapse: collapse; width: 100% }
td, th { padding: 10px 14px; vertical-align: top }
`;

// A badge outline: `lobes` arcs bulging out to about `outer`, meeting at points on a circle of radius `inner`.
function sealPath(lobes, inner, outer) {
  const at = (r, a) => `${(12 + r * Math.sin(a)).toFixed(2)} ${(12 - r * Math.cos(a)).toFixed(2)}`;
  const step = 2 * Math.PI / lobes;
  let d = `M${at(inner, 0)}`;
  for (let k = 0; k < lobes; k++) d += `Q${at(outer, (k + 0.5) * step)} ${at(inner, (k + 1) * step)}`;
  return d + 'Z';
}

// Icons on a 24-unit grid, stroked in currentColor (the x-icon's color); drawn for this deck.
const ICON_ATTRS = {
  viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round',
  'stroke-linejoin': 'round', 'aria-hidden': 'true',
};
const ICONS = {
  // a scalloped badge with a check mark
  Verified: `<path d="${sealPath(8, 7.6, 11.6)}"/><path d="M8.6 12.3l2.3 2.3 4.6-4.9"/>`,
  // a cylinder: top disc, sides, a band halfway down and the bottom rim
  Database: '<ellipse cx="12" cy="5.5" rx="7.5" ry="3"/><path d="M4.5 5.5v13a7.5 3 0 0 0 15 0v-13"/>'
    + '<path d="M4.5 12a7.5 3 0 0 0 15 0"/>',
  // a dial with hour and minute hands
  Clock: '<circle cx="12" cy="12" r="9"/><path d="M12 6.8V12l3.6 2.2"/>',
  // two rounded chain links overlapping on the diagonal
  Link: '<rect x="3.5" y="11.75" width="11" height="6.5" rx="3.25" transform="rotate(-45 9 15)"/>'
    + '<rect x="9.5" y="5.75" width="11" height="6.5" rx="3.25" transform="rotate(-45 15 9)"/>',
  // a circle with a check mark
  CheckCircle: '<circle cx="12" cy="12" r="9"/><path d="M8 12.4l2.7 2.7 5.3-5.6"/>',
};

const ENTITIES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ENTITIES[c]);
}

// The deck's slides as one document; image URLs point to the asset map's files.
function buildDocument(deckDir, assets, report) {
  const deck = JSON.parse(fs.readFileSync(path.join(deckDir, 'deck.json'), 'utf8'));
  const order = deck.order || [];
  const parts = [];
  for (const id of order) {
    const file = path.join(deckDir, 'slides', `${id}.html`);
    if (!fs.existsSync(file)) {
      report.errors.push(`slide ${id}: slides/${id}.html not found`);
      continue;
    }
    const html = fs.readFileSync(file, 'utf8').replace(BLOB, (m, blob) => {
      const target = assets[blob];
      if (!target || !fs.existsSync(target)) {
        report.errors.push(`slide ${id}: blob ${blob} ${target ? 'file not found' : 'not in the asset map'}`);
        return m;
      }
      return pathToFileURL(path.resolve(target)).href;
    });
    parts.push(html.trim());
  }
  const doc = `<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>${escapeHtml(deck.title || 'Deck')}`
    + `</title>\n<style>${CSS}</style></head>\n<body>\n${parts.join('\n')}\n</body></html>\n`;
  return { order, doc };
}

// In the page: stand in for x-icon and x-shape; count them.
function shimElements([order, icons, iconAttrs]) {
  const out = { icons: {}, shapes: 0, errors: [] };
  const sections = [...document.querySelectorAll('body > section')];
  sections.forEach((section, i) => {
    for (const el of section.querySelectorAll('x-icon')) {
      const name = el.getAttribute('name');
      if (!icons[name]) {
        out.errors.push(`slide ${order[i]}: unknown x-icon name ${JSON.stringify(name)}`);
        continue;
      }
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      for (const [k, v] of Object.entries(iconAttrs)) svg.setAttribute(k, v);
      svg.setAttribute('style', `${el.getAttribute('style') || ''};display:block;flex:none`);
      svg.innerHTML = icons[name];
      el.replaceWith(svg);
      out.icons[name] = (out.icons[name] || 0) + 1;
    }
    for (const el of section.querySelectorAll('x-shape')) {
      if (el.getAttribute('kind') === 'ellipse') out.shapes++;
      else out.errors.push(`slide ${order[i]}: unknown x-shape kind ${JSON.stringify(el.getAttribute('kind'))}`);
    }
  });
  return out;
}

// In the page: wait for every image to decode; list those that did not load (slide id and file name).
async function checkImages(order) {
  const out = { count: 0, loaded: 0, failed: [] };
  const sections = [...document.querySelectorAll('body > section')];
  for (const [i, section] of sections.entries()) {
    for (const img of section.querySelectorAll('img')) {
      out.count++;
      try {
        await img.decode();
      } catch (e) {
        // reported below
      }
      if (img.complete && img.naturalWidth > 0) {
        out.loaded++;
      } else {
        const src = img.getAttribute('src') || '';
        out.failed.push({ slide: order[i], file: decodeURIComponent(src.split('/').pop()) });
      }
    }
  }
  return out;
}

// In the page: shrink text that does not fit (see the header); report changes and what still does not fit.
function fitPass(order) {
  const TEXT = 'p, h1, h2, h3';
  const out = { checked: 0, adjustments: [], unresolved: [] };
  const sections = [...document.querySelectorAll('body > section')];
  const failed = new Set();
  const fontPx = el => parseFloat(getComputedStyle(el).fontSize);
  const floorFor = (tag, px) => {
    if (px <= 28) return Math.min(px, 20);
    if (tag === 'h1' || tag === 'h2') return Math.min(px, 40);
    return Math.ceil(px * 0.75);
  };
  const outside = (r, b) => r.left < b.left - 1 || r.top < b.top - 1 || r.right > b.right + 1
    || r.bottom > b.bottom + 1;
  // scrollHeight only for a fixed height: with a tight line-height (1 for the agenda's numbers) the font's ascent
  // and descent reach past the line box and count as overflow, although the box grows with its lines.
  const overflows = (el, section) => {
    if (el.scrollWidth > el.clientWidth + 1 || (el.style.height && el.scrollHeight > el.clientHeight + 1)) return true;
    const r = el.getBoundingClientRect();
    for (let box = el.parentElement; box; box = box.parentElement) {
      if (outside(r, box.getBoundingClientRect())) return true;
      if (box === section) break;
    }
    return false;
  };
  const shown = el => !el.closest('aside') && el.getClientRects().length > 0;
  const fail = (i, el, why, extra = {}) => {
    failed.add(el);
    out.unresolved.push({ slide: order[i], tag: el.tagName.toLowerCase(), ...extra, why });
  };

  sections.forEach((section, i) => {
    for (const el of section.querySelectorAll(TEXT)) {
      if (!shown(el)) continue;
      out.checked++;
      if (!overflows(el, section)) continue;
      const tag = el.tagName.toLowerCase();
      const from = fontPx(el);
      const floor = floorFor(tag, from);
      let size = from;
      while (overflows(el, section) && size - 1 >= floor) {
        size -= 1;
        el.style.fontSize = `${size}px`;
      }
      if (size !== from) out.adjustments.push({ slide: order[i], tag, from, to: size });
      if (overflows(el, section)) fail(i, el, 'text overflows at its floor', { from, to: size });
    }
  });

  // After all changes: the slides themselves, boxes of fixed height, and every text element once more.
  sections.forEach((section, i) => {
    if (section.scrollWidth > section.clientWidth + 1 || section.scrollHeight > section.clientHeight + 1) {
      fail(i, section, 'content runs off the slide');
    }
    for (const box of section.querySelectorAll('*')) {
      if (!(box instanceof HTMLElement) || !box.style.height || box.tagName === 'IMG' || !shown(box)) continue;
      if (!box.firstElementChild && !box.textContent.trim()) continue;
      if (box.scrollHeight > box.clientHeight + 1 || box.scrollWidth > box.clientWidth + 1) {
        fail(i, box, 'content overflows a box of fixed height');
      }
    }
    for (const el of section.querySelectorAll(TEXT)) {
      if (!failed.has(el) && shown(el) && overflows(el, section)) fail(i, el, 'text overflows after the fit pass');
    }
  });
  return out;
}

async function main() {
  const args = process.argv.slice(2);
  const keepHtml = args.includes('--keep-html');
  const [deckDir, assetsPath, outPdf] = args.filter(a => a !== '--keep-html');
  if (!deckDir || !assetsPath || !outPdf || !outPdf.endsWith('.pdf')) {
    console.error('usage: node deck_pdf.js <deck_dir> <assets.json> <out.pdf> [--keep-html]');
    process.exit(2);
  }
  const report = {
    slides: 0, sections: 0, images: null, icons: {}, shapes: 0, fit: null, errors: [], pdf: null,
  };
  const assets = JSON.parse(fs.readFileSync(assetsPath, 'utf8'));
  const { order, doc } = buildDocument(deckDir, assets, report);
  report.slides = order.length;
  const htmlPath = outPdf.replace(/\.pdf$/, '.html');
  fs.writeFileSync(htmlPath, doc);

  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: WIDTH, height: HEIGHT } });
    await page.goto(pathToFileURL(path.resolve(htmlPath)).href, { waitUntil: 'load' });
    report.sections = await page.evaluate(() => document.querySelectorAll('body > section').length);
    if (report.sections !== order.length) {
      report.errors.push(`${report.sections} sections in the document for ${order.length} slides`);
    } else {
      const ids = await page.evaluate(() => [...document.querySelectorAll('body > section')].map(s => s.id));
      ids.forEach((id, i) => {
        if (id && id !== order[i]) report.errors.push(`slide ${order[i]}: its section's id is ${JSON.stringify(id)}`);
      });
    }
    const shim = await page.evaluate(shimElements, [order, ICONS, ICON_ATTRS]);
    report.icons = shim.icons;
    report.shapes = shim.shapes;
    report.errors.push(...shim.errors);
    report.images = await page.evaluate(checkImages, order);
    if (report.images.failed.length) report.errors.push(`${report.images.failed.length} image(s) did not load`);

    await page.emulateMedia({ media: 'print' });
    await page.evaluate(() => document.fonts.ready.then(() => null));
    report.fit = await page.evaluate(fitPass, order);
    if (report.fit.unresolved.length) report.errors.push(`${report.fit.unresolved.length} fit failure(s)`);

    if (!report.errors.length) {
      await page.pdf({
        path: outPdf, width: `${WIDTH}px`, height: `${HEIGHT}px`, printBackground: true, preferCSSPageSize: true,
      });
      report.pdf = outPdf;
    }
  } finally {
    await browser.close();
    if (!keepHtml) fs.rmSync(htmlPath, { force: true });
  }
  console.log(JSON.stringify(report));
  if (report.errors.length) process.exitCode = 1;
}

main().catch(err => {
  console.error(`deck_pdf.js: ${err && err.message ? err.message.split('\n')[0] : err}`);
  process.exit(1);
});
