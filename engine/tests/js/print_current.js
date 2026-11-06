"use strict";
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('path');
(async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 800}});
    await page.goto('file://' + path.resolve(__dirname, '../../../projects/saas-churn-vs-winrate/explorer.html'));
    await page.waitForSelector('.tile');
    await page.locator('#view-structure').click();
    await page.locator('.lever input[type=range]').first().focus();
    await page.keyboard.press('End');
    await page.waitForTimeout(100);
    const expected = await page.evaluate(() => {
      const data = JSON.parse(document.getElementById('sd-data').textContent);
      return SDFormat.fmt(SDMetrics.all(SDEngine.run(SDExplorer.params()), data.metrics)[data.decision.metric]);
    });
    await page.locator('#zoom-in').click();
    const diagram = page.locator('#st-canvas svg.sd-diagram');
    const view = await diagram.getAttribute('viewBox');
    await page.evaluate(() => dispatchEvent(new Event('beforeprint')));
    assert.ok((await page.locator('.tile.decision .tile-value').textContent()).startsWith(expected), 'print uses current settings');
    await page.evaluate(() => dispatchEvent(new Event('afterprint')));
    assert.equal(await diagram.getAttribute('viewBox'), view, 'printing preserves pan and zoom');
    assert.equal(await page.locator('#results').getAttribute('hidden'), '', 'printing preserves active view');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
