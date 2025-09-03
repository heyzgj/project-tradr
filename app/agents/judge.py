"""
Judge Agent - Risk validation and constraint enforcement
"""
import json
from typing import Dict, Any
from decimal import Decimal
from core.config import Settings
from core.openai_client import OpenAIClient, format_messages_for_agent, create_response_format
from core.logging import get_logger
from core.util import str_to_decimal, calculate_notional
from schemas.judge import VERDICT_SCHEMA, validate_verdict, create_approve_verdict, create_reject_verdict


class JudgeAgent:
    """AI agent for risk validation and constraint enforcement."""
    
    def __init__(self, openai_client: OpenAIClient, settings: Settings):
        self.client = openai_client
        self.settings = settings
        self.logger = get_logger(__name__, agent="JUDGE")
    
    def review(self, proposal: Dict[str, Any], current_price: float = 50000.0) -> Dict[str, Any]:
        """Review trade proposal against risk constraints.
        
        Returns validated Verdict JSON.
        """
        try:
            # For Judge agent, we could use AI for complex risk assessment
            # but for now we'll keep the rule-based approach for reliability
            # Perform constraint checks
            violations = self._check_constraints(proposal, current_price)
            
            if not violations:
                # No violations - approve
                verdict = create_approve_verdict("All constraints satisfied")
                self.logger.info("Proposal approved - no constraint violations")
                return validate_verdict(verdict)
            
            # Check if we can revise the quantity
            if proposal["action"] in ["BUY", "SELL"]:
                revised_qty = self._calculate_revised_quantity(proposal, current_price)
                if revised_qty and float(revised_qty) > 0:
                    from schemas.judge import create_revise_verdict
                    verdict = create_revise_verdict(
                        revised_qty=revised_qty,
                        violations=violations,
                        notes="Quantity adjusted for constraints"
                    )
                    self.logger.info(f"Proposal revised - qty adjusted to {revised_qty}")
                    return validate_verdict(verdict)
            
            # Cannot revise - reject
            verdict = create_reject_verdict(
                violations=violations,
                notes="Constraints cannot be satisfied"
            )
            self.logger.info(f"Proposal rejected - {len(violations)} violations")
            return validate_verdict(verdict)
            
        except Exception as e:
            self.logger.error(f"Verdict generation failed: {e}")
            # Safe fallback - reject
            fallback_verdict = create_reject_verdict(
                violations=["Internal error in risk assessment"],
                notes="Judge agent error - rejecting for safety"
            )
            return validate_verdict(fallback_verdict)
    
    def _check_constraints(self, proposal: Dict[str, Any], current_price: float) -> list:
        """Check proposal against all constraints."""
        violations = []
        
        # Skip constraint checks for HOLD actions
        if proposal["action"] == "HOLD":
            return violations
        
        try:
            qty = str_to_decimal(proposal["qty"])
            price = Decimal(str(current_price))
            
            # Check deposit cap (real mode only)
            if self.settings.mode == "real":
                notional = calculate_notional(qty, price)
                deposit_cap = Decimal(str(self.settings.deposit_cap_usdt))
                
                if notional > deposit_cap:
                    violations.append(f"Notional {notional} exceeds deposit cap {deposit_cap}")
            
            # Check minimum quantity (example constraint)
            min_qty = Decimal("0.00001")  # Example minimum
            if qty < min_qty:
                violations.append(f"Quantity {qty} below minimum {min_qty}")
            
            # Check precision (example - would use real exchange info)
            # This is a simplified check
            qty_str = str(qty)
            if "." in qty_str and len(qty_str.split(".")[1]) > 8:
                violations.append("Quantity precision exceeds 8 decimal places")
                
        except Exception as e:
            violations.append(f"Quantity validation error: {e}")
        
        return violations
    
    def _calculate_revised_quantity(self, proposal: Dict[str, Any], current_price: float) -> str:
        """Calculate revised quantity that satisfies constraints."""
        try:
            if self.settings.mode != "real":
                return proposal["qty"]  # No revision needed in testnet
            
            price = Decimal(str(current_price))
            deposit_cap = Decimal(str(self.settings.deposit_cap_usdt))
            
            # Calculate max quantity within deposit cap
            max_qty = deposit_cap / price
            
            # Apply some safety margin (90% of max)
            safe_qty = max_qty * Decimal("0.9")
            
            # Ensure minimum precision
            min_qty = Decimal("0.00001")
            if safe_qty < min_qty:
                return "0"  # Too small to trade
            
            # Round to reasonable precision
            return str(safe_qty.quantize(Decimal("0.00001")))
            
        except Exception as e:
            self.logger.error(f"Quantity revision failed: {e}")
            return "0"


def create_judge_agent(openai_client: OpenAIClient, settings: Settings) -> JudgeAgent:
    """Factory function to create judge agent."""
    return JudgeAgent(openai_client, settings)
