#!/usr/bin/env node
/*
IPA follow-ups on slides 4 and 5 as a PowerPoint deck, in the update deck's style (MIT A-Lab / Roper IPA).

Eleven follow-up charts (viz/figures/slides/sl_19 ... sl_31; none names a customer) on eight content slides:
4.1-4.4 (machines under 4 vs 4+ years) and 5.1-5.4 (repeat contacts), between a cover, an agenda and a closing slide.
Titles, card headers, takeaways, alt text and speaker notes come from viz/deliverables/followups_pptx.json: the
fact-checked text of the update deck's follow-up slides, renumbered (the update deck's 4d is 4.3 here), with slide
4.1 pairing sl_19 and sl_20, which the update deck shows on separate slides.

The look is the update deck's: slides designed at 1920 x 1080 px are drawn at 144 px to the inch on the 13.33 x 7.5 in
page, so 1 px = 0.5 pt. Arial; titles 24 pt bold in the deck's blue; a section label, progress dots and the MIT logo in
the header; cards with a gray header band; the Key Takeaway bar; the confidentiality footer and a slide label (4.1 ...).
It is a structured deck: a theme (Arial, the deck's colours as scheme colours, written into the theme part after the
file is saved), one layout per frame (cover, agenda, content per section, closing) carrying the header, footer, logo,
takeaway bar and the title, takeaway and label placeholders, and one section per part. Cards are composed per slide.

Inputs:  viz/deliverables/followups_pptx.json; viz/figures/slides/sl_NN_*.png;
         --assets DIR holding the deck's mit_logo.png, ipa_logo.png and sloan_photo.jpg
Output:  deliverables/IPA_Followups_30Oct2026.pptx, or --out FILE
Run:     NODE_PATH=<node_modules with pptxgenjs> node viz/deliverables/followups_pptx.js --assets DIR [--out FILE]
*/
'use strict';
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const PptxGenJS = require('pptxgenjs');

const ROOT = path.resolve(__dirname, '..', '..');
const FIG = path.join(ROOT, 'viz', 'figures', 'slides');
const CONTENT = path.join(__dirname, 'followups_pptx.json');

const px = (v) => v / 144;  // inches, from px of the 1920 x 1080 design
const HEX = {
  ink: '20252B', blue: '215F9B', white: 'FFFFFF', band: 'F2F2F2', navy: '005493', dot: 'C9CFD6', border: 'D8D8D8',
  gray: '64717D', ink2: '3A444E',
};
const THEME = {
  name: 'IPA A-Lab', headFontFace: 'Arial', bodyFontFace: 'Arial',
  colors: {
    dk1: HEX.ink, lt1: HEX.white, dk2: HEX.blue, lt2: HEX.band, accent1: HEX.blue, accent2: HEX.navy,
    accent3: HEX.dot, accent4: HEX.border, accent5: HEX.gray, accent6: HEX.ink2, hlink: HEX.blue, folHlink: HEX.gray,
  },
};
const FOOTER = 'MIT A-Lab · Roper IPA · Confidential - Do Not Share';
const CARD_TOP = 232, CARD_H = 634, BAND_H = 67;        // the update deck's card geometry (px)

function args(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 2) {
    if (!['--assets', '--out'].includes(argv[i]) || argv[i + 1] === undefined) {
      throw new Error(`usage: node followups_pptx.js --assets DIR [--out FILE] (got ${argv.join(' ')})`);
    }
    out[argv[i].slice(2)] = argv[i + 1];
  }
  if (!out.assets) throw new Error('--assets DIR is required (mit_logo.png, ipa_logo.png, sloan_photo.jpg)');
  return out;
}

function pngSize(file) {
  const b = fs.readFileSync(file);
  if (b.readUInt32BE(12) !== 0x49484452) throw new Error(`${file} is not a PNG`);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}

