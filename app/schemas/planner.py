"""
Plan JSON Schema for Planner Agent output
"""
from typing import Dict, Any, List
import json

# Plan JSON Schema per spec
PLAN_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["mode", "explore_ratio", "next_wakeup_secs", "strategies"],
    "properties": {
        "mode": {"enum": ["OBSERVE", "TRADE"]},
        "explore_ratio": {"type": "number", "minimum": 0, "maximum": 1},
        "next_wakeup_secs": {"type": "integer", "minimum": 30, "maximum": 3600},
        "strategies": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["policy_id"],
                "properties": {
                    "policy_id": {"type": "string"},
                    "params": {
                        "type": "object",
                        "additionalProperties": False
                    }
                },
                "additionalProperties": False
            },
            "minItems": 1,
            "maxItems": 3
        }
    },
    "additionalProperties": False
}


def validate_plan(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate plan data against schema.
    
    Returns validated data or raises ValueError.
    """
    if not isinstance(data, dict):
        raise ValueError("Plan must be a dictionary")
    
    # Check required fields
    required = ["mode", "explore_ratio", "next_wakeup_secs", "strategies"]
    for field in required:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    
    # Validate mode
    if data["mode"] not in ["OBSERVE", "TRADE"]:
        raise ValueError(f"Invalid mode: {data['mode']}")
    
    # Validate explore_ratio
    if not isinstance(data["explore_ratio"], (int, float)) or not (0 <= data["explore_ratio"] <= 1):
        raise ValueError(f"explore_ratio must be number between 0 and 1")
    
    # Validate next_wakeup_secs
    if not isinstance(data["next_wakeup_secs"], int) or not (30 <= data["next_wakeup_secs"] <= 3600):
        raise ValueError(f"next_wakeup_secs must be integer between 30 and 3600")
    
    # Validate strategies
    if not isinstance(data["strategies"], list) or not (1 <= len(data["strategies"]) <= 3):
        raise ValueError(f"strategies must be array with 1-3 items")
    
    for i, strategy in enumerate(data["strategies"]):
        if not isinstance(strategy, dict):
            raise ValueError(f"Strategy {i} must be object")
        if "policy_id" not in strategy:
            raise ValueError(f"Strategy {i} missing policy_id")
        if not isinstance(strategy["policy_id"], str):
            raise ValueError(f"Strategy {i} policy_id must be string")
        # params is optional now
        if "params" in strategy and not isinstance(strategy["params"], dict):
            raise ValueError(f"Strategy {i} params must be object")
    
    return data


def create_observe_plan(wakeup_secs: int = 300) -> Dict[str, Any]:
    """Create a minimal OBSERVE mode plan."""
    return {
        "mode": "OBSERVE",
        "explore_ratio": 0.0,
        "next_wakeup_secs": max(30, min(wakeup_secs, 3600)),
        "strategies": [
            {
                "policy_id": "observe_only",
                "params": {}
            }
        ]
    }


def create_trade_plan(explore_ratio: float, strategies: List[Dict[str, Any]], 
                     wakeup_secs: int = 300) -> Dict[str, Any]:
    """Create a TRADE mode plan with strategies."""
    return {
        "mode": "TRADE",
        "explore_ratio": max(0.0, min(explore_ratio, 1.0)),
        "next_wakeup_secs": max(30, min(wakeup_secs, 3600)),
        "strategies": strategies[:3]  # Max 3 strategies
    }


def get_plan_schema_for_openai() -> Dict[str, Any]:
    """Get schema formatted for OpenAI Responses API."""
    return {
        "name": "plan_response",
        "schema": PLAN_SCHEMA
    }
