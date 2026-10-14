"""Fixed T01 condition rotation; selection never overrides the planned order."""

EXECUTION_ORDER_POLICY = {
    "policy_id": "replicate-block-mirrored-rotation-v1",
    "block_order": "replicate-then-scenario",
    "scenario_order": [f"S{i}" for i in range(1, 13)],
    "odd_scenario_orders": {"1": ["A", "B", "C"], "2": ["B", "C", "A"], "3": ["C", "A", "B"]},
    "even_scenario_orders": {"1": ["C", "B", "A"], "2": ["A", "C", "B"], "3": ["B", "A", "C"]},
    "excluded_conditions": "retain-ledger-skip-execution",
    "subset_order": "filter-canonical-schedule",
    "resume_order": "keep-schedule-skip-completed-retry-invalid-in-original-slot",
}


def ordered_run_slots(protocol, *, scenario_ids=None, condition_ids=None, replicates=None):
    """Produce canonical slots, including explicit C exclusions on Impossible."""
    policy = protocol.get("execution_order")
    if policy != EXECUTION_ORDER_POLICY:
        raise ValueError("Use the recorded mirrored condition rotation.")
    conditions = {c["condition_id"]: c for c in protocol["conditions"]}
    selected_scenarios = set(policy["scenario_order"] if scenario_ids is None else scenario_ids)
    selected_conditions = set(conditions if condition_ids is None else condition_ids)
    selected_replicates = set((1, 2, 3) if replicates is None else replicates)
    if (not selected_scenarios or not selected_scenarios.issubset(policy["scenario_order"])
            or not selected_conditions or not selected_conditions.issubset(conditions)
            or not selected_replicates or not selected_replicates.issubset({1, 2, 3})):
        raise ValueError("Select known nonempty scenario, condition and replicate subsets.")
    slot_index, execution_index = 0, 0
    for replicate in (1, 2, 3):
        if replicate not in selected_replicates:
            continue
        for scenario_id in policy["scenario_order"]:
            if scenario_id not in selected_scenarios:
                continue
            parity = "odd" if int(scenario_id[1:]) % 2 else "even"
            nominal = policy[f"{parity}_scenario_orders"][str(replicate)]
            for position, condition_id in enumerate(nominal, start=1):
                if condition_id not in selected_conditions:
                    continue
                applicable = scenario_id in conditions[condition_id]["scenario_ids"]
                slot_index += 1
                if applicable:
                    execution_index += 1
                yield {
                    "scenario_id": scenario_id, "replicate": replicate, "condition_id": condition_id,
                    "order_policy_id": policy["policy_id"],
                    "nominal_condition_position": position,
                    "planned_slot_index": slot_index,
                    "planned_execution_index": execution_index if applicable else None,
                    "applicable": applicable,
                }
