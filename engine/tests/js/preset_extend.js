// A preset may set a lever outside its validated range (e.g. "no programme" puts the budget at 0). The page then labels
// every result "outside validated range", so the banner that explains those labels must be shown and the slider must be
// able to hold the value the run uses - exactly what Load does for a saved scenario.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('path');

(async () => {
  const b = await chromium.launch();
  try {
    let tested = 0;
    for (const name of ['bass-b2b-adoption', 'saas-churn-vs-winrate', 'car-dealership-profit']) {
      const page = await b.newPage({viewport: {width: 1280, height: 800}});
      const url = 'file://' + path.resolve(__dirname, '../../../projects', name, 'explorer.html');
      await page.goto(url);
      await page.waitForSelector('.tile');
      const D = await page.evaluate(() => JSON.parse(document.getElementById('sd-data').textContent));
      const out = (p) => D.levers.filter((l) => p.params[l.name] < l.low || p.params[l.name] > l.high);
      for (let i = 0; i < D.presets.length; i++) {
        const p = D.presets[i], levers = out(p);
        if (!levers.length) { continue; }
        tested++;
        await page.goto(url);                                   // a fresh page: extended ranges start off
        await page.waitForSelector('.tile');
        assert.equal(await page.locator('#extend').isChecked(), false, name + ': extended ranges must start off');
        await page.locator('#preset-list button').nth(i).click();
        await page.waitForTimeout(80);
        const where = name + ' preset "' + p.name + '"';
        assert.equal(await page.locator('#extend').isChecked(), true, where + ' is outside a validated range: it must turn extended ranges on');
        assert.equal(await page.locator('#banner').isHidden(), false, where + ': the banner must explain the "outside validated range" labels');
        const used = await page.evaluate(() => SDExplorer.params());
        for (const l of levers) {
          assert.equal(used[l.name], p.params[l.name], where + ': the run must use the preset value for ' + l.name);
          if (l.fixed) { continue; }
          const slider = page.locator('#lv-' + D.levers.indexOf(l));     // app.js ids a lever's slider by its index
          const shown = Number(await slider.inputValue());
          assert.equal(shown, p.params[l.name], where + ': the ' + l.name + ' slider shows ' + shown
            + ' while the run uses ' + p.params[l.name] + ' (the slider range must widen to hold it)');
        }
      }
      await page.close();
    }
    assert.ok(tested > 0, 'no shipped preset sets a lever outside its validated range: this regression is untested');
  } finally { await b.close(); }
})().catch((e) => { console.error(e); process.exit(1); });
