// WCAG 1.4.10 reflow: at a 320 CSS px wide viewport the page must not scroll horizontally. Found by the exerciser: once four
// scenarios were saved, the (nowrap) button label "Four scenarios saved (remove one to save another)" pushed the page 15px wide.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('path');
(async () => {
  const b = await chromium.launch();
  try {
    for (const name of ['bass-b2b-adoption', 'saas-churn-vs-winrate', 'car-dealership-profit']) {
      const p = await b.newPage({viewport: {width: 320, height: 800}});
      await p.goto('file://' + path.resolve(__dirname, '../../../projects', name, 'explorer.html'));
      await p.waitForSelector('.tile');
      const width = () => p.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
      let [scroll, client] = await width();
      assert.ok(scroll <= client, name + ': page is wider than 320px at rest (' + scroll + ' > ' + client + ')');
      for (let i = 0; i < 4; i++) { await p.locator('#save-scenario').click(); }
      if (!(await p.evaluate(() => document.getElementById('comparison-details').open))) { await p.locator('#comparison-details > summary').click(); }
      await p.waitForTimeout(300);
      assert.equal(await p.locator('#saved li').count(), 4, name + ': four scenarios should be saved');
      assert.equal(await p.evaluate(() => document.getElementById('comparison-details').open), true, name + ': the comparison table should be open');
      assert.match((await p.locator('#save-scenario').textContent()).trim(), /^Four scenarios saved/, name + ': the long button label is the state under test');
      [scroll, client] = await width();
      assert.ok(scroll <= client, name + ': page is wider than 320px with four saved scenarios (' + scroll + ' > ' + client + ')');
      await p.close();
    }
  } finally { await b.close(); }
})().catch((e) => { console.error(e); process.exit(1); });
