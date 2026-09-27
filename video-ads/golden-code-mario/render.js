// node render.js out.mp4 audio.wav  → renders scene.html at 30fps and muxes audio
const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const { spawn } = require('child_process');
const path = require('path');
const FF = process.env.FFMPEG || 'ffmpeg', FPS = 30, DUR = 30;
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1080, height: 1920 } });
  await p.goto('file://' + path.resolve(__dirname, 'scene.html'));
  await p.evaluate(async () => { await document.fonts.load('96px Lalezar'); await document.fonts.load('60px Tajawal'); await document.fonts.load('90px "Noto Color Emoji"', '📦'); });
  const ff = spawn(FF, ['-y', '-f', 'image2pipe', '-framerate', FPS, '-c:v', 'mjpeg', '-i', '-', '-i', process.argv[3],
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'medium', '-crf', '20', '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', process.argv[2]], { stdio: ['pipe', 'inherit', 'inherit'] });
  for (let f = 0; f < FPS * DUR; f++) {
    const d = await p.evaluate(t => { draw(t); return document.getElementById('c').toDataURL('image/jpeg', 0.92); }, f / FPS);
    if (!ff.stdin.write(Buffer.from(d.split(',')[1], 'base64'))) await new Promise(r => ff.stdin.once('drain', r));
  }
  ff.stdin.end(); await new Promise(r => ff.on('close', r)); await b.close();
})();
