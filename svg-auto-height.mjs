/**
 * SVG auto-height helper for 场景英译 cards.
 * Measures content via a dry-run layout pass; no rsvg-convert / Inkscape.
 */

export function escapeXml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

/** Rough CJK-aware text width in px at given font-size */
export function measureText(text, fontSize, opts = {}) {
  const { cjk = 1.0, latin = 0.55 } = opts;
  let w = 0;
  for (const ch of String(text ?? "")) {
    if (/[\u0000-\u00ff]/.test(ch)) w += fontSize * latin;
    else w += fontSize * cjk;
  }
  return w;
}

/** Wrap text into lines that fit maxWidth */
export function wrapText(text, fontSize, maxWidth, opts = {}) {
  const s = String(text ?? "");
  if (!s) return [""];
  const lines = [];
  let cur = "";
  for (const ch of s) {
    const next = cur + ch;
    if (measureText(next, fontSize, opts) > maxWidth && cur) {
      lines.push(cur);
      cur = ch;
    } else {
      cur = next;
    }
  }
  if (cur) lines.push(cur);
  return lines.length ? lines : [""];
}

/**
 * Layout cursor helper
 */
export function createLayout(startY = 0) {
  let y = startY;
  const marks = [];
  return {
    get y() {
      return y;
    },
    set y(v) {
      y = v;
    },
    add(dy) {
      y += dy;
      return y;
    },
    mark(name) {
      marks.push({ name, y });
    },
    marks,
  };
}

/**
 * Build final SVG string.
 * @param {object} opts
 * @param {number} opts.width
 * @param {number} opts.height - content height (viewBox / height)
 * @param {string} opts.css
 * @param {string} opts.body - inner SVG markup
 * @param {string} [opts.className]
 */
export function buildSvg({ width, height, css, body, className = "scene-card" }) {
  const h = Math.ceil(height);
  const w = Math.ceil(width);
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" class="${escapeXml(className)}">
  <defs>
    <style type="text/css"><![CDATA[
${css}
    ]]></style>
    <linearGradient id="bgGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#f0faf6"/>
      <stop offset="45%" stop-color="#e6f5ef"/>
      <stop offset="100%" stop-color="#d9efe6"/>
    </linearGradient>
    <linearGradient id="headerGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#0d7377"/>
      <stop offset="100%" stop-color="#14919b"/>
    </linearGradient>
  </defs>
  <rect class="page-bg" width="100%" height="100%" fill="url(#bgGrad)"/>
${body}
</svg>
`;
}
