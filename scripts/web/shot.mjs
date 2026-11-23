// Headless check of the walkthrough over the Chrome DevTools protocol (Node 22, no dependencies).
//   node scripts/web/shot.mjs <url> <out.png> [walkSeconds]      (Chrome: $CHROME or the macOS default path)
// Waits for window.__ready, prints console errors, optionally holds W for walkSeconds and prints the HUD position
// before and after (a collision / walking check without looking at pictures), then saves a screenshot.
import { spawn } from 'node:child_process';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [url, out, walk = '0'] = process.argv.slice(2);
const PORT = 9333;
const chrome = spawn(process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, '--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist',
  '--window-size=1600,900', `--user-data-dir=${mkdtempSync(join(tmpdir(), 'wt-'))}`, 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let targets;
for (let i = 0; i < 50; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); if (targets.length) break; } catch { /* starting */ }
  await sleep(200);
}
const page = targets.find((t) => t.type === 'page');
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r));
let id = 0; const pending = new Map();
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type))
    console.log('console.' + m.params.type + ':', m.params.args.map((a) => a.value ?? a.description).join(' ').slice(0, 300));
  if (m.method === 'Runtime.exceptionThrown') console.log('exception:', m.params.exceptionDetails.exception?.description?.slice(0, 400));
});
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const evalJs = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true })).result?.result?.value;
await send('Runtime.enable');
await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: 1600, height: 900, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url });
let ready = false;
for (let i = 0; i < 300 && !ready; i++) { await sleep(200); ready = await evalJs('window.__ready === true'); }
console.log('ready:', ready, '| status:', await evalJs("document.getElementById('status')?.textContent || 'loaded'"));
await sleep(1500);                      // let the exposure settle
if (Number(walk) > 0) {
  console.log('before:', await evalJs("document.getElementById('pos').textContent"));
  await send('Input.dispatchKeyEvent', { type: 'keyDown', code: 'KeyW', key: 'w', windowsVirtualKeyCode: 87 });
  await sleep(Number(walk) * 1000);
  await send('Input.dispatchKeyEvent', { type: 'keyUp', code: 'KeyW', key: 'w', windowsVirtualKeyCode: 87 });
  await sleep(300);
  console.log('after: ', await evalJs("document.getElementById('pos').textContent"));
}
const shot = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(out, Buffer.from(shot.result.data, 'base64'));
console.log('saved', out);
ws.close();
chrome.kill();
process.exit(0);
