// Runs in an isolated world inside a web tab: page scripts can't see it, and it shares only the DOM.
// Atlas pulls batches of untranslated text (on-screen first), translates them and writes the results
// back into the same text nodes, so the page keeps its layout, links and scripts. Text is sent one
// block (paragraph, heading, list item) at a time, each text node marked with a numbered span, so a
// sentence split by links or bold text is translated as one sentence and the pieces land back in place.
(() => {
  if (window.__atlasTranslate) return true;
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'TEXTAREA', 'CODE', 'PRE', 'KBD', 'SAMP', 'VAR', 'SVG', 'MATH', 'CANVAS', 'IFRAME']);
  const UNIT_NODES = 40, UNIT_CHARS = 3000;
  const done = new WeakMap();     // node -> { original, translation }
  const inFlight = new WeakMap(); // node -> text sent for it
  const sent = new Map();         // unit id -> [{ node, text }]
  const touched = new Set();
  let nextId = 1, dirty = true;
  const observer = new MutationObserver(() => { dirty = true; });

  function skipped(element) {
    for (let node = element; node && node !== document.documentElement; node = node.parentElement) {
      if (SKIP.has(node.tagName.toUpperCase()) || node.isContentEditable) return true;
      if (node.getAttribute('translate') === 'no' || node.classList.contains('notranslate')) return true;
    }
    return false;
  }

  function wanted(node) {
    const text = node.nodeValue;
    if (!text || !/\p{L}.*\p{L}/su.test(text)) return false;
    const record = done.get(node);
    if (record && record.translation === text) return false;
    if (inFlight.get(node) === text) return false;
    return !skipped(node.parentElement);
  }

  function blockOf(node) {
    for (let element = node.parentElement; element; element = element.parentElement) {
      if (element === document.body || !getComputedStyle(element).display.startsWith('inline')) return element;
    }
    return document.body;
  }

  const escape = text => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  function collect(limit) {
    if (!document.body) return [];
    dirty = false;
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    const blocks = new Map();
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!wanted(node)) continue;
      const block = blockOf(node);
      if (!blocks.has(block)) blocks.set(block, []);
      blocks.get(block).push(node);
    }
    const onScreen = [], later = [], height = window.innerHeight;
    for (const [block, nodes] of blocks) {
      const box = block.getBoundingClientRect();
      const list = box.width && box.bottom > 0 && box.top < height ? onScreen : later;
      let unit = [], size = 0;
      for (const node of nodes) {
        if (unit.length && (unit.length >= UNIT_NODES || size + node.nodeValue.length > UNIT_CHARS)) { list.push(unit); unit = []; size = 0; }
        unit.push(node); size += node.nodeValue.length;
      }
      if (unit.length) list.push(unit);
    }
    const picked = onScreen.concat(later).slice(0, limit);
    if (onScreen.length + later.length > limit) dirty = true;
    return picked.map(nodes => {
      const id = nextId++;
      sent.set(id, nodes.map(node => ({ node, text: node.nodeValue })));
      for (const node of nodes) inFlight.set(node, node.nodeValue);
      const html = nodes.length === 1
        ? escape(nodes[0].nodeValue.trim())
        : nodes.map((node, index) => `<span id="t${index}">${escape(node.nodeValue)}</span>`).join('');
      return { id, text: html };
    });
  }

  function pieces(html, count) {
    const parsed = new DOMParser().parseFromString(`<body>${html}</body>`, 'text/html');
    if (count === 1) return [parsed.body.textContent];
    return Array.from({ length: count }, (_, index) => {
      const span = parsed.getElementById(`t${index}`);
      return span ? span.textContent : null;
    });
  }

  function apply(items) {
    for (const { id, text } of items) {
      const entries = sent.get(id);
      sent.delete(id);
      if (!entries) continue;
      for (const entry of entries) inFlight.delete(entry.node);
      if (typeof text !== 'string' || !text.trim()) continue;
      const translated = pieces(text, entries.length);
      entries.forEach((entry, index) => {
        const piece = translated[index];
        if (piece == null || entry.node.nodeValue !== entry.text) return;
        const lead = entry.text.match(/^\s*/)[0], trail = entry.text.match(/\s*$/)[0];
        const translation = piece.trim() ? lead + piece.trim() + trail : entry.text;
        const record = done.get(entry.node);
        done.set(entry.node, { original: record && record.translation === entry.text ? record.original : entry.text, translation });
        entry.node.nodeValue = translation;
        touched.add(entry.node);
      });
    }
  }

  function release(ids) {
    for (const id of ids) {
      for (const entry of sent.get(id) || []) inFlight.delete(entry.node);
      sent.delete(id);
    }
  }

  function restore() {
    observer.disconnect();
    sent.clear();
    for (const node of touched) {
      const record = done.get(node);
      if (record && node.nodeValue === record.translation) node.nodeValue = record.original;
      done.delete(node);
    }
    touched.clear();
    delete window.__atlasTranslate;
  }

  window.__atlasTranslate = { collect, apply, release, restore, dirty: () => dirty };
  return true;
})();
