// Replay the actual read-only workbench entry and its updated-packet control.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const { chromium } = require('playwright-core');
const out = path.join(root, 'ledger/browser');
fs.mkdirSync(out, { recursive: true });
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const inputs = ['workbench/index.html','workbench/engine.js','workbench/stats.js',
  'workbench/chain-engine.js','workbench/chain.js','workbench/result.js','workbench/result.json',
  'patient_workbench_result.json'].map(p => ({ path: p, sha256: hash(path.join(root,p)) }));
const browser = await chromium.launch({
  ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : { channel: 'chrome' }), headless: true,
  args: ['--js-flags=--max-old-space-size=256'],
});
const errors = [], receipts = [];
const started = performance.now();
try {
  const context = await browser.newContext({ acceptDownloads: true });
  await context.route(/^https?:/, route => route.abort());
  const page = await context.newPage();
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(pathToFileURL(path.join(root, 'workbench/index.html')).href);
  if (process.argv.includes('--probe')) {
    const result = { browser: browser.version(), node: process.version, title: await page.title(),
      elapsed_ms: performance.now()-started, errors, max_rss_node_kib: process.resourceUsage().maxRSS };
    fs.writeFileSync(path.join(out,'probe.json'),JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify(result));
  } else {
    for (const name of ['built_in_two_readout','updated_combined_regimen']) {
      if (name === 'built_in_two_readout') {
        await page.click('#example');
      } else {
        await page.setInputFiles('#packet-file',path.join(root,'patient_workbench_result.json'));
        await page.waitForFunction(() => document.querySelector('#rule-note').textContent.includes('0.31875'));
      }
      await page.click('#reveal');
      const visible = await page.evaluate(() => ({
        comparison: document.querySelector('#comparison').innerText,
        failure: document.querySelector('#failure').innerText,
        patient_rows: document.querySelectorAll('#patients tr').length,
        wrong_reported_rows: document.querySelectorAll('#patients tr[data-result="bad"]').length,
        visible_error: document.querySelector('#error').hidden ? null : document.querySelector('#error').textContent,
      }));
      const [csv] = await Promise.all([page.waitForEvent('download'),page.click('#download')]);
      await csv.saveAs(path.join(out,name+'.csv'));
      const [analysis] = await Promise.all([page.waitForEvent('download'),page.click('#export')]);
      await analysis.saveAs(path.join(out,name+'.json'));
      receipts.push({name,...visible,csv_sha256:hash(path.join(out,name+'.csv')),
        analysis_sha256:hash(path.join(out,name+'.json'))});
    }
    if (errors.length || receipts.some(r => r.visible_error)) throw Error(JSON.stringify({errors,receipts}));
    if (receipts[0].patient_rows!==43 || receipts[0].wrong_reported_rows!==4 ||
        receipts[1].patient_rows!==43 || receipts[1].wrong_reported_rows!==1) throw Error('Unexpected patient counts');
    const result={browser:browser.version(),node:process.version,playwright:require('playwright-core/package.json').version,
      entry:'workbench/index.html',inputs,receipts,errors,elapsed_ms:performance.now()-started,
      max_rss_node_kib:process.resourceUsage().maxRSS,mode:'headless; file entry; local downloads; HTTP requests blocked'};
    fs.writeFileSync(path.join(out,'receipt.json'),JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify(result,null,2));
  }
  await context.close();
} finally {
  await browser.close();
}
