"""
OpenAI Chat Completions API with structured outputs (JSON Schema)
"""
import json
from typing import Dict, Any, Optional
from core.config import Settings
from core.logging import get_logger, PerformanceTimer


class OpenAIClient:
    """OpenAI Chat Completions client with structured outputs using JSON Schema."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(__name__)
        self._client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize OpenAI client."""
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.settings.openai_api_key)
            self.logger.info("OpenAI client initialized with structured outputs support")
        except Exception as e:
            self.logger.error(f"OpenAI client initialization failed: {e}")
            self._client = None

    def create_structured_completion(
        self,
        model: str,
        messages: list,
        response_format: Dict[str, Any],
        temperature: float = 0.5,
        max_tokens: int = 200,
        reasoning_effort: str = "medium",
        agent_type: str = "generic"
    ) -> Dict[str, Any]:
        """Create structured completion with GPT-5-mini enhanced capabilities."""
        
        with PerformanceTimer(self.logger, f"OpenAI {model} structured completion", model=model):
            try:
                if self._client is None:
                    # Return mock data when client unavailable
                    return self._create_mock_response(response_format)
                
                # GPT-5-mini supports structured outputs natively
                if "gpt-5-mini" in model.lower():
                    return self._create_gpt5_mini_completion(
                        model, messages, response_format, temperature, max_tokens, agent_type
                    )
                elif "o1-mini" in model.lower():
                    return self._create_o1_completion(
                        model, messages, response_format, reasoning_effort, agent_type
                    )
                else:
                    # Use standard GPT-4 structured outputs
                    return self._create_standard_completion(
                        model, messages, response_format, temperature, max_tokens
                    )
                
            except Exception as e:
                self.logger.error(f"OpenAI API error: {e}")
                # Return mock fallback on any error
                return self._create_mock_response(response_format)

    def _create_gpt5_mini_completion(
        self,
        model: str,
        messages: list,
        response_format: Dict[str, Any],
        temperature: float,
        max_tokens: int,
        agent_type: str
    ) -> Dict[str, Any]:
        """Create completion using GPT-5-mini with enhanced reasoning and structured outputs."""
        try:
            # GPT-5-mini supports structured outputs natively
            # Optimize max_tokens for GPT-5-mini (it can generate up to 128k tokens)
            if max_tokens < 500:  # Give it more room for reasoning
                max_tokens = 500
                
            response = self._client.chat.completions.create(
                model="gpt-5-mini",  # Use exact GPT-5-mini model name
                messages=messages,
                response_format=response_format,  # Native structured output support
                temperature=temperature,
                max_tokens=max_tokens,
                # Add timeout to prevent hanging
                timeout=30  # 30 second timeout for better reliability
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from GPT-5-mini")
            
            # Parse and validate JSON (should be structured already)
            result = json.loads(content)
            self.logger.info(f"GPT-5-mini completion successful for {agent_type} agent")
            return result
            
        except Exception as e:
            self.logger.warning(f"GPT-5-mini completion failed: {e}, falling back to GPT-4o")
            # Fallback to GPT-4o if GPT-5-mini fails
            return self._create_standard_completion(
                "gpt-4o", messages, response_format, temperature, max_tokens
            )

    def _create_o1_completion(
        self,
        model: str,
        messages: list,
        response_format: Dict[str, Any],
        reasoning_effort: str,
        agent_type: str
    ) -> Dict[str, Any]:
        """Create completion using o1-mini with reasoning capabilities."""
        try:
            # o1-mini models have specific parameter requirements
            # Note: o1-mini may not support structured outputs directly yet
            # So we'll use a hybrid approach with explicit JSON instructions
            
            # Enhance the system message with JSON schema requirements
            enhanced_messages = self._enhance_messages_for_o1(messages, response_format)
            
            # Set reasoning effort based on agent type
            if agent_type == "trader":
                reasoning_effort = "high"  # Trader needs deep market analysis
            elif agent_type == "judge":
                reasoning_effort = "medium"  # Judge needs careful risk assessment
            else:  # planner
                reasoning_effort = "medium"  # Planner needs strategic thinking
            
            response = self._client.chat.completions.create(
                model="o1-mini",  # Use the actual o1-mini model name
                messages=enhanced_messages,
                reasoning_effort=reasoning_effort,
                # Note: o1 models don't support temperature, max_tokens, or response_format yet
                # These parameters are handled differently
            )
            
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from o1-mini")
            
            # Extract JSON from the response (o1 models return reasoning + JSON)
            result = self._extract_json_from_o1_response(content, response_format)
            
            self.logger.info(f"o1-mini completion successful with {reasoning_effort} reasoning")
            return result
            
        except Exception as e:
            self.logger.warning(f"o1-mini completion failed: {e}, falling back to standard model")
            # Fallback to GPT-4 if o1-mini fails
            return self._create_standard_completion(
                "gpt-4o-mini", messages, response_format, 0.5, 200
            )

    def _create_standard_completion(
        self,
        model: str,
        messages: list,
        response_format: Dict[str, Any],
        temperature: float,
        max_tokens: int
    ) -> Dict[str, Any]:
        """Create standard GPT-4 completion with structured outputs."""
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from OpenAI")
        
        # Parse and validate JSON
        result = json.loads(content)
        self.logger.info("Standard OpenAI completion successful")
        return result

    def _enhance_messages_for_o1(self, messages: list, response_format: Dict[str, Any]) -> list:
        """Enhance messages for o1-mini with explicit JSON schema instructions."""
        schema = response_format.get("json_schema", {}).get("schema", {})
        schema_name = response_format.get("json_schema", {}).get("name", "response")
        
        # Add explicit JSON instruction to the last user message
        enhanced_messages = messages.copy()
        if enhanced_messages:
            last_message = enhanced_messages[-1]["content"]
            json_instruction = f"""

CRITICAL: You must respond with ONLY a valid JSON object that matches this exact schema:

Schema name: {schema_name}
Required fields: {list(schema.get('required', []))}
Schema: {json.dumps(schema, indent=2)}

Your response must be ONLY the JSON object, no other text, explanations, or reasoning outside the JSON.
"""
            enhanced_messages[-1]["content"] = last_message + json_instruction
        
        return enhanced_messages

    def _extract_json_from_o1_response(self, content: str, response_format: Dict[str, Any]) -> Dict[str, Any]:
        """Extract JSON from o1-mini response which may include reasoning text."""
        try:
            # Try to parse the entire content as JSON first
            return json.loads(content)
        except json.JSONDecodeError:
            # If that fails, look for JSON block in the response
            import re
            
            # Look for JSON blocks
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            matches = re.findall(json_pattern, content, re.DOTALL)
            
            for match in matches:
                try:
                    result = json.loads(match)
                    # Validate it has expected structure
                    schema = response_format.get("json_schema", {}).get("schema", {})
                    required_fields = schema.get("required", [])
                    if all(field in result for field in required_fields):
                        return result
                except json.JSONDecodeError:
                    continue
            
            # If no valid JSON found, return mock response
            self.logger.warning("Could not extract valid JSON from o1 response, using mock")
            return self._create_mock_response(response_format)

    def _create_mock_response(self, response_format: Dict[str, Any]) -> Dict[str, Any]:
        """Generate mock response based on schema name."""
        try:
            schema_name = response_format.get("json_schema", {}).get("name", "unknown")
            
            if "plan" in schema_name.lower():
                return {
                    "mode": "OBSERVE",
                    "explore_ratio": 0.1,
                    "next_wakeup_secs": 300,
                    "strategies": [
                        {"policy_id": "observe_only", "params": {}}
                    ],
                }
            elif "proposal" in schema_name.lower():
                return {
                    "action": "HOLD",
                    "qty": "0",
                    "policy_id": "observe_only",
                    "hypothesis": "Market unclear - using fallback",
                    "confidence": 0.5,
                }
            elif "verdict" in schema_name.lower():
                return {
                    "decision": "APPROVE",
                    "notes": "Fallback approval"
                }
            else:
                return {"status": "mock_response"}
                
        except Exception as e:
            self.logger.error(f"Mock response generation failed: {e}")
            return {"status": "error"}


def create_openai_client(settings: Optional[Settings] = None) -> OpenAIClient:
    """Factory function to create OpenAI client."""
    if settings is None:
        settings = Settings()
    return OpenAIClient(settings)


def format_messages_for_agent(system_prompt: str, user_content: str) -> list:
    """Format messages for OpenAI Chat Completions."""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def create_response_format(schema_name: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Create response format for structured outputs with JSON schema."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "schema": schema,
            "strict": True
        },
    }
