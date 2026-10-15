const { PGlite } = require('@electric-sql/pglite');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');

function read(relative) {
  return fs.readFileSync(path.join(root, relative), 'utf8');
}

function extractSqlConstant(name) {
  const source = read('scripts/refresh_marketing_audiences.py');
  const pattern = new RegExp(`${name} = r"""([\\s\\S]*?)"""`);
  const match = source.match(pattern);
  if (!match) throw new Error(`No se pudo extraer ${name}`);
  return match[1];
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

  const buildAudience = extractSqlConstant('BUILD_NEXT_SQL')
    .replaceAll('%(inactivity_days)s', '180');

  const buildProjects = extractSqlConstant('BUILD_PROJECTS_NEXT_SQL');
  const loadAudience = extractSqlConstant('LOAD_AUDIENCES_SQL');
  const loadProjects = extractSqlConstant('LOAD_PROJECTS_SQL');

  await db.exec(buildAudience);
  await db.exec(buildProjects);
  await db.exec('DELETE FROM analytics.marketing_audiencias;');
  await db.exec(loadAudience);
  await db.exec(loadProjects);

  const result = await db.query(`
    SELECT
      personas,
      positivas,
      negativas_sin_avance,
      exclusiones,
      contacto_valido,
      aptas_entrega_externa,
      con_proyecto_origen,
      con_proyecto_conversion,
      cambios_proyecto,
      project_links
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
    con_proyecto_origen: 6n,
    con_proyecto_conversion: 2n,
    cambios_proyecto: 1n,
    project_links: 7n,
  };

  for (const [key, value] of Object.entries(expected)) {
    if (BigInt(actual[key]) !== value) {
      throw new Error(`${key}: esperado ${value}, obtenido ${actual[key]}`);
    }
  }

  const positive = await db.query(
    'SELECT count(*) AS n FROM analytics.v_marketing_positiva'
  );

  const negative = await db.query(
    'SELECT count(*) AS n FROM analytics.v_marketing_negativa_sin_avance'
  );

  if (
    BigInt(positive.rows[0].n) !== 2n
    || BigInt(negative.rows[0].n) !== 1n
  ) {
    throw new Error(
      'Las vistas internas no respetaron contacto válido/supresión'
    );
  }

  const lineage = await db.query(`
    SELECT
      proyecto_origen,
      proyecto_conversion,
      cambio_proyecto
    FROM analytics.marketing_audiencias
    WHERE persona_key = 'doc:33333333'
  `);

  const row = lineage.rows[0];

  if (
    row.proyecto_origen !== 'Sialia'
    || row.proyecto_conversion !== 'Urbanzen'
    || row.cambio_proyecto !== true
  ) {
    throw new Error(
      `Linaje inesperado para Carla: ${JSON.stringify(row)}`
    );
  }

  console.log('marketing_audiences integration: PASS');
  await db.close();

})().catch((error) => {
  console.error(error);
  process.exit(1);
});
