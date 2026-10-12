// Screenshot Lesson Studio (desktop + phone). Usage: node screenshot.cjs OUT_DIR [open-first-lesson]
const fs = require('fs');
const {openBrowser} = require('/home/nitin/remotion/renderer/node_modules/@remotion/renderer');
const out = process.argv[2];
const openFirst = process.argv[3] === 'open';
const openSettings = process.argv[3] === 'settings';
const lessonId = /^[0-9a-f]{32}$/.test(process.argv[3] || '') ? process.argv[3] : null;
(async () => {
  const browser = await openBrowser('chrome', {browserExecutable: '/usr/bin/google-chrome', chromeMode: 'chrome-for-testing', logLevel: 'error'});
  try {
    for (const [name, width, height] of [['desktop', 1440, 1000], ['phone', 400, 860]]) {
      const page = await browser.newPage({context: null, logLevel: 'error', indent: false, pageIndex: 0, onBrowserLog: null, onLog: () => {}});
      await page.setViewport({width, height: openSettings ? 1700 : height, deviceScaleFactor: 1});
      await page.goto({url: 'http://127.0.0.1:18610/' + (lessonId ? '#' + lessonId : ''), timeout: 20000});
      const token = fs.readFileSync('/home/nitin/manim/scivid-data/api-token', 'utf8').trim();
      await page.evaluate(async (value) => {
        await new Promise((r) => setTimeout(r, 800));
        if (!document.querySelector('#signin').hidden) {
          document.querySelector('#access-key').value = value;
          document.querySelector('#signin-form').requestSubmit();
        }
        await new Promise((r) => setTimeout(r, 2500));
      }, token);
      if (openSettings) {
        await page.evaluate(async () => {
          document.querySelector('#open-settings').click();
          await new Promise((r) => setTimeout(r, 1500));
          document.querySelector('#add-connection').click();
          document.querySelector('#c-type').value = 'anthropic';
          document.querySelector('#c-type').dispatchEvent(new Event('change'));
          document.querySelector('#settings').scrollTop = 0;
          await new Promise((r) => setTimeout(r, 500));
        });
      }
      if (openFirst) {
        await page.evaluate(async () => {
          document.querySelector('.card')?.click();
          await new Promise((r) => setTimeout(r, 2500));
        });
      }
      const errors = await page.evaluate(() => [...document.querySelectorAll('.error:not([hidden])')].map((e) => e.textContent));
      const shot = await page._client().send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
      fs.writeFileSync(`${out}/${name}${openFirst ? '-detail' : ''}${lessonId ? '-lesson' : ''}${openSettings ? '-settings' : ''}.png`, Buffer.from((shot.value || shot).data, 'base64'));
      console.log(name, 'errors:', JSON.stringify(errors));
      await page.close();
    }
  } finally {
    await browser.close({silent: true});
  }
})().catch((e) => { console.error(e); process.exit(1); });
