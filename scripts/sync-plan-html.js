#!/usr/bin/env node
'use strict';

/**
 * sync-plan-html.js
 *
 * Reads docs/IMPLEMENTATION-PLAN.md and rewrites the PHASES and OPEN_ITEMS
 * arrays in docs/IMPLEMENTATION-PLAN.html, including:
 *
 *   phase.details — HTML rendered from content between the goal block and
 *                   the first task (tables, file lists, notes, etc.)
 *   task.body     — HTML rendered from content between consecutive task
 *                   headers (commands, code blocks, explanations)
 *
 * Usage: node scripts/sync-plan-html.js
 */

const fs   = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const MD   = path.join(ROOT, 'docs', 'IMPLEMENTATION-PLAN.md');
const HTML = path.join(ROOT, 'docs', 'IMPLEMENTATION-PLAN.html');

// ── Inline Markdown → HTML ──────────────────────────────────────────
// Handles backtick code and bold only; used for single-line strings
// (goal text, task text, table cells).

function md2html(s) {
  return s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

// ── HTML escaping ───────────────────────────────────────────────────

function escHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── Markdown table → HTML <table> ───────────────────────────────────

function renderTable(lines) {
  // Drop separator rows (e.g. |---|---|)
  const dataLines = lines.filter(l => !/^\|[\s\-:|]+\|/.test(l));
  if (!dataLines.length) return '';

  const parseRow = l => l.split('|').map(c => c.trim()).filter(Boolean);
  const [header, ...rows] = dataLines;

  let html = '<table>';
  html += '<thead><tr>'
    + parseRow(header).map(h => `<th>${md2html(h)}</th>`).join('')
    + '</tr></thead>';
  html += '<tbody>'
    + rows.map(r => '<tr>' + parseRow(r).map(c => `<td>${md2html(c)}</td>`).join('') + '</tr>').join('')
    + '</tbody>';
  return html + '</table>\n';
}

// ── Full Markdown block → HTML ──────────────────────────────────────
// Handles: fenced code blocks, tables, blockquotes, unordered lists,
// paragraphs (with inline md). Skips horizontal rules (---).
// Task body content is indented 2 spaces in the MD; strip that first.

function md2htmlFull(md) {
  if (!md || !md.trim()) return '';

  // Strip 2-space indentation used by task body content in MD list items
  const lines = md.split('\n').map(l => l.replace(/^  /, ''));
  let html = '';
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Blank line — skip
    if (/^\s*$/.test(line)) { i++; continue; }

    // Horizontal rule — skip
    if (/^---+$/.test(line.trim())) { i++; continue; }

    // Fenced code block: ```lang ... ```
    if (/^```/.test(line)) {
      const codeLines = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // consume closing ```
      html += `<pre><code>${escHtml(codeLines.join('\n'))}</code></pre>\n`;
      continue;
    }

    // Table: lines starting with |
    if (/^\|/.test(line)) {
      const tableLines = [];
      while (i < lines.length && /^\|/.test(lines[i])) {
        tableLines.push(lines[i]);
        i++;
      }
      html += renderTable(tableLines);
      continue;
    }

    // Blockquote: > text
    if (/^>/.test(line)) {
      const quoteLines = [];
      while (i < lines.length && /^>/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^>\s?/, ''));
        i++;
      }
      html += `<blockquote>${md2html(quoteLines.join(' '))}</blockquote>\n`;
      continue;
    }

    // Unordered list: - or * followed by space
    if (/^[-*]\s/.test(line)) {
      const items = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s+/, ''));
        i++;
      }
      html += '<ul>'
        + items.map(t => `<li>${md2html(t)}</li>`).join('')
        + '</ul>\n';
      continue;
    }

    // Paragraph: accumulate until blank line, code fence, table, list, or rule
    const paraLines = [];
    while (
      i < lines.length &&
      !/^\s*$/.test(lines[i]) &&
      !/^```/.test(lines[i]) &&
      !/^\|/.test(lines[i]) &&
      !/^>/.test(lines[i]) &&
      !/^[-*]\s/.test(lines[i]) &&
      !/^---+$/.test(lines[i].trim())
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length) {
      html += `<p>${md2html(paraLines.join(' '))}</p>\n`;
    }
  }

  return html;
}

// ── Parsers ─────────────────────────────────────────────────────────

function parseMd(src) {
  const phases = [];

  // Split on level-2 phase headings; keep only phase chunks
  const chunks = src
    .split(/^(?=## Phase)/m)
    .filter(c => /^## Phase/.test(c));

  for (const chunk of chunks) {
    const firstLine = chunk.split('\n')[0];

    // Match: ## Phase −1 — Title  or  ## Phase 0 — Title
    // The em-dash (—) is U+2014; Unicode minus (−, U+2212) normalised below
    const hm = firstLine.match(/^## Phase\s+(.+?)\s+—\s+(.+)$/);
    if (!hm) continue;

    const numDisplay = hm[1].trim();
    const numAscii   = numDisplay.replace(/−/g, '-'); // U+2212 → ASCII hyphen
    const id         = `phase-${numAscii}`;
    const label      = `Phase ${numDisplay}`;
    const title      = `${label} — ${hm[2].trim()}`;

    // ── Goal ──────────────────────────────────────────────────────
    // Stop before a double newline, **Files section, or any **CAP heading
    const gm = chunk.match(
      /\*\*Goal:\*\*\s*([\s\S]+?)(?=\n\n|\*\*Files|\*\*[A-Z]|^---)/m
    );
    const goal = gm
      ? md2html(gm[1].replace(/\n/g, ' ').trim())
      : '';

    // ── Details ───────────────────────────────────────────────────
    // Everything between the end of the goal block and the first task header
    const firstTaskPos = chunk.search(/^- \[[ x]\]/m);
    let details = '';
    if (gm && firstTaskPos > 0) {
      const goalBlockEnd = chunk.indexOf(gm[0]) + gm[0].length;
      const detailsRaw   = chunk.slice(goalBlockEnd, firstTaskPos).trim();
      details = md2htmlFull(detailsRaw);
    }

    // ── Tasks with bodies ──────────────────────────────────────────
    // Find all task header positions, then slice the text between them
    const taskMatches = [];
    const taskRe = /^- \[[ x]\] \*\*[^*]+\*\*/gm;
    let tm;
    while ((tm = taskRe.exec(chunk)) !== null) {
      taskMatches.push({ index: tm.index, end: tm.index + tm[0].length, header: tm[0] });
    }

    const tasks = [];
    for (let j = 0; j < taskMatches.length; j++) {
      const bodyStart = taskMatches[j].end;
      const bodyEnd   = j + 1 < taskMatches.length
        ? taskMatches[j + 1].index
        : chunk.length;
      const bodyRaw   = chunk.slice(bodyStart, bodyEnd).trim();

      // Extract task ID (supports negative: −1.1) and label from header
      const full = taskMatches[j].header
        .replace(/^- \[[ x]\] \*\*/, '')
        .replace(/\*\*$/, '')
        .trim();
      const im = full.match(/^([-−\d]+\.\d+)\s+(.+)$/); // [-−] = ASCII + Unicode minus
      if (!im) continue;

      tasks.push({
        id:   im[1],
        text: md2html(im[2]),
        body: md2htmlFull(bodyRaw),
      });
    }

    if (tasks.length) phases.push({ id, label, title, goal, details, tasks });
  }

  return phases;
}

function parseOpenItems(src) {
  const tm = src.match(
    /\| #[^|]*\| Item[^|]*\| Phase[^|]*\| Status[^|]*\|\s*\n\|[-| ]+\|\s*\n((?:\|[^\n]+\|\s*\n?)+)/
  );
  if (!tm) return [];

  return tm[1].trim().split('\n').map(row => {
    const cols = row.split('|').map(c => c.trim()).filter(Boolean);
    if (cols.length < 4) return null;
    const [num, text, phase, status] = cols;
    const s = status.toLowerCase();
    return {
      num:    parseInt(num, 10),
      text:   text.replace(/\*\*/g, ''),
      phase,
      status: s.includes('defer')       ? 'deferred'
             : s.includes('outstanding') ? 'outstanding'
             : 'critical',
    };
  }).filter(Boolean);
}

// ── JS generation ───────────────────────────────────────────────────

// Escape for single-quoted JS string literals (also escapes newlines so
// multi-line HTML bodies remain valid inside the generated source).
function esc(s) {
  return s
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/\r/g, '')
    .replace(/\n/g, '\\n');
}

function phasesToJs(phases) {
  const body = phases.map(p => {
    const tasks = p.tasks
      .map(t =>
        `      { id: '${esc(t.id)}', text: '${esc(t.text)}', body: '${esc(t.body)}' }`
      )
      .join(',\n');
    return (
      `  {\n` +
      `    id: '${esc(p.id)}',\n` +
      `    label: '${esc(p.label)}',\n` +
      `    title: '${esc(p.title)}',\n` +
      `    goal: '${esc(p.goal)}',\n` +
      `    details: '${esc(p.details)}',\n` +
      `    tasks: [\n${tasks}\n    ]\n` +
      `  }`
    );
  }).join(',\n');
  return `const PHASES = [\n${body}\n];`;
}

function openItemsToJs(items) {
  const body = items
    .map(i =>
      `  { num: ${i.num}, text: '${esc(i.text)}', phase: '${esc(i.phase)}', status: '${esc(i.status)}' }`
    )
    .join(',\n');
  return `const OPEN_ITEMS = [\n${body}\n];`;
}

// ── Array replacement (bracket-depth aware) ─────────────────────────
// Replaces `const NAME = [...];` by counting bracket depth so nested
// arrays/objects inside string values do not confuse the search.

function replaceConst(src, varName, newDecl) {
  const marker = `const ${varName} = [`;
  const start  = src.indexOf(marker);
  if (start === -1) throw new Error(`"${varName}" not found in HTML`);

  let depth = 0, i = start + marker.length - 1; // i starts at opening [
  while (i < src.length) {
    if      (src[i] === '[') depth++;
    else if (src[i] === ']') { depth--; if (depth === 0) break; }
    i++;
  }
  let end = i + 1;
  if (src[end] === ';') end++; // consume trailing semicolon

  return src.slice(0, start) + newDecl + src.slice(end);
}

// ── Main ─────────────────────────────────────────────────────────────

const mdSrc   = fs.readFileSync(MD,   'utf8');
const htmlSrc = fs.readFileSync(HTML, 'utf8');

const phases    = parseMd(mdSrc);
const openItems = parseOpenItems(mdSrc);

if (!phases.length) {
  console.error('ERROR: no phases parsed -- check heading format in MD.');
  process.exit(1);
}

let out = replaceConst(htmlSrc, 'PHASES',     phasesToJs(phases));
    out = replaceConst(out,     'OPEN_ITEMS', openItemsToJs(openItems));

fs.writeFileSync(HTML, out, 'utf8');
console.log(`Synced: ${phases.length} phases, ${openItems.length} open items -> ${path.relative(ROOT, HTML)}`);
