// usage: node render.js preview <outdir> f1 f2 ...   |  node render.js video <out.mp4-video-only>
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs'), path = require('path');
(async () => {
  const mode = process.argv[2];
  const b = await chromium.launch({ args: ['--allow-file-access-from-files'] });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  p.on('console', m => console.log('[page]', m.text())); p.on('pageerror', e => console.log('[err]', e.message));
  await p.goto('file://' + path.resolve(__dirname, 'index.html') + '#render');
  await p.evaluate(() => window.ready);
  const grab = async i => { const d = await p.evaluate(i => { renderFrame(i); return document.getElementById('c').toDataURL('image/png'); }, i); return Buffer.from(d.split(',')[1], 'base64'); };
  if (mode === 'preview') {
    const dir = process.argv[3]; fs.mkdirSync(dir, { recursive: true });
    for (const f of process.argv.slice(4)) fs.writeFileSync(path.join(dir, `f${String(f).padStart(3, '0')}.png`), await grab(+f));
  } else {
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', '24', '-i', '-', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', process.argv[3]], { stdio: ['pipe', 'inherit', 'inherit'] });
    const t0 = Date.now();
    for (let i = 0; i < 720; i++) { const buf = await grab(i); if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r)); if (i % 40 === 0) console.log('frame', i, ((Date.now() - t0) / 1000).toFixed(1) + 's'); }
    ff.stdin.end(); await new Promise(r => ff.on('close', r));
  }
  await b.close();
})();
