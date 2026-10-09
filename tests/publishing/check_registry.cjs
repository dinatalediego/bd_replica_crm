// NODE_PATH=/tmp/atlas-sql-test/node_modules node tests/publishing/check_registry.cjs
const {PGlite}=require('@electric-sql/pglite');
const fs=require('node:fs');
(async()=>{
 const db=new PGlite();
 const ddl=fs.readFileSync('sql/101_publishing/01_registry.sql','utf8');
 await db.exec(ddl);await db.exec(ddl);
 const payload={data:{indicators:[{id:'test',value:1}]},model:{metrics:[{}],results:[{}]},scenario:{scenarios:[{}]},story:{findings:[{}],decisions:[{id:"test-decision"}],wisdom_cards:[{}]}};
 const insert=`INSERT INTO publish.product_release(archive_sha256,product_id,product_version,classification,manifest,payload) VALUES($1,'demo','1.0.0','SYNTHETIC',$2,$3) ON CONFLICT(archive_sha256) DO NOTHING`;
 const args=['a'.repeat(64),JSON.stringify({classification:'SYNTHETIC'}),JSON.stringify(payload)];
 await db.query(insert,args);await db.query(insert,args);
 const n=await db.query('SELECT count(*)::int n FROM publish.product_release');if(n.rows[0].n!==1)throw Error('not idempotent');
 for(const view of ['data_product','model_run','indicator','model_metric','model_prediction','scenario','finding','numeric_story','decision_insight','wisdom_card']){
  const r=await db.query(`SELECT count(*)::int n FROM publish.${view}`);if(r.rows[0].n!==1)throw Error('bad view '+view);
 }
 for(const mutation of ["UPDATE publish.product_release SET product_id='mutated'",'DELETE FROM publish.product_release','TRUNCATE publish.product_release']){
  let rejected=false;try{await db.exec(mutation)}catch(e){rejected=true}if(!rejected)throw Error('mutation accepted');
 }
 const ev=`INSERT INTO publish.decision_event(event_sha256,archive_sha256,decision_id,event_type,occurred_at,payload) VALUES($1,$2,$3,'OUTCOME_OBSERVED','2026-10-09T18:00:00Z','{}')`;
 await db.query(ev,['b'.repeat(64),'a'.repeat(64),'test-decision']);
 let failed=false;try{await db.query(ev,['c'.repeat(64),'a'.repeat(64),'missing'])}catch(e){failed=true}if(!failed)throw Error('dangling decision');
 for(const sql of ['UPDATE publish.decision_event SET decision_id=decision_id','DELETE FROM publish.decision_event','TRUNCATE publish.decision_event']){let blocked=false;try{await db.exec(sql)}catch(e){blocked=true}if(!blocked)throw Error('feedback mutated')}
 const learning=await db.query('SELECT * FROM publish.decision_learning');if(learning.rows.length!==1||learning.rows[0].event_type!=='OUTCOME_OBSERVED')throw Error('missing learning');
 await db.close();console.log('PASS: install twice, idempotent register, 10 views, immutable releases, feedback references and learning view');
})().catch(e=>{console.error(e);process.exitCode=1});
