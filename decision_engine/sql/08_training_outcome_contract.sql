-- Governed supervised-outcome contract for separation_fall_risk.
--
-- A CRM 'caida' that is explicitly documented as a department/unit change is
-- not equivalent to losing the commercial opportunity. It is a transfer event.
-- Treating it as FALL would inject label noise into any supervised model.
--
-- IMPORTANT:
-- * this does NOT rewrite the certified lifecycle in CORE;
-- * CURRENT risk eligibility remains governed by current-state evidence;
-- * transfer evidence is post-outcome and therefore never a live feature;
-- * confirmed transfer falls are excluded from the binary FALL-vs-CONVERTED
--   training target until successor-opportunity lineage is certified.

create or replace view decision_intelligence.v_separation_fall_training_outcome as
select
    h.*,
    coalesce(a.has_confirmed_department_change, false) as has_confirmed_department_transfer,
    case
        when h.target_fall_before_conversion = 1
         and coalesce(a.has_confirmed_department_change, false)
            then 'TRANSFER_UNIT'
        when h.target_fall_before_conversion = 1
            then 'FELL'
        when h.target_fall_before_conversion = 0
            then 'CONVERTED'
        when h.outcome_class = 'CENSORED_OPEN'
            then 'CENSORED_OPEN'
        else coalesce(h.outcome_class, 'UNKNOWN')
    end::text as training_outcome_class,
    case
        when h.target_fall_before_conversion = 1
         and coalesce(a.has_confirmed_department_change, false)
            then null::integer
        else h.target_fall_before_conversion
    end as training_target_fall_before_conversion,
    case
        when h.target_fall_before_conversion is null then false
        when h.target_fall_before_conversion = 1
         and coalesce(a.has_confirmed_department_change, false) then false
        else true
    end as training_label_eligible,
    case
        when h.target_fall_before_conversion = 1
         and coalesce(a.has_confirmed_department_change, false)
            then 'KNOWN_DEPARTMENT_TRANSFER_POST_OUTCOME'
        when h.target_fall_before_conversion is null
            then 'OUTCOME_NOT_YET_OBSERVED_OR_NOT_TEMPORALLY_LABELABLE'
        else null
    end::text as training_label_exclusion_reason,
    'TARGET_ONLY_POST_OUTCOME_GOVERNANCE'::text as transfer_evidence_role,
    false::boolean as transfer_evidence_live_feature_eligible
from decision_intelligence.v_separation_fall_outcome_history h
left join decision_intelligence.v_fall_reason_analysis_corpus a
  on a.codigo_proforma = h.codigo_proforma;

create or replace view decision_intelligence.v_separation_fall_training_outcome_health as
select
    count(*)::bigint as lifecycle_rows,
    count(*) filter (where target_fall_before_conversion is not null)::bigint as original_temporally_labeled_rows,
    count(*) filter (where target_fall_before_conversion = 1)::bigint as original_fall_rows,
    count(*) filter (where target_fall_before_conversion = 0)::bigint as conversion_rows,
    count(*) filter (where training_outcome_class = 'TRANSFER_UNIT')::bigint as known_department_transfer_rows,
    count(*) filter (where training_target_fall_before_conversion = 1)::bigint as trainable_fall_rows,
    count(*) filter (where training_label_eligible)::bigint as trainable_labeled_rows,
    count(*) filter (where not training_label_eligible)::bigint as excluded_or_censored_rows,
    round(
        count(*) filter (where training_target_fall_before_conversion = 1)::numeric
        / nullif(count(*) filter (where training_label_eligible), 0),
        4
    ) as trainable_fall_rate,
    count(*) filter (
        where training_label_eligible
          and training_target_fall_before_conversion is null
    )::bigint as eligible_with_null_target,
    count(*) filter (
        where training_outcome_class = 'TRANSFER_UNIT'
          and training_target_fall_before_conversion is not null
    )::bigint as transfer_rows_leaking_into_binary_target
from decision_intelligence.v_separation_fall_training_outcome;

comment on view decision_intelligence.v_separation_fall_training_outcome is
'Governed historical target: known department transfers are a separate competing event and are excluded from binary fall-vs-conversion training until successor lineage is certified.';

comment on view decision_intelligence.v_separation_fall_training_outcome_health is
'Quality counters for the supervised training label, including transfer-event decontamination.';
