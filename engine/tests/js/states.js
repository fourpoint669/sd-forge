const{chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch();try{const p=await b.newPage({viewport:{width:1280,height:800}});await p.goto('file://'+require('path').resolve(__dirname,'../../../projects/bass-b2b-adoption/explorer.html'));await p.waitForSelector('.tile');assert.equal(await p.locator('#comparison-details').count(),1);assert.equal(await p.locator('#comparison-details').getAttribute('open'),null);await p.locator('#save-scenario').click();assert.notEqual(await p.locator('#comparison-details').getAttribute('open'),null);const text=await p.evaluate(()=>{const root=document.createElement('div');document.body.append(root);const c=new SDCharts.LineChart(root,{id:'empty-probe',title:'Empty probe'});c.update({title:'Empty probe',time:[],series:[],bands:[]});return root.querySelector('.chart-status').textContent});assert.match(text,/No finite data/);
const hidden = await p.evaluate(() => {
  const disclosure = document.createElement('details');
  const summary = document.createElement('summary'); summary.textContent = 'Deferred chart probe';
  const root = document.createElement('div'); disclosure.append(summary, root); document.body.append(disclosure);
  const chart = new SDCharts.LineChart(root, {id: 'deferred-probe', title: 'Deferred probe'});
  const opts = {title: 'Deferred probe', time: [0, 1, 2], timeUnit: 'Time', fmt: String, fmtAxis: String,
    series: [{label: 'Probe', color: 'var(--series-current)', values: [0, 1, 2]}], bands: []};
  chart.update(opts);
  const before = root.querySelector('path').getAttribute('d');
  chart.update(Object.assign({}, opts, {series: [{label: 'Probe', color: 'var(--series-current)', values: [0, 2, 1]}]}));
  const deferred = root.querySelector('path').getAttribute('d') === before;
  disclosure.open = true;
  return deferred;
});
assert.equal(hidden, true, 'closed chart defers its SVG update');
await p.waitForFunction(() => {
  const path = document.querySelector('#deferred-probe-title').closest('.card-head').parentElement.querySelector('path');
  const points = path.getAttribute('d').match(/[-\d.]+/g).map(Number);
  return points[3] < points[5];
});}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)})
