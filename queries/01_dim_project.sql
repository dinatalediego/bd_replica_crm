SELECT DISTINCT
    project_key,
    project_name
FROM analytics.v_pbi_ai_control_tower_v293
WHERE project_key IS NOT NULL
ORDER BY project_key;
