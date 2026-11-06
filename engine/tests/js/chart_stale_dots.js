// Regression: after a scenario is saved while chart groups are collapsed, the collapsed charts keep their old crosshair dots but
// get the new series; moving the Structure tab's time slider then threw "Cannot read properties of undefined (reading
// 'setAttribute')" in LineChart.showCross and stopped the crosshair sync. No uncaught error may occur in any of these flows.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('path');
(async () => {
  const b = await chromium.launch();
  try {
    for (const name of ['bass-b2b-adoption', 'saas-churn-vs-winrate', 'car-dealership-profit']) {
      const p = await b.newPage({viewport: {width: 1280, height: 900}});
      const errors = [];
      p.on('pageerror', (e) => errors.push(e.message));
      await p.goto('file://' + path.resolve(__dirname, '../../../projects', name, 'explorer.html'));
      await p.waitForSelector('.tile');
      const scrub = async () => {
        await p.locator('#view-structure').click();
        await p.locator('#st-time').focus();
        await p.keyboard.press('End');
        await p.keyboard.press('Home');
        await p.locator('#view-results').click();
      };
      const flows = [
        ['initial', async () => {}],
        ['a saved scenario', async () => { await p.locator('#save-scenario').click(); await p.waitForTimeout(200); }],
        ['the scenario removed', async () => {
          assert.equal(await p.locator('#saved li').count(), 1, name + ': one scenario should be saved before it is removed');
          await p.locator('#saved button[aria-label^="Remove scenario"]').first().click(); await p.waitForTimeout(200);
          assert.equal(await p.locator('#saved li').count(), 0, name + ': the scenario was not removed');
        }],
        ['two scenarios and a preset', async () => {
          await p.locator('#save-scenario').click(); await p.locator('#save-scenario').click();
          await p.locator('#preset-list button').nth(1).click(); await p.waitForTimeout(200);
          assert.equal(await p.locator('#saved li').count(), 2, name + ': two scenarios should be saved');
        }],
      ];
      for (const [label, step] of flows) {
        await step();
        await scrub();
        // hover an open chart too: the crosshair is synchronised across every chart, drawn or not
        const box = await p.evaluate(() => {
          const s = [...document.querySelectorAll('#charts .chart svg.plot')].find((x) => x.getBoundingClientRect().width > 0);
          if (!s) { return null; }
          s.scrollIntoView({block: 'center'});
          const r = s.getBoundingClientRect();
          return {x: r.x, y: r.y, width: r.width, height: r.height};
        });
        assert.ok(box, name + ' after ' + label + ': no visible chart plot to hover');
        await p.mouse.move(box.x + box.width * 0.4, box.y + box.height / 2); await p.mouse.move(box.x + box.width * 0.6, box.y + box.height / 2);
        await p.waitForTimeout(150);
        const shown = await p.evaluate((pt) => {
          const s = document.elementFromPoint(pt.x, pt.y);
          const plot = s && s.closest ? s.closest('svg.plot') : null;
          const cross = plot && plot.querySelector('.cross');
          return !!cross && cross.getAttribute('visibility') === 'visible';
        }, {x: box.x + box.width * 0.6, y: box.y + box.height / 2});
        assert.ok(shown, name + ' after ' + label + ': hovering a chart did not show its crosshair');
        assert.deepEqual(errors, [], name + ': uncaught error after ' + label + ': ' + errors[0]);
      }
      await p.close();
    }
  } finally { await b.close(); }
})().catch((e) => { console.error(e); process.exit(1); });
