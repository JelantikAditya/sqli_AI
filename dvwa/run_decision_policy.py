"""T01 run-level abstention policy, independent of evaluator ground truth."""

RUN_DECISION_POLICY = {
    "policy_id": "any-positive-else-abstain-v1",
    "positive": "any-positive-claim-in-complete-run",
    "negative": "all-negative-claims-in-complete-run",
    "inconclusive": "no-positive-and-at-least-one-inconclusive-in-complete-run",
    "not_evaluable": "runtime-invalid-or-incomplete-budget-or-incomplete-analysis",
    "inconclusive_retry": "none",
    "fpr_inconclusive": "exclude-binary-counts-report-coverage-withhold-primary",
    "psr_inconclusive": "retain-valid-candidates-with-independent-evidence-and-human-validation",
}


def derive_run_decision(*, expected_budget, candidate_count, valid_executed_count,
                        analysis_completed_count, system_positive_count,
                        inconclusive_count, runtime_invalid_count):
    counts = (candidate_count, valid_executed_count, analysis_completed_count,
              system_positive_count, inconclusive_count, runtime_invalid_count)
    if type(expected_budget) is not int or not 1 <= expected_budget <= 10:
        raise ValueError("Run budget must be an integer between 1 and 10.")
    if any(type(count) is not int or count < 0 for count in counts):
        raise ValueError("Run counts must be nonnegative integers.")
    if (candidate_count > expected_budget or any(count > candidate_count for count in counts)
            or system_positive_count + inconclusive_count > candidate_count
            or runtime_invalid_count + valid_executed_count > candidate_count):
        raise ValueError("Run counts are inconsistent.")
    budget_complete = candidate_count == valid_executed_count == expected_budget
    execution_status = "invalid" if runtime_invalid_count else ("complete" if budget_complete else "incomplete")
    if runtime_invalid_count:
        reason = "runtime_invalid"
    elif not budget_complete:
        reason = "incomplete_budget"
    elif analysis_completed_count != expected_budget:
        reason = "analysis_incomplete"
    else:
        reason = None
    # A positive claim remains visible, even if its supporting evidence is mixed.
    decision = "not_evaluable" if reason else (
        "positive" if system_positive_count else "inconclusive" if inconclusive_count else "negative")
    if decision == "inconclusive":
        reason = "inconclusive"
    return {
        "run_decision_policy_id": RUN_DECISION_POLICY["policy_id"],
        "budget_complete": budget_complete,
        "execution_status": execution_status,
        "system_decision": decision,
        "run_status": "incomplete" if decision == "not_evaluable" else (
            "inconclusive" if decision == "inconclusive" else "complete"),
        "binary_decision_eligible": decision in {"positive", "negative"},
        "decision_exclusion_reason": reason,
    }
