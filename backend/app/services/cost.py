"""
Cost calculation for LLM API usage.

Pricing as of February 2025 (update as needed):
- Anthropic Claude Sonnet 4.5: $3/MTok input, $15/MTok output
- Anthropic Claude Opus 4: $15/MTok input, $75/MTok output
- Groq Llama models: $0.05/MTok input, $0.08/MTok output (approximate)
"""

from dataclasses import dataclass


@dataclass
class ModelPricing:
    """Pricing per million tokens."""
    input_per_mtok: float
    output_per_mtok: float


# Pricing table (per million tokens)
PRICING: dict[str, ModelPricing] = {
    # Anthropic models
    "claude-sonnet-4-5-20250929": ModelPricing(3.0, 15.0),
    "claude-4-5-sonnet": ModelPricing(3.0, 15.0),
    "claude-opus-4-5-20250929": ModelPricing(15.0, 75.0),
    "claude-4-5-opus": ModelPricing(15.0, 75.0),
    # Groq models (approximate)
    "meta-llama/llama-4-maverick-17b-128e-instruct": ModelPricing(0.05, 0.08),
    "meta-llama/llama-4-scout-17b-16e-instruct": ModelPricing(0.05, 0.08),
    # Default fallback
    "default": ModelPricing(3.0, 15.0),
}


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str = "default",
) -> float:
    """
    Calculate estimated cost in USD for LLM usage.
    
    Args:
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens generated
        model: Model identifier for pricing lookup
        
    Returns:
        Estimated cost in USD
    """
    pricing = PRICING.get(model, PRICING["default"])
    
    # Convert to millions
    input_mtok = input_tokens / 1_000_000
    output_mtok = output_tokens / 1_000_000
    
    cost = (input_mtok * pricing.input_per_mtok) + (output_mtok * pricing.output_per_mtok)
    
    return round(cost, 6)  # Round to 6 decimal places (micro-dollars)


def format_cost(cost_usd: float) -> str:
    """Format cost for display."""
    if cost_usd < 0.01:
        return f"${cost_usd:.4f}"
    elif cost_usd < 1.0:
        return f"${cost_usd:.3f}"
    else:
        return f"${cost_usd:.2f}"
