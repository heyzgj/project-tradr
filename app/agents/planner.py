"""
Planner Agent - Strategic planning with adaptive behavior
"""
import json
from typing import Dict, Any
from core.config import Settings
from core.openai_client import OpenAIClient, format_messages_for_agent, create_response_format
from core.logging import get_logger
from schemas.planner import PLAN_SCHEMA, validate_plan, create_observe_plan


class PlannerAgent:
    """AI agent for strategic planning and mode selection."""
    
    def __init__(self, openai_client: OpenAIClient, settings: Settings):
        self.client = openai_client
        self.settings = settings
        self.logger = get_logger(__name__, agent="PLANNER")
    
    def plan(self, memory_context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate strategic plan based on memory and market context.
        
        Returns validated Plan JSON.
        """
        try:
            # Create system prompt
            system_prompt = self._create_system_prompt()
            
            # Create user prompt with context
            user_prompt = self._create_user_prompt(memory_context)
            
            # Format messages
            messages = format_messages_for_agent(system_prompt, user_prompt)
            
            # Create response format
            response_format = create_response_format("plan_response", PLAN_SCHEMA)
            
            # Call OpenAI with planner-specific reasoning
            response = self.client.create_structured_completion(
                model=self.settings.model_planner,
                messages=messages,
                response_format=response_format,
                temperature=0.5,
                max_tokens=200,
                agent_type="planner"
            )
            
            # Validate response
            validated_plan = validate_plan(response)
            
            self.logger.info(f"Generated plan: mode={validated_plan['mode']}, "
                           f"strategies={len(validated_plan['strategies'])}")
            
            return validated_plan
            
        except Exception as e:
            self.logger.error(f"Plan generation failed: {e}")
            # Return safe fallback
            fallback_plan = create_observe_plan(300)
            self.logger.info("Using fallback OBSERVE plan")
            return fallback_plan
    
    def _create_system_prompt(self) -> str:
        """Create system prompt for planner agent with strategic reasoning."""
        return """You are an advanced strategic trading planner with sophisticated reasoning capabilities. Your mission is to maximize long-term portfolio growth through intelligent strategy selection and risk management.

STRATEGIC REASONING FRAMEWORK:
1. ASSESS: Evaluate current market regime, volatility, and trend conditions
2. ANALYZE: Review recent performance data and strategy effectiveness  
3. ADAPT: Adjust strategy selection based on changing market dynamics
4. OPTIMIZE: Balance exploration of new approaches vs exploitation of proven strategies

DECISION MATRIX:
- OBSERVE Mode: Use during high uncertainty, major news events, or after significant losses
- TRADE Mode: Use during stable conditions with clear market signals and proven strategies

EXPLORATION STRATEGY:
- Low (0.0-0.3): Exploit proven strategies in stable, profitable conditions
- Medium (0.3-0.7): Balanced approach during normal market conditions  
- High (0.7-1.0): Explore new strategies during poor performance or changing regimes

TIMING OPTIMIZATION:
- Short intervals (30-300s): Active trading in volatile, opportunity-rich markets
- Medium intervals (300-1800s): Normal trading conditions with moderate volatility
- Long intervals (1800-3600s): Low volatility, uncertain conditions, or risk management

RISK MANAGEMENT PRIORITIES:
1. Capital preservation during adverse conditions
2. Gradual position scaling during recovery phases
3. Aggressive growth only in confirmed favorable conditions
4. Continuous learning from both successes and failures

OUTPUT JSON ONLY. Think strategically about market dynamics and performance optimization."""
    
    def _create_user_prompt(self, memory_context: Dict[str, Any]) -> str:
        """Create user prompt with memory context."""
        context_summary = self._summarize_context(memory_context)
        
        return f"""Current Context:
{context_summary}

Symbol: {self.settings.symbol}
Mode: {self.settings.mode}
Deposit Cap: {self.settings.deposit_cap_usdt} USDT

Generate a strategic plan considering:
- Recent strategy performance from memory
- Current market regime and volatility
- Risk management and position sizing
- Exploration vs exploitation balance

Output valid Plan JSON only."""
    
    def _summarize_context(self, memory_context: Dict[str, Any]) -> str:
        """Summarize memory context for prompt."""
        if not memory_context:
            return "No prior memory available - initial planning cycle"
        
        summary_parts = []
        
        # Count recent experiments
        experiment_count = len(memory_context)
        summary_parts.append(f"Recent experiments: {experiment_count}")
        
        # Sample recent strategies
        recent_strategies = list(memory_context.keys())[:3]
        if recent_strategies:
            summary_parts.append(f"Recent strategies: {', '.join(recent_strategies)}")
        
        # Basic performance indicators
        executed_count = sum(1 for exp in memory_context.values() 
                           if isinstance(exp, dict) and exp.get("result") == "executed")
        if executed_count > 0:
            summary_parts.append(f"Executed trades: {executed_count}")
        
        return " | ".join(summary_parts)


def create_planner_agent(openai_client: OpenAIClient, settings: Settings) -> PlannerAgent:
    """Factory function to create planner agent."""
    return PlannerAgent(openai_client, settings)
