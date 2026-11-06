// The About card under a lever, and the detail card in the Structure tab, must be readable at every width: its values use the card's width instead of a sliver
// beside the labels (a 90px value column turned a one-line source into a 600px column of text).
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('path');
(async () => {
  const b = await chromium.launch();
  try {
    for (const name of ['bass-b2b-adoption', 'saas-churn-vs-winrate', 'car-dealership-profit']) {
      for (const width of [390, 768, 1024, 1280, 1440]) {
        const p = await b.newPage({viewport: {width, height: 900}});
        await p.goto('file://' + path.resolve(__dirname, '../../../projects', name, 'explorer.html'));
        await p.waitForSelector('.tile');
        if (width <= 700) { await p.locator('#tab-levers').click(); }
        const n = await p.locator('.lever button[aria-controls]').count();
        assert.ok(n > 0, name + ': no lever About buttons');
        for (let i = 0; i < n; i++) { await p.locator('.lever button[aria-controls]').nth(i).click(); }
        const bad = await p.evaluate(() => [...document.querySelectorAll('.lever .info-card')].flatMap(card => {
          const cs = getComputedStyle(card), inner = card.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
          const out = [];
          if (card.scrollWidth > card.clientWidth + 1) { out.push('card overflows horizontally'); }
          card.querySelectorAll('dd').forEach(dd => {
            const w = dd.getBoundingClientRect().width;
            if (w < 0.8 * inner) { out.push(Math.round(w) + 'px value in a ' + Math.round(inner) + 'px card: ' + dd.textContent.slice(0, 30)); }
          });
          return out.map(m => (card.closest('.lever').querySelector('label,.name') || {}).textContent + ': ' + m);
        }));
        assert.ok(bad.length === 0, name + ' at ' + width + 'px: ' + bad.length + ' problems, e.g. ' + bad.slice(0, 3).join(' | '));
        // the Structure tab's detail card, for a spread of variables (stocks, flows, constants)
        await p.getByRole('tab', {name: 'Structure'}).click();
        await p.waitForSelector('g.node');
        const nodes = await p.locator('g.node').count();
        const picks = [...new Set([0, 1, 2, 3, 4, 5].map(k => Math.floor(k * (nodes - 1) / 5)))];
        for (const k of picks) {
          await p.locator('g.node').nth(k).dispatchEvent('click');
          await p.waitForTimeout(150);
          const sbad = await p.evaluate(() => [...document.querySelectorAll('.st-side .info-card')].filter(c => c.offsetParent).flatMap(card => {
            const cs = getComputedStyle(card), inner = card.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
            const out = [];
            if (card.scrollWidth > card.clientWidth + 1) { out.push('card overflows horizontally'); }
            card.querySelectorAll('dd').forEach(dd => {
              const w = dd.getBoundingClientRect().width;
              if (w < 0.8 * inner) { out.push(Math.round(w) + 'px value in a ' + Math.round(inner) + 'px card: ' + dd.textContent.slice(0, 30)); }
            });
            return out;
          }));
          assert.ok(sbad.length === 0, name + ' structure detail ' + k + ' at ' + width + 'px: ' + sbad.length + ' problems, e.g. ' + sbad.slice(0, 3).join(' | '));
        }
        await p.close();
      }
    }
  } finally { await b.close(); }
})().catch(e => { console.error(e); process.exit(1); });
