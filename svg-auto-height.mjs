/**
 * foreignObject SVG 高度：Chrome CDP 实测 + HTML 结构估算回退
 */
import fs from 'fs';
import { spawn } from 'child_process';
import os from 'os';
import path from 'path';
import { fileURLToPath } from 'url';

const CHROME_PATHS = [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Google Chromium.app/Contents/MacOS/Chromium',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
];

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function findChrome() {
  return CHROME_PATHS.find((p) => fs.existsSync(p)) ?? null;
}

/** 从 HTML 字符串统计结构，估算高度（无浏览器时的回退） */
export function estimateHeightFromHtml(html, width = 1320) {
  const n = (re) => (html.match(re) || []).length;
  const cards = n(/class="card"/g);
  const samples = n(/class="sample"/g);
  const sections = n(/class="sec"/g);
  const maps = n(/class="map"/g);
  const tableRows = n(/<tr[\s>]/gi);
  const pres = n(/<pre class="data"/g);
  const flowBlocks = n(/class="flow"/g);
  const dualBlocks = n(/class="dual"/g);
  const insightKey = n(/class="insight-key"/g);
  const listItems = n(/<li>/g);
  const h1 = n(/<h1>/g);

  let h = 48; // body padding
  h += h1 * 72 + 36; // title block
  h += n(/class="legend"/g) * 44;
  h += maps * 580;
  h += insightKey * 160;
  h += flowBlocks * 100;
  h += dualBlocks * 180;
  h += sections * 85;
  h += cards * 330;
  h += samples * 460;
  h += pres * 110;
  h += Math.max(0, tableRows) * 30;
  h += listItems * 20;
  h += 64; // footer

  // 宽表格/长代码块略增
  if (html.length > 80000) h += 400;
  else if (html.length > 40000) h += 200;

  return Math.ceil(h * 1.02);
}

function cdpSend(ws, method, params = {}) {
  const id = Math.floor(Math.random() * 1e9);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`CDP timeout: ${method}`)), 15000);
    const handler = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id === id) {
        clearTimeout(timer);
        ws.removeEventListener('message', handler);
        if (msg.error) reject(new Error(msg.error.message));
        else resolve(msg.result);
      }
    };
    ws.addEventListener('message', handler);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

/** 用本机 Chrome headless + CDP 测量渲染高度 */
export async function measureHtmlHeight(html, width = 1320) {
  const chrome = findChrome();
  if (!chrome) return null;

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'svg-measure-'));
  const tmpHtml = path.join(tmpDir, 'page.html');
  const fullPage = `<!DOCTYPE html><html><head><meta charset="utf-8"><style>html,body{margin:0;padding:0;}</style></head><body>${html}</body></html>`;
  fs.writeFileSync(tmpHtml, fullPage, 'utf8');

  const port = 9300 + Math.floor(Math.random() * 700);
  const fileUrl = `file://${tmpHtml}`;

  const proc = spawn(
    chrome,
    [
      '--headless=new',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-dev-shm-usage',
      `--remote-debugging-port=${port}`,
      'about:blank',
    ],
    { stdio: 'ignore' },
  );

  try {
    let targets = null;
    for (let i = 0; i < 30; i++) {
      try {
        const res = await fetch(`http://127.0.0.1:${port}/json/version`);
        if (res.ok) {
          targets = await fetch(`http://127.0.0.1:${port}/json`).then((r) => r.json());
          break;
        }
      } catch {
        /* retry */
      }
      await sleep(100);
    }
    if (!targets?.length) return null;

    const pageTarget = targets.find((t) => t.type === 'page') ?? targets[0];
    const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.addEventListener('open', resolve, { once: true });
      ws.addEventListener('error', reject, { once: true });
    });

    await cdpSend(ws, 'Page.enable');
    await cdpSend(ws, 'Emulation.setDeviceMetricsOverride', {
      width,
      height: 800,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await cdpSend(ws, 'Page.navigate', { url: fileUrl });
    await sleep(html.length > 30000 ? 900 : 450);
    await cdpSend(ws, 'Runtime.evaluate', {
      expression: 'document.fonts ? document.fonts.ready : Promise.resolve()',
      awaitPromise: true,
    }).catch(() => {});

    const { result } = await cdpSend(ws, 'Runtime.evaluate', {
      expression: `Math.ceil(Math.max(
        document.body.scrollHeight,
        document.documentElement.scrollHeight,
        document.body.offsetHeight,
        document.documentElement.offsetHeight
      ))`,
      returnByValue: true,
    });

    ws.close();
    const measured = Number(result?.value);
    if (!Number.isFinite(measured) || measured < 100) return null;
    return measured + 24; // 底部缓冲
  } catch (err) {
    if (process.env.SVG_MEASURE_DEBUG) console.error('[svg-auto-height]', err);
    return null;
  } finally {
    proc.kill('SIGTERM');
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
}

/** 优先 CDP 实测，失败则 HTML 估算 */
export async function resolveSvgHeight(html, width = 1320) {
  const measured = await measureHtmlHeight(html, width);
  if (measured) return measured;
  return estimateHeightFromHtml(html, width);
}

export function wrapForeignObjectSvg({ css, body, width, height }) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <foreignObject x="0" y="0" width="${width}" height="${height}">
    <div xmlns="http://www.w3.org/1999/xhtml">
      <style>${css}</style>
      ${body}
    </div>
  </foreignObject>
</svg>`;
}

export function fixSvgXml(svg) {
  return svg
    .replace(/&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[\da-fA-F]+;)/g, '&amp;')
    .replace(/<br(?!\s*\/>)(?=\s*>)/gi, '<br/')
    .replace(/<br\s*\/?>/gi, '<br/>');
}

/** 构建完整 SVG：自动测高 + XML 修复，加 50% 缓冲避免 foreignObject 截断 */
export async function buildSvg({ css, body, width = 1320 }) {
  const innerHtml = `<style>${css}</style>${body}`;
  const measuredHeight = await resolveSvgHeight(innerHtml, width);
  const height = Math.ceil(measuredHeight * 1.5); // 50% buffer: CSS gradients, shadows, Chinese font rendering
  let svg = wrapForeignObjectSvg({ css, body, width, height });
  svg = fixSvgXml(svg);
  return { svg, height };
}

// CLI: echo "$html" | node svg-auto-height.mjs [--estimate] [--width=1320]
const isCli = process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));
if (isCli) {
  const args = process.argv.slice(2);
  const estimateOnly = args.includes('--estimate');
  const widthArg = args.find((a) => a.startsWith('--width='));
  const width = widthArg ? Number(widthArg.split('=')[1]) : 1320;
  const html = fs.readFileSync(0, 'utf8');
  const height = estimateOnly
    ? estimateHeightFromHtml(html, width)
    : await resolveSvgHeight(html, width);
  console.log(height);
}
