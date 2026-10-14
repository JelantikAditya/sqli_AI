"""Evaluator-only FPR accounting for one planned negative group and replicate."""

from analyze_response import confusion_class, validate_run_summary
from rag_pipeline import load_catalog


def summarize_fpr_replicate(summaries, *, experiment_id, condition_id, replicate,
                            scenario_ids=("S10", "S11", "S12"), candidate_budget=10):
    """Retain abstentions/missing units; never report decided-only FPR as primary."""
    negatives = {s["scenario_id"] for s in load_catalog()["scenarios"] if s["ground_truth"] == "negative"}
    expected = set(scenario_ids)
    if (not expected or len(expected) != len(scenario_ids) or not expected.issubset(negatives)
            or condition_id not in {"A", "B"} or type(replicate) is not int or replicate not in {1, 2, 3}
            or type(candidate_budget) is not int or not 1 <= candidate_budget <= 10
            or not isinstance(experiment_id, str) or not experiment_id):
        raise ValueError("Use an explicit experiment, A/B replicate, and unique planned negative scenarios.")
    by_scenario = {}
    for summary in summaries:
        validate_run_summary(summary)
        ctx = summary["context"]
        if (ctx["experiment_id"] != experiment_id or ctx["condition_id"] != condition_id
                or ctx["replicate"] != replicate or ctx["scenario_id"] not in expected
                or summary["expected_budget"] != candidate_budget):
            raise ValueError("Summary does not belong to the planned FPR group.")
        if ctx["scenario_id"] in by_scenario:
            raise ValueError("Select one final ledger attempt per planned unit; duplicate scenario found.")
        by_scenario[ctx["scenario_id"]] = summary
    classes = [confusion_class(summary, "negative") for summary in by_scenario.values()]
    fp, tn = classes.count("FP"), classes.count("TN")
    abstained = sum(s["system_decision"] == "inconclusive" for s in by_scenario.values())
    not_evaluable = sum(s["system_decision"] == "not_evaluable" for s in by_scenario.values())
    missing = sorted(expected - set(by_scenario))
    decided = fp + tn
    complete = decided == len(expected)
    status = "complete" if complete else "incomplete" if missing or not_evaluable else "inconclusive"
    return {
        "scope": "development-fpr-accounting-not-formal-validated-results",
        "experiment_id": experiment_id, "condition_id": condition_id, "replicate": replicate,
        "planned_scenario_ids": sorted(expected), "planned_negative_units": len(expected),
        "FP": fp, "TN": tn, "inconclusive_units": abstained, "not_evaluable_units": not_evaluable,
        "missing_scenario_ids": missing, "binary_decision_units": decided,
        "decision_coverage": decided / len(expected),
        "status": status,
        # Withhold the primary number unless every planned negative unit is binary and evaluable.
        "primary_fpr": fp / decided if complete else None,
        "diagnostic_decided_only_fpr": fp / decided if decided else None,
        "primary_summary_eligible": complete,
    }
