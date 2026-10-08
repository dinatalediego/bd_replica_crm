// Optional isolated SQL runner: npm install --prefix /tmp/econom-test @electric-sql/pglite
// NODE_PATH=/tmp/econom-test/node_modules node tests/integration/run_econometric_pglite.cjs
const { PGlite } = require('@electric-sql/pglite');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
(async () => {
  const db = new PGlite();
  const contracts = ['01_tables', '02_capture', '03_datasets', '04_evaluation'].map(n => `sql/100_econometria/${n}.sql`);
  const files = ['tests/integration/evolucion_comercial_fixture.sql', 'tests/integration/econometric_fixture.sql',
    'sql/99_evolucion_comercial/01_contract.sql', 'sql/97_commercial_forecasting/01_evidence.sql', ...contracts, ...contracts];
  for (const file of files) await db.exec(fs.readFileSync(path.join(root, file), 'utf8'));
  for (const fn of ['refresh_evolucion_comercial()', 'capture_econometric_events()', 'capture_econometric_current()',
    'backfill_econometric_prices()', 'backfill_econometric_stock()', 'build_econometric_datasets(true)']) {
    await db.exec(`BEGIN; SELECT analytics.${fn}; COMMIT;`);
  }
  await db.exec(fs.readFileSync(path.join(root, 'tests/integration/econometric_assertions.sql'), 'utf8'));
  await db.close();
  console.log('PASS: installation, reinstallation, refresh, SQL assertions and mutation guards');
})().catch(e => { console.error(e); process.exitCode = 1; });
