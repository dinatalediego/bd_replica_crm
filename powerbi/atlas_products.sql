-- Local/private consumer. Replace the SHA placeholder with ONE registered release.
-- This does not replace existing Power BI contracts.
SELECT r.archive_sha256,r.classification,
       i.indicator->>'id' AS indicator_id,
       i.indicator->>'name' AS indicator_name,
       (i.indicator->>'value')::numeric AS value,
       i.indicator->>'unit' AS unit,
       (i.indicator->>'period')::date AS period,
       r.payload->'data'->'provenance'->>'semantics' AS source_semantics
FROM publish.product_release r
JOIN publish.indicator i USING(archive_sha256)
WHERE r.archive_sha256 = 'REPLACE_WITH_ONE_RELEASE_SHA256';
