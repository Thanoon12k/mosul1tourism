const { chromium } = require('/opt/node22/lib/node_modules/playwright');const path=require('path'),fs=require('fs');
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:1080,height:1920}});
p.on('pageerror',e=>console.log('ERR',e.message));await p.goto('file://'+path.resolve(__dirname,'scene.html')+'?v='+(process.env.V||'services'));
await p.evaluate(async()=>{await document.fonts.load('96px Lalezar');await document.fonts.load('60px Tajawal')});
for(const t of process.argv.slice(3)){const d=await p.evaluate(t=>{draw(+t);return document.getElementById('c').toDataURL('image/jpeg',.8)},t);fs.writeFileSync(`${process.argv[2]}/f${t}.jpg`,Buffer.from(d.split(',')[1],'base64'))}await b.close()})();
