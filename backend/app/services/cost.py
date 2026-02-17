"""
Cost calculation for LLM API usage.

Pricing as of February 2026 (update as needed):
- Anthropic Claude Sonnet 4.5: $3/MTok input, $15/MTok output
- Anthropic Claude Opus 4.5: $15/MTok input, $75/MTok output
- Anthropic Claude Haiku 4.5: $1/MTok input, $5/MTok output

Note: Prompt caching pricing is not yet accounted for.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
    "claude-haiku-4-5-20251001": ModelPricing(1.0, 5.0),
    "claude-4-5-haiku": ModelPricing(1.0, 5.0),
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
    pricing = PRICING.get(model)
    if pricing is None:
        logger.warning("No pricing found for model %r, using default (Sonnet) rates", model)
        pricing = PRICING["default"]
    
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
