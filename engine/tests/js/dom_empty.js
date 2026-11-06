// Loop strength over time must never be a chart with nothing in it. Where no loop carries a score at a time step,
// every relative score there is NaN and a band drawn for it has zero height; with no step scored the whole chart is
// invisible and cannot be told apart from a broken page. Reported from use on car-dealership-profit, whose base case
// leaves "retention loss when overloaded" at 0, freezing a link in every one of its 67 loops.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('path');

const page_of = (name) => 'file://' + path.resolve(__dirname, '../../../projects', name, 'explorer.html');

async function openLoopStrength(p, url) {
  await p.goto(url);
  await p.waitForSelector('.tile');
  await p.locator('#view-structure').click();
  await p.waitForSelector('#structure svg.sd-diagram .node');
  await p.locator('#side-tab-strength').click();
  await p.waitForSelector('#dominance:not([hidden])');
}

// bands that actually enclose some area, i.e. would be visible
const drawn = (p) => p.evaluate(() => [...document.querySelectorAll('#dominance svg.dom-chart path.dom-band')]
  .filter((el) => {
    const ys = [...(el.getAttribute('d') || '').matchAll(/[ML](-?[\d.]+),(-?[\d.]+)/g)].map((m) => parseFloat(m[2]));
    return ys.length > 1 && Math.max(...ys) - Math.min(...ys) > 0.01;
  }).length);

(async () => {
  const b = await chromium.launch();
  try {
    // 1. A model whose base case scores every loop draws a chart and says nothing about emptiness.
    let p = await b.newPage({viewport: {width: 1360, height: 900}});
    await openLoopStrength(p, page_of('saas-churn-vs-winrate'));
    assert.equal(await p.locator('#dominance .dom-empty').count(), 0, 'saas: nothing should be reported empty at base');
    assert.ok(await drawn(p) > 0, 'saas: the loop-strength chart should have visible bands at base');
    await p.close();

    // 2. car-dealership-profit: empty at base, and it says so instead of drawing invisible bands.
    p = await b.newPage({viewport: {width: 1360, height: 900}});
    await openLoopStrength(p, page_of('car-dealership-profit'));
    const note = p.locator('#dominance .dom-empty');
    assert.equal(await note.count(), 1, 'car dealership: the empty loop-strength view should be explained');
    const text = (await note.textContent()).replace(/\s+/g, ' ');
    assert.match(text, /No loop strength to show at these lever settings/, 'the note should say there is nothing to show');
    assert.match(text, /retention loss when overloaded/, 'the note should carry the declared reason');
    assert.equal(await p.locator('#dominance svg.dom-chart').count(), 0,
      'car dealership: no chart should be drawn when every band would have zero height');
    assert.equal(await p.locator('#dominance #dom-method').count(), 1,
      'the method statement must survive the empty case');

    // 3. ... and the chart comes back when the lever that freezes the loops is raised.
    const id = await p.evaluate(() => {
      const D = JSON.parse(document.getElementById('sd-data').textContent);
      const i = D.levers.findIndex((l) => l.name === 'retention loss when overloaded');
      return i >= 0 ? 'lv-' + i : null;
    });
    assert.ok(id, 'the retention lever should be on the page');
    await p.evaluate((lv) => {
      const el = document.getElementById(lv);
      el.value = '0.4';
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
    }, id);
    await p.waitForSelector('#dominance svg.dom-chart', {timeout: 20000});
    assert.equal(await p.locator('#dominance .dom-empty').count(), 0, 'the note should go when there is a chart');
    assert.ok(await drawn(p) > 50, 'raising the lever should draw most of the 67 loops');
    await p.close();
    console.log('ok');
  } finally {
    await b.close();
  }
})().catch((e) => { console.error(e); process.exit(1); });
