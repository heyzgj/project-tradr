"""
Verdict JSON Schema for Judge Agent output
"""
from typing import Dict, Any, List, Optional

# Verdict JSON Schema per spec
VERDICT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["decision"],
    "properties": {
        "decision": {"enum": ["APPROVE", "REVISE", "REJECT"]},
        "revised_qty": {"type": "string", "pattern": "^\\d+(\\.\\d+)?$"},
        "violations": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "notes": {"type": "string", "maxLength": 120}
    },
    "additionalProperties": False
}


def validate_verdict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate verdict data against schema.
    
    Returns validated data or raises ValueError.
    """
    if not isinstance(data, dict):
        raise ValueError("Verdict must be a dictionary")
    
    # Check required fields
    if "decision" not in data:
        raise ValueError("Missing required field: decision")
    
    # Validate decision
    if data["decision"] not in ["APPROVE", "REVISE", "REJECT"]:
        raise ValueError(f"Invalid decision: {data['decision']}")
    
    # Validate optional fields
    if "revised_qty" in data:
        if not isinstance(data["revised_qty"], str):
            raise ValueError("revised_qty must be string")
        try:
            float(data["revised_qty"])  # Check if valid decimal
        except ValueError:
            raise ValueError(f"revised_qty must be valid decimal string: {data['revised_qty']}")
    
    if "violations" in data:
        if not isinstance(data["violations"], list) or len(data["violations"]) > 4:
            raise ValueError("violations must be array with max 4 items")
        for violation in data["violations"]:
            if not isinstance(violation, str):
                raise ValueError("All violations must be strings")
    
    if "notes" in data:
        if not isinstance(data["notes"], str) or len(data["notes"]) > 120:
            raise ValueError("notes must be string with max 120 characters")
    
    return data


def create_approve_verdict(notes: str = "") -> Dict[str, Any]:
    """Create an APPROVE verdict."""
    verdict = {"decision": "APPROVE"}
    if notes:
        verdict["notes"] = notes[:120]
    return verdict


def create_revise_verdict(revised_qty: str, violations: List[str], notes: str = "") -> Dict[str, Any]:
    """Create a REVISE verdict with corrected quantity."""
    verdict = {
        "decision": "REVISE",
        "revised_qty": str(revised_qty),
        "violations": violations[:4]  # Max 4 violations
    }
    if notes:
        verdict["notes"] = notes[:120]
    return verdict


def create_reject_verdict(violations: List[str], notes: str = "") -> Dict[str, Any]:
    """Create a REJECT verdict."""
    verdict = {
        "decision": "REJECT",
        "violations": violations[:4]  # Max 4 violations
    }
    if notes:
        verdict["notes"] = notes[:120]
    return verdict


def get_verdict_schema_for_openai() -> Dict[str, Any]:
    """Get schema formatted for OpenAI Responses API."""
    return {
        "name": "verdict_response",
        "schema": VERDICT_SCHEMA
    }
