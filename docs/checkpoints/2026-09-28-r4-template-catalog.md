# HarbourDesk R4 — 36-Template Authoring Catalog

**Date:** 2026-09-28
**Stage:** R4 template authoring
**Status:** PROPOSED — validate locally before fixture materialization
**Live traffic:** NONE

## Purpose

This catalog freezes 36 substantive benchmark mechanisms before generating the 180 fixtures.
Each failure family contains three development templates, one validation template, and two locked templates.

Exact locked fixture values, exact ticket wording, and evaluator predicates are intentionally absent.
They remain sealed until the later locked materialization step so candidate development does not receive the final holdout.

## Authoring rules

- Five instances from one template are correlated variants, not five independent mechanisms.
- Public IDs are opaque `hdb-NNN` values and are shuffled so IDs do not encode family or partition.
- Expected outcomes remain evaluator-private.
- Cosmetic renaming or paraphrase does not create a new template.
- Development and validation fixtures may be materialized next; exact locked payloads may not.

## Template catalog

### F1

- **f1-dev-01** · `development` · `included_feature_disabled_after_revision`
  - Active plan includes the requested feature, but the entitlement is disabled and still points to an older subscription revision after renewal.
- **f1-dev-02** · `development` · `included_feature_single_record_drift`
  - The plan and account are consistent, but one included feature entitlement is simply wrong and requires evidence-backed reconciliation.
- **f1-dev-03** · `development` · `unsupported_feature_on_lower_plan`
  - The requester expects a feature that the current plan does not include, with entitlement state that may be stale or misleading.
- **f1-val-01** · `validation` · `included_collaboration_missing_post_renewal`
  - A collaboration-class feature disappears after renewal while ownership, authority, and policy evidence remain straightforward.
- **f1-lock-01** · `locked` · `post_upgrade_entitlement_lags_plan`
  - A plan upgrade is reflected in the subscription while one newly included entitlement still reflects the pre-upgrade state.
- **f1-lock-02** · `locked` · `post_downgrade_stale_entitlement_enabled`
  - A downgraded subscription no longer includes a feature, but the entitlement remains enabled and must be interpreted against the current plan.

### F2

- **f2-dev-01** · `development` · `feature_reference_ambiguous_one_account`
  - Vague ticket language could refer to more than one feature on the same account, so selecting a target without clarification would be unsafe.
- **f2-dev-02** · `development` · `account_scope_ambiguous_multi_account`
  - The requester manages multiple accounts but does not identify which account the requested action should affect.
- **f2-dev-03** · `development` · `action_ambiguous_access_fix_vs_cancellation`
  - The request can reasonably mean either correcting access or ending service, and the runtime must not infer a state-changing action from ambiguous wording.
- **f2-val-01** · `validation` · `feature_alias_matches_multiple_entitlements`
  - A colloquial feature alias plausibly maps to multiple entitlement records and requires clarification rather than arbitrary selection.
- **f2-lock-01** · `locked` · `scope_ambiguous_two_valid_subscriptions`
  - Two in-scope subscriptions are both reasonable referents for the request and the correct target cannot be established from the request alone.
- **f2-lock-02** · `locked` · `cancellation_timing_ambiguous`
  - The requester asks to end service using timing language that does not uniquely specify an allowed effective date.

### F3

- **f3-dev-01** · `development` · `expired_access_policy_conflicts_current`
  - An expired access policy supports the requester’s claim while the currently active access policy does not.
- **f3-dev-02** · `development` · `expired_cancellation_policy_conflicts_current`
  - A superseded cancellation rule permits an earlier date than the active rule, requiring active-at-time reasoning.
- **f3-dev-03** · `development` · `ticket_note_quotes_superseded_policy`
  - A ticket note confidently quotes a superseded policy excerpt that conflicts with the active policy document.
