// A lever box must read "0,14" the way a decimal-comma locale means it (0.14), and still read "1,000" as one thousand.
// Before: every comma was stripped as a thousands separator, so a German user typing 0,14 got 14 (then clamped to the maximum).
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('path');
(async () => {
  const b = await chromium.launch();
  try {
    const p = await b.newPage({viewport: {width: 1280, height: 900}, locale: 'de-DE'});
    await p.goto('file://' + path.resolve(__dirname, '../../../projects/bass-b2b-adoption/explorer.html'));
    await p.waitForSelector('.tile');
    await p.locator('#extend').check();                                   // no clamping: the typed value shows exactly
    const box = p.locator('#levers .num input').first();
    // The box shows the value to 6 significant digits (fmtLever), so the expected text is the typed value rounded the same way.
    const six = (n) => String(Number(Number(n).toPrecision(6)));
    const cases = [['0,1', 0.1], ['0,14', 0.14], ['0.14', 0.14], ['1,5', 1.5], ['0,125', 0.125], ['1,000', 1000], ['1,234', 1234],
                   ['12,345', 12345], ['1,234,567', 1234567], ['1,00,000', 100000], ['1,234.5', 1234.5], ['2.5e2', 250]];
    for (const [typed, value] of cases) {
      await box.fill(typed); await box.press('Enter'); await box.blur();
      const shown = six(value);
      assert.equal(await box.inputValue(), shown, 'typed ' + JSON.stringify(typed) + ' gave ' + JSON.stringify(await box.inputValue()) + ', expected ' + shown);
    }
    for (const junk of ['1,2,3', '1.000,5', 'abc', '1,', ',5x']) {        // not a number: refused, the previous value stays
      await box.fill('0.14'); await box.press('Enter'); await box.blur();
      await box.fill(junk); await box.press('Enter'); await box.blur();
      assert.equal(await box.inputValue(), '0.14', 'typed ' + JSON.stringify(junk) + ' changed the value to ' + await box.inputValue());
    }
  } finally { await b.close(); }
})().catch((e) => { console.error(e); process.exit(1); });
