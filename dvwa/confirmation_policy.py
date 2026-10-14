"""Shared T01 policy for one logical candidate, never a vote across runs."""

CONFIRMATION_POLICY_ID = "three-valid-confirmations-all-positive-v1"
CONFIRMATIONS_REQUIRED = 3


def classify_confirmations(results: dict[int, bool], *, runtime_valid: bool = True) -> dict:
    """Only trials 1/2/3 can establish success; partial/extra trials cannot."""
    if any(type(index) is not int or index < 1 or type(signal) is not bool
           for index, signal in results.items()):
        raise ValueError("Confirmation indices must be positive integers with boolean signals.")
    positive = sum(results.values())
    if not runtime_valid:
        status = "RUNTIME_INVALID"
    elif set(results) != {1, 2, 3}:
        status = "INCOMPLETE_CONFIRMATIONS"
    elif positive == CONFIRMATIONS_REQUIRED:
        status = "CONSISTENT_POSITIVE"
    elif positive:
        status = "MIXED_EVIDENCE"
    else:
        status = "CONSISTENT_NEGATIVE"
    return {
        "confirmation_policy_id": CONFIRMATION_POLICY_ID,
        "evidence_status": status,
        "valid_confirmation_count": len(results),
        "positive_confirmation_count": positive,
        # None means not evaluable, rather than an unsuccessful valid candidate.
        "confirmed_success": (status == "CONSISTENT_POSITIVE")
        if status in {"CONSISTENT_POSITIVE", "MIXED_EVIDENCE", "CONSISTENT_NEGATIVE"} else None,
    }