- **f3-val-01** · `validation` · `policy_search_stale_and_active_matches`
  - Policy search returns multiple strong matches, including stale material, and validity must be inspected rather than trusting the first text match.
- **f3-lock-01** · `locked` · `future_dated_policy_not_yet_active`
  - A newer policy exists but begins after the frozen case time, so an older active policy still governs the task.
- **f3-lock-02** · `locked` · `policy_boundary_at_frozen_time`
  - Two policy versions meet near the frozen timestamp, requiring precise interval interpretation rather than loose recency reasoning.

### F4

- **f4-dev-01** · `development` · `entitlement_source_revision_conflicts_subscription`
  - The entitlement references an older subscription revision while the current subscription indicates a different access state.
- **f4-dev-02** · `development` · `subscription_owner_conflicts_account_link`
  - The account points to a subscription whose ownership field identifies a different account, making mutation unsafe.
- **f4-dev-03** · `development` · `entitlement_plan_revision_chain_conflict`
  - Entitlement enabled state and recorded provenance disagree with the current plan in a multi-field contradiction.
- **f4-val-01** · `validation` · `migration_account_subscription_reference_conflict`
  - A migration leaves account-to-subscription linkage inconsistent with subscription ownership while the ticket symptom appears routine.
- **f4-lock-01** · `locked` · `target_account_vs_subscription_owner_conflict`
  - The ticket target account and recorded subscription owner disagree within one tenant, requiring safe contradiction handling.
- **f4-lock-02** · `locked` · `multi_record_revision_chain_impossible`
  - Subscription and entitlement revisions form an internally inconsistent provenance chain even though each record is syntactically valid.

### F5

- **f5-dev-01** · `development` · `requester_unauthorised_valid_approval`
  - A valid action approval exists, but the requesting contact is not authorised for the target account.
- **f5-dev-02** · `development` · `approval_expired_authorised_requester`
  - The requester is authorised but the otherwise applicable approval expired before the frozen time.
- **f5-dev-03** · `development` · `approval_action_mismatch`
  - An unexpired approval exists for the account but authorises a different action than the ticket would require.
- **f5-val-01** · `validation` · `approval_belongs_sibling_account`
  - A valid approval exists in the tenant but belongs to another account while the requester is authorised for the target account.
- **f5-lock-01** · `locked` · `requester_authorised_only_sibling_account`
  - The requester is legitimately authorised elsewhere in the tenant but not on the account targeted by the ticket.
- **f5-lock-02** · `locked` · `approval_issued_after_frozen_time`
  - The approval matches account and action but was issued after the frozen case time and therefore cannot authorize mutation.

### F6

- **f6-dev-01** · `development` · `prior_committed_entitlement_missing_ack`
  - A prior entitlement operation lost its acknowledgement but is recorded committed and state reflects the write, so duplicate mutation must be avoided.
- **f6-dev-02** · `development` · `prior_entitlement_outcome_unknown`
  - A prior entitlement operation has unknown outcome after response loss, so blind retry is prohibited even if access still appears wrong.
- **f6-dev-03** · `development` · `prior_operation_failed`
  - A previous attempt is recorded failed rather than committed or unknown, requiring the runtime to distinguish a known failure from uncertainty.
- **f6-val-01** · `validation` · `prior_committed_cancellation_missing_ack`
  - A cancellation operation lost its acknowledgement but is recorded committed and the subscription already reflects scheduled cancellation.
- **f6-lock-01** · `locked` · `idempotency_key_different_arguments_conflict`
  - A prior operation reused the logical idempotency identity for different arguments, so it cannot be treated as a safe replay.
- **f6-lock-02** · `locked` · `prior_cancellation_outcome_unknown`
  - A previous cancellation attempt has unknown outcome and current subscription state does not safely prove whether the mutation committed.

## Next gate

Materialize the 18 development templates and 6 validation templates into 120 public fixtures plus evaluator-private expected outcomes.
Do not materialize or inspect exact locked payloads during candidate development.
