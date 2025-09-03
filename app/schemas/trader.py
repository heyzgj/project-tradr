"""
Proposal JSON Schema for Trader Agent output
"""
from typing import Dict, Any
import json

# Proposal JSON Schema per spec
PROPOSAL_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["action", "qty", "policy_id", "hypothesis", "confidence"],
    "properties": {
        "action": {"enum": ["BUY", "SELL", "HOLD"]},
        "qty": {"type": "string", "pattern": "^\\d+(\\.\\d+)?$"},
        "policy_id": {"type": "string"},
        "hypothesis": {"type": "string", "maxLength": 120},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1}
    },
    "additionalProperties": False
}


def validate_proposal(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate proposal data against schema.
    
    Returns validated data or raises ValueError.
    """
    if not isinstance(data, dict):
        raise ValueError("Proposal must be a dictionary")
    
    # Check required fields
    required = ["action", "qty", "policy_id", "hypothesis", "confidence"]
    for field in required:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    
    # Validate action
    if data["action"] not in ["BUY", "SELL", "HOLD"]:
        raise ValueError(f"Invalid action: {data['action']}")
    
    # Validate qty (string with decimal pattern)
    if not isinstance(data["qty"], str):
        raise ValueError("qty must be string")
    try:
        float(data["qty"])  # Check if valid decimal
    except ValueError:
        raise ValueError(f"qty must be valid decimal string: {data['qty']}")
    
    # Validate policy_id
    if not isinstance(data["policy_id"], str):
        raise ValueError("policy_id must be string")
    
    # Validate hypothesis
    if not isinstance(data["hypothesis"], str) or len(data["hypothesis"]) > 120:
        raise ValueError("hypothesis must be string with max 120 characters")
    
    # Validate confidence
    if not isinstance(data["confidence"], (int, float)) or not (0 <= data["confidence"] <= 1):
        raise ValueError("confidence must be number between 0 and 1")
    
    return data


def create_hold_proposal(policy_id: str, hypothesis: str, confidence: float = 0.5) -> Dict[str, Any]:
    """Create a HOLD proposal (safe default)."""
    return {
        "action": "HOLD",
        "qty": "0",
        "policy_id": policy_id,
        "hypothesis": hypothesis[:120],  # Truncate to max length
        "confidence": max(0.0, min(confidence, 1.0))
    }


def create_trade_proposal(action: str, qty: str, policy_id: str, 
                         hypothesis: str, confidence: float) -> Dict[str, Any]:
    """Create a BUY/SELL proposal."""
    if action not in ["BUY", "SELL"]:
        raise ValueError(f"Invalid action: {action}")
    
    return {
        "action": action,
        "qty": str(qty),  # Ensure string format
        "policy_id": policy_id,
        "hypothesis": hypothesis[:120],  # Truncate to max length
        "confidence": max(0.0, min(confidence, 1.0))
    }


def get_proposal_schema_for_openai() -> Dict[str, Any]:
    """Get schema formatted for OpenAI Responses API."""
    return {
        "name": "proposal_response", 
        "schema": PROPOSAL_SCHEMA
    }
