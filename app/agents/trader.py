"""
Trader Agent - Market analysis and trade proposal generation
"""
import json
from typing import Dict, Any
from core.config import Settings
from core.openai_client import OpenAIClient, format_messages_for_agent, create_response_format
from core.logging import get_logger
from schemas.trader import PROPOSAL_SCHEMA, validate_proposal, create_hold_proposal


class TraderAgent:
    """AI agent for market analysis and trade proposal generation."""
    
    def __init__(self, openai_client: OpenAIClient, settings: Settings):
        self.client = openai_client
        self.settings = settings
        self.logger = get_logger(__name__, agent="TRADER")
    
    def propose(self, plan: Dict[str, Any], indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Generate trade proposal based on plan and market indicators.
        
        Returns validated Proposal JSON.
        """
        try:
            # Create system prompt
            system_prompt = self._create_system_prompt()
            
            # Create user prompt with context
            user_prompt = self._create_user_prompt(plan, indicators)
            
            # Format messages
            messages = format_messages_for_agent(system_prompt, user_prompt)
            
            # Create response format
            response_format = create_response_format("proposal_response", PROPOSAL_SCHEMA)
            
            # Call OpenAI with trader-specific high reasoning (thinking mode)
            response = self.client.create_structured_completion(
                model=self.settings.model_trader,
                messages=messages,
                response_format=response_format,
                temperature=0.5,
                max_tokens=200,
                reasoning_effort="high",  # Explicit high reasoning for complex trading analysis
                agent_type="trader"
            )
            
            # Validate response
            validated_proposal = validate_proposal(response)
            
            self.logger.info(f"Generated proposal: {validated_proposal['action']} "
                           f"{validated_proposal['qty']} (confidence: {validated_proposal['confidence']})")
            
            return validated_proposal
            
        except Exception as e:
            self.logger.error(f"Proposal generation failed: {e}")
            # Return safe fallback
            fallback_proposal = create_hold_proposal(
                policy_id="fallback",
                hypothesis="Error in analysis, maintaining safe position",
                confidence=0.3
            )
            self.logger.info("Using fallback HOLD proposal")
            return fallback_proposal
    
    def _create_system_prompt(self) -> str:
        """Create system prompt for trader agent with enhanced reasoning."""
        return """You are an advanced AI trading agent with deep reasoning capabilities. Your goal is to generate optimal trade proposals through comprehensive market analysis.

REASONING APPROACH:
1. ANALYZE: Thoroughly examine all market indicators, price patterns, and technical signals
2. SYNTHESIZE: Connect patterns across different timeframes and indicators  
3. EVALUATE: Assess risk-reward ratios and probability of success
4. DECIDE: Make data-driven trading decisions with clear rationale

MARKET ANALYSIS FRAMEWORK:
- Technical Indicators: RSI levels, moving average relationships, volume patterns
- Price Action: Support/resistance, trend strength, momentum shifts  
- Market Context: Volatility regime, correlation patterns, sentiment indicators
- Risk Assessment: Position sizing, stop-loss levels, maximum drawdown scenarios

DECISION CRITERIA:
- BUY: Strong bullish signals, favorable risk/reward (>2:1), high confidence (>0.7)
- SELL: Strong bearish signals, favorable risk/reward (>2:1), high confidence (>0.7)  
- HOLD: Mixed signals, unfavorable risk/reward, uncertainty, or risk management

OUTPUT REQUIREMENTS:
- JSON format only, conforming exactly to the provided schema
- Hypothesis: Concise reasoning (max 120 chars) explaining the core logic
- Confidence: 0.0-1.0 based on signal strength and conviction level
- Quantity: Precise position size considering risk management

RISK MANAGEMENT:
- Never risk more than 2% of capital on a single trade
- Prefer smaller positions when uncertainty exists
- Consider market volatility in position sizing
- Align with overall strategic objectives

Think deeply about market dynamics before making decisions."""
    
    def _create_user_prompt(self, plan: Dict[str, Any], indicators: Dict[str, Any]) -> str:
        """Create user prompt with plan and indicator context."""
        plan_summary = self._summarize_plan(plan)
        indicators_summary = self._summarize_indicators(indicators)
        
        return f"""Strategic Plan:
{plan_summary}

Market Indicators:
{indicators_summary}

Symbol: {self.settings.symbol}
Mode: {self.settings.mode}
Deposit Cap: {self.settings.deposit_cap_usdt} USDT

Analyze the market conditions and generate a trade proposal:
- Consider technical indicators and market signals
- Follow the strategic plan guidance
- Use appropriate position sizing for the mode
- Provide clear, concise hypothesis
- Assign confidence based on signal strength

Output valid Proposal JSON only."""
    
    def _summarize_plan(self, plan: Dict[str, Any]) -> str:
        """Summarize plan for prompt."""
        mode = plan.get("mode", "UNKNOWN")
        strategies = plan.get("strategies", [])
        explore_ratio = plan.get("explore_ratio", 0.0)
        
        strategy_names = [s.get("policy_id", "unknown") for s in strategies]
        
        return f"Mode: {mode} | Strategies: {', '.join(strategy_names)} | Exploration: {explore_ratio:.2f}"
    
    def _summarize_indicators(self, indicators: Dict[str, Any]) -> str:
        """Summarize indicators for prompt."""
        if not indicators:
            return "No indicators available"
        
        summary_parts = []
        
        # Common indicators
        if "rsi" in indicators:
            rsi = indicators["rsi"]
            summary_parts.append(f"RSI: {rsi:.1f}")
        
        if "ma20" in indicators:
            ma20 = indicators["ma20"]
            summary_parts.append(f"MA20: {ma20:.2f}")
        
        if "price" in indicators:
            price = indicators["price"]
            summary_parts.append(f"Price: {price:.2f}")
        
        if "volume_avg" in indicators:
            vol = indicators["volume_avg"]
            summary_parts.append(f"Volume: {vol:.0f}")
        
        return " | ".join(summary_parts) if summary_parts else str(indicators)


def create_trader_agent(openai_client: OpenAIClient, settings: Settings) -> TraderAgent:
    """Factory function to create trader agent."""
    return TraderAgent(openai_client, settings)