function jpegSize(file) {
  const b = fs.readFileSync(file);
  for (let i = 2; i < b.length;) {                       // walk the markers to the first start-of-frame
    const marker = b[i + 1], len = b.readUInt16BE(i + 2);
    if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) {
      return { w: b.readUInt16BE(i + 7), h: b.readUInt16BE(i + 5) };
    }
    i += 2 + len;
  }
  throw new Error(`${file}: no JPEG frame header`);
}

function contain(box, img) {
  // The largest rectangle of the image's shape inside box (px), centred in it.
  const s = Math.min(box.w / img.w, box.h / img.h);
  const w = img.w * s, h = img.h * s;
  return { x: box.x + (box.w - w) / 2, y: box.y + (box.h - h) / 2, w, h };
}

function gradientPng(w, h) {
  // The Key Takeaway label block: #C5D3E5 to #A9BFD8 over the first 62%, then the deck's blue, as in the deck's CSS.
  const rgb = (hex) => [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const [a, b, c] = [rgb('C5D3E5'), rgb('A9BFD8'), rgb(HEX.blue)];
  const row = Buffer.alloc(1 + w * 3);                   // filter byte 0, then RGB
  for (let x = 0; x < w; x++) {
    const f = x / w;
    row.set(f < 0.62 ? a.map((v, i) => Math.round(v + (b[i] - v) * f / 0.62)) : c, 1 + x * 3);
  }
  const chunk = (type, data) => {
    const body = Buffer.concat([Buffer.from(type), data]);
    const len = Buffer.alloc(4), crc = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    crc.writeUInt32BE(zlib.crc32(body) >>> 0);
    return Buffer.concat([len, body, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8;                                           // bit depth
  ihdr[9] = 2;                                           // truecolour
  const raw = Buffer.concat(Array.from({ length: h }, () => row));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

async function writeTheme(file, theme) {
  // pptxgenjs writes Office's palette into ppt/theme/theme1.xml; put the deck's colours and name there instead.
  const JSZip = require(require.resolve('jszip', { paths: [require.resolve('pptxgenjs')] }));
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  const part = 'ppt/theme/theme1.xml';
  const slots = Object.keys(theme.colors);
  const scheme = `<a:clrScheme name="${theme.name}">`
    + slots.map((k) => `<a:${k}><a:srgbClr val="${theme.colors[k]}"/></a:${k}>`).join('') + '</a:clrScheme>';
  const xml = (await zip.file(part).async('string'))
    .replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => scheme)
    .replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, head) => `${head}${theme.name}"`);
  if (!xml.includes(scheme)) throw new Error(`${part}: no colour scheme to replace`);
  zip.file(part, xml);
  for (const name of Object.keys(zip.files).filter((n) => n.endsWith('.xml'))) {
    const bad = (await zip.file(name).async('string')).match(/<a:srgbClr val="((?![0-9A-Fa-f]{6}")[^"]*)"/);
    if (bad) {
      throw new Error(`${name}: colour "${bad[1]}" is not six hex digits (a scheme colour in a hex-only option)`);
    }
  }
  fs.writeFileSync(file, await zip.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' }));
}

async function main() {
  const opt = args(process.argv.slice(2));
  const deck = JSON.parse(fs.readFileSync(CONTENT, 'utf8'));
  const asset = (name) => {
    const p = path.join(opt.assets, name);
    if (!fs.existsSync(p)) throw new Error(`missing asset ${p}`);
    return p;
  };
  const MIT = asset('mit_logo.png'), IPA = asset('ipa_logo.png'), PHOTO = asset('sloan_photo.jpg');
  const out = opt.out || path.join(ROOT, 'deliverables', 'IPA_Followups_30Oct2026.pptx');
  fs.mkdirSync(path.dirname(out), { recursive: true });

  const pres = new PptxGenJS();
  pres.layout = 'LAYOUT_WIDE';                           // 13.33 x 7.5 in = 1920 x 1080 px at 144 px/in
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = deck.file_title;
  pres.author = 'MIT Analytics Lab';
  const C = pres.SchemeColor, S = pres.ShapeType;
  const box = (x, y, w, h) => ({ x: px(x), y: px(y), w: px(w), h: px(h) });
  const mitTop = contain({ x: 1658, y: 22, w: 190, h: 45 }, pngSize(MIT));
  const mitBottom = contain({ x: 1658, y: 996, w: 190, h: 45 }, pngSize(MIT));
  const ipaLogo = contain({ x: 72, y: 990, w: 80, h: 47 }, pngSize(IPA));
  const footer = (color, w = 900) => ({ text: { text: FOOTER, options: {
    ...box(72, 1004, w, 30), fontSize: 12, color, margin: 0, valign: 'top' } } });
  const dot = (x, color) => ({ text: { text: '', options: { ...box(x, 30, 18, 18), shape: S.ellipse,
    fill: { color }, line: { color, width: 0 } } } });
  const placeholder = (name, type, b, o) => ({
    placeholder: { options: { name, type, ...b, margin: 0, ...o }, text: '' } });

  // Layouts --------------------------------------------------------------------------------------------------------
  pres.defineSlideMaster({
    title: 'IPA_COVER', background: { color: C.background1 },
    objects: [
      { text: { text: '', options: { ...box(0, 540, 156, 270), shape: S.homePlate, fill: { color: C.accent1 },
        line: { color: C.accent1, width: 0 } } } },
      placeholder('title', 'title', box(216, 648, 1640, 100), { fontSize: 20, bold: true, color: C.text2,
        align: 'left', valign: 'top', lineSpacingMultiple: 1.0 }),
      placeholder('subtitle', 'body', box(216, 762, 1600, 40), { fontSize: 14, bold: true, italic: true,
        color: C.text1, valign: 'top' }),
      placeholder('details', 'body', box(216, 808, 1600, 140), { fontSize: 12, color: C.text1, valign: 'top',
        lineSpacingMultiple: 1.35 }),
      { image: { ...box(ipaLogo.x, ipaLogo.y, ipaLogo.w, ipaLogo.h), path: IPA, altText: 'IPA logo' } },
      { text: { text: FOOTER, options: { ...box(216, 1004, 900, 30), fontSize: 12, color: C.accent5, margin: 0 } } },
      { image: { ...box(mitBottom.x, mitBottom.y, mitBottom.w, mitBottom.h), path: MIT, altText: 'MIT logo' } },
    ],
  });
  pres.defineSlideMaster({
    title: 'IPA_AGENDA', background: { color: C.background1 },
    objects: [
      { rect: { ...box(765, 0, 1155, 1080), fill: { color: C.accent2 } } },
      { rect: { ...box(56, 18, 10, 46), fill: { color: C.accent1 } } },
      { text: { text: 'Agenda', options: { ...box(80, 22, 600, 39), fontSize: 13, color: C.text1, margin: 0 } } },
      placeholder('title', 'title', box(72, 96, 620, 70), { fontSize: 26, bold: true, color: C.text2, align: 'left',
        valign: 'top' }),
      footer(C.accent5, 660),
    ],
  });
  const takeawayPng = 'image/png;base64,' + gradientPng(1000, 160).toString('base64');
  const dotsLeft = 960 - ((deck.sections.length - 1) * 36 + 18) / 2;   // one dot per section, centred as in the deck
  for (const [k, sec] of deck.sections.entries()) {
    pres.defineSlideMaster({
      title: `IPA_CONTENT_${sec.key}`, background: { color: C.background1 },
      objects: [
        { rect: { ...box(56, 18, 10, 46), fill: { color: C.accent1 } } },
        { text: { text: sec.label, options: { ...box(80, 22, 760, 39), fontSize: 13, color: C.text1, margin: 0,
          valign: 'middle' } } },
        ...deck.sections.map((_, i) => dot(dotsLeft + 36 * i, i === k ? C.accent1 : C.accent3)),
        { image: { ...box(mitTop.x, mitTop.y, mitTop.w, mitTop.h), path: MIT, altText: 'MIT logo' } },
        placeholder('title', 'title', box(72, 88, 1776, 125), { fontSize: 24, bold: true, color: C.text2,
          align: 'left', valign: 'top', lineSpacingMultiple: 1.0 }),
        // Key Takeaway bar: the label block (gradient, then blue) and the takeaway text on light gray.
        { image: { ...box(186, 874, 500, 80), data: takeawayPng, altText: 'Key Takeaway bar' } },
        { text: { text: 'Key Takeaway', options: { ...box(208, 874, 280, 80), fontSize: 14, bold: true,
          color: C.text1, margin: 0, valign: 'middle' } } },
        { rect: { ...box(686, 874, 1048, 80), fill: { color: C.background2 } } },
        placeholder('takeaway', 'body', box(710, 874, 1000, 80), { fontSize: 13, color: C.text1, valign: 'middle',
          lineSpacingMultiple: 1.0 }),
        footer(C.accent5),
        placeholder('label', 'body', box(1748, 1004, 100, 30), { fontSize: 12, color: C.accent5, align: 'right',
          valign: 'top' }),
      ],
    });
  }
  pres.defineSlideMaster({
    title: 'IPA_CLOSING', background: { color: C.background1 },
    objects: [
      { rect: { ...box(0, 0, 765, 1080), fill: { color: C.accent2 } } },
      { text: { text: 'Thank You', options: { ...box(0, 480, 765, 110), fontSize: 28, bold: true,
        color: C.background1, align: 'center', valign: 'middle', margin: 0 } } },
      { text: { text: 'Questions?', options: { ...box(765, 490, 1155, 110), fontSize: 28, bold: true,
        color: C.text1, align: 'center', valign: 'middle', margin: 0 } } },
      footer(C.background1, 660),
      { image: { ...box(mitBottom.x, mitBottom.y, mitBottom.w, mitBottom.h), path: MIT, altText: 'MIT logo' } },
    ],
  });

  // Slides ---------------------------------------------------------------------------------------------------------
  const counts = { slides: 0, charts: 0, notes: 0 };
  const charts = [];

  pres.addSection({ title: 'Opening' });
  const cover = pres.addSlide({ masterName: 'IPA_COVER', sectionTitle: 'Opening' });
  const photo = jpegSize(PHOTO);
  cover.addImage({ path: PHOTO, x: 0, y: 0, w: px(1920), h: px(1920 * photo.h / photo.w),
    sizing: { type: 'cover', w: px(1920), h: px(620) }, altText: deck.cover.photo_alt,
    objectName: 'Cover photo' });
  cover.addText(deck.cover.title, { placeholder: 'title' });
  cover.addText(deck.cover.subtitle, { placeholder: 'subtitle' });
  const line = (label, value, last) => [
    { text: `${label}: `, options: {} }, { text: value, options: { bold: true, breakLine: !last } }];
  cover.addText([...line('Date', deck.cover.date), ...line('IPA collaborators', deck.cover.collaborators),
    ...line('Authors', deck.cover.authors), ...line('Supervisors', deck.cover.supervisors, true)],
  { placeholder: 'details' });
  cover.addNotes(deck.cover.notes);
  counts.notes += 1;

  const agenda = pres.addSlide({ masterName: 'IPA_AGENDA', sectionTitle: 'Opening' });
  agenda.addText('Agenda', { placeholder: 'title' });
  const step = 178, first = 540 - step * (deck.sections.length - 1) / 2 - 50;
  deck.sections.forEach((sec, i) => {
    const y = first + step * i;
    agenda.addText(String(i + 1), { ...box(846, y, 90, 100), fontSize: 50, bold: true, color: C.background1,
      margin: 0, valign: 'middle', isTextBox: true, objectName: `Agenda number ${i + 1}` });
    agenda.addText(sec.agenda, { ...box(950, y + 10, 900, 80), fontSize: 19, bold: true, color: C.background1,
      margin: 0, valign: 'middle', isTextBox: true, objectName: `Agenda item ${i + 1}` });
  });
  agenda.addNotes(deck.agenda_notes);
  counts.notes += 1;

  const card = (slide, x, w, header, n) => {
    slide.addShape(S.roundRect, { ...box(x, CARD_TOP, w, CARD_H), fill: { color: C.background1 },
      line: { color: C.accent4, width: 0.5 }, rectRadius: px(14), objectName: `Card ${n}` });
    slide.addShape(S.round2SameRect, { ...box(x, CARD_TOP, w, BAND_H), fill: { color: C.background2 },
      line: { color: C.accent4, width: 0.5 }, objectName: `Card ${n} header band` });
    slide.addText(header, { ...box(x + 28, CARD_TOP + 14, w - 56, BAND_H - 28), fontSize: 14, bold: true,
      color: C.text1, margin: 0, valign: 'middle', isTextBox: true, objectName: `Card ${n} header` });
  };
  const chart = (slide, x, w, c, n) => {
    const file = path.join(FIG, c.png);
    const r = contain({ x: x + 17, y: CARD_TOP + BAND_H + 16, w: w - 34, h: 532 }, pngSize(file));
    slide.addImage({ path: file, ...box(r.x, r.y, r.w, r.h), altText: c.alt, objectName: `Card ${n} chart` });
    charts.push(c.png);
  };
  const textCard = (slide, x, w, c, n) => {
    const top = CARD_TOP + BAND_H + 24, bottom = CARD_TOP + CARD_H - 24, slot = (bottom - top) / c.items.length;
    c.items.forEach(([head, body], i) => {
      const y = top + slot * i;
      slide.addText(String(i + 1), { ...box(x + 32, y + (slot - 56) / 2, 56, 56), shape: S.roundRect,
        rectRadius: px(10), fill: { color: C.accent1 }, fontSize: 15, bold: true, color: C.background1,
        align: 'center', valign: 'middle', margin: 0, objectName: `Card ${n} item ${i + 1} number` });
      slide.addText([{ text: head, options: { bold: true, fontSize: 13, color: C.text1, breakLine: true } },
        { text: body, options: { fontSize: 12, color: C.accent6 } }],
      { ...box(x + 112, y, w - 144, slot), margin: 0, valign: 'middle', paraSpaceAfter: 2, isTextBox: true,
        objectName: `Card ${n} item ${i + 1}` });
    });
  };

  for (const sec of deck.sections) {
    pres.addSection({ title: sec.agenda });
    for (const s of sec.slides) {
      const slide = pres.addSlide({ masterName: `IPA_CONTENT_${sec.key}`, sectionTitle: sec.agenda });
      slide.addText(s.title, { placeholder: 'title' });
      slide.addText(s.takeaway, { placeholder: 'takeaway' });
      slide.addText(s.label, { placeholder: 'label' });
      const slots = s.cards.length === 1 ? [[72, 1776]] : [[72, 862], [986, 862]];
      if (s.cards.length > 2) throw new Error(`slide ${s.label}: at most two cards`);
      s.cards.forEach((c, i) => {
        const [x, w] = slots[i];
        card(slide, x, w, c.header, i + 1);
        if (c.kind === 'chart') chart(slide, x, w, c, i + 1);
        else textCard(slide, x, w, c, i + 1);
      });
      slide.addNotes(s.notes);
      counts.notes += 1;
    }
  }

  pres.addSection({ title: 'Close' });
  pres.addSlide({ masterName: 'IPA_CLOSING', sectionTitle: 'Close' });
  counts.slides = pres.slides.length;
  counts.charts = charts.length;

  const file = await pres.writeFile({ fileName: out });
  await writeTheme(file, THEME);
  console.log(`wrote ${path.relative(ROOT, file)}: ${counts.slides} slides, ${counts.charts} charts `
    + `(${charts.map((c) => c.split('_')[1]).join(', ')}), ${counts.notes} slides with notes`);
}

main().catch((e) => {
  console.error(`Error: ${e.message}`);
  process.exit(1);
});
