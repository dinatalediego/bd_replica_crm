const { PGlite } = require('@electric-sql/pglite');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');

function read(relative) {
  return fs.readFileSync(path.join(root, relative), 'utf8');
}

function refreshSql() {
  const source = read('scripts/refresh_marketing_audiences.py');
  const match = source.match(/REFRESH_SQL = r"""([\s\S]*?)"""/);
  if (!match) throw new Error('No se pudo extraer REFRESH_SQL');
  return match[1].replaceAll('%(inactivity_days)s', '180');
}

(async () => {
  const db = new PGlite();
  await db.exec(read('tests/integration/marketing_audiences_fixture.sql'));
  await db.exec(read('sql/115_marketing_audiences/01_contract.sql'));
  await db.exec(`
    INSERT INTO analytics.marketing_consentimientos
      (persona_key, permitido, fuente_verificacion, verificado_en)
    VALUES ('doc:11111111', true, 'fixture', now());
    INSERT INTO analytics.marketing_supresiones (persona_key, motivo)
    VALUES ('doc:22222222', 'fixture no contactar');
  `);
  await db.exec(refreshSql());

  const result = await db.query(`
    SELECT personas, positivas, negativas_sin_avance, exclusiones,
           contacto_valido, aptas_entrega_externa
    FROM analytics.v_marketing_audiencias_health
  `);
  const actual = result.rows[0];
  const expected = {
    personas: 6n,
    positivas: 3n,
    negativas_sin_avance: 2n,
    exclusiones: 3n,
    contacto_valido: 5n,
    aptas_entrega_externa: 1n,
  };
  for (const [key, value] of Object.entries(expected)) {
    if (BigInt(actual[key]) !== value) {
      throw new Error(`${key}: esperado ${value}, obtenido ${actual[key]}`);
    }
  }
  const positive = await db.query('SELECT count(*) AS n FROM analytics.v_marketing_positiva');
  const negative = await db.query('SELECT count(*) AS n FROM analytics.v_marketing_negativa_sin_avance');
  if (BigInt(positive.rows[0].n) !== 2n || BigInt(negative.rows[0].n) !== 1n) {
    throw new Error('Las vistas exportables no respetaron supresión/segmentación');
  }
  console.log('marketing_audiences integration: PASS');
  await db.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
