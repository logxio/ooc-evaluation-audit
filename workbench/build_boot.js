/* Build the browser's small opening packet and independently loadable chemical details.
   The full public data files remain the source of truth. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const dir = path.join(__dirname, 'data');
const root = { window: {} };
for (const name of ['ooc-data.js', 'ooc-final-1009.js']) {
  vm.runInNewContext(fs.readFileSync(path.join(dir, name), 'utf8'), root, { filename: name });
}
const full = root.window.OOC;
const final = root.window.OOC_FINAL_1009;
const first = full.examples[0].chemical;
const boot = JSON.parse(JSON.stringify(full));
delete boot.sources;
const shards = Array.from({ length: 16 }, () => []);

boot.chems.forEach((chemical, i) => {
  const source = full.chems[i];
  const well = full.wells.find(row => row.name === chemical.name);
  if (!well) throw new Error(`Missing wells for ${chemical.name}`);
  shards[i % shards.length].push({
    i,
    d: source.d.map(({ f, ll, w, e }) => ({ f, ll, w, e })),
    y: well.y
  });
  if (chemical.name !== first) chemical.d.forEach(design => {
    for (const key of ['f', 'll', 'w', 'e']) delete design[key];
  });
});
boot.wells.forEach(well => { if (well.name !== first) delete well.y; });

const finalBoot = {
  schema: final.schema,
  screening: {
    closedLoop: final.screening.closedLoop,
    pairedContrasts: {
      model_disagreement__minus__nested_measured_only:
        final.screening.pairedContrasts.model_disagreement__minus__nested_measured_only
    },
    display: final.screening.display
  },
  baselines: {
    stackTotals: final.baselines.stackTotals,
    opponents: Array(final.baselines.opponents.length).fill(null)
  },
  patients: final.patients
};

function write(name, code) {
  const file = path.join(dir, name);
  if (process.argv.includes('--check')) {
    if (fs.readFileSync(file, 'utf8') !== code) throw new Error(`${name} needs rebuilding`);
  } else fs.writeFileSync(file, code);
}
write('ooc-boot.js', `window.OOC = ${JSON.stringify(boot)};\n`);
write('ooc-final-boot.js', `window.OOC_FINAL_1009 = ${JSON.stringify(finalBoot)};\n`);
shards.forEach((rows, i) => {
  write(`ooc-detail-${String(i).padStart(2, '0')}.js`,
    `window.OOC_DETAIL_SHARDS = window.OOC_DETAIL_SHARDS || {}; window.OOC_DETAIL_SHARDS[${i}] = ${JSON.stringify(rows)};\n`);
});

const runtimeFiles = [
  'vendor/d3.v7.9.0.min.js',
  'data/ooc-boot.js',
  'data/ooc-final-boot.js',
  'assets/mount-final-1009.js',
  'engine.js', 'stats.js', 'chain-engine.js', 'result.js',
  'assets/core.js', 'assets/charts-a.js', 'assets/charts-b.js',
  'assets/charts-c.js', 'assets/copy.js'
];
const runtime = '/* D3 ISC license: vendor/d3.LICENSE.txt. Source files are kept beside this bundle. */\n' +
  runtimeFiles.map(name => fs.readFileSync(path.join(__dirname, name), 'utf8').trimEnd()).join('\n;\n') + '\n';
const runtimeFile = path.join(__dirname, 'runtime.js');
if (process.argv.includes('--check')) {
  if (fs.readFileSync(runtimeFile, 'utf8') !== runtime) throw new Error('runtime.js needs rebuilding');
} else fs.writeFileSync(runtimeFile, runtime);
