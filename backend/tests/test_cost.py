"""Tests for cost calculation module."""

import pytest
from app.services.cost import calculate_cost, format_cost, PRICING


class TestCalculateCost:
    """Tests for calculate_cost function."""

    def test_zero_tokens(self):
        """Zero tokens should return zero cost."""
        assert calculate_cost(0, 0) == 0.0

    def test_sonnet_pricing(self):
        """Test cost calculation with Sonnet pricing ($3/MTok in, $15/MTok out)."""
        # 1M input tokens + 1M output tokens = $3 + $15 = $18
        cost = calculate_cost(1_000_000, 1_000_000, model="claude-sonnet-4-5-20250929")
        assert cost == 18.0

    def test_small_request(self):
        """Test typical small request (1000 in, 500 out)."""
        # 1000 input = 0.001 MTok * $3 = $0.003
        # 500 output = 0.0005 MTok * $15 = $0.0075
        # Total = $0.0105
        cost = calculate_cost(1000, 500, model="claude-sonnet-4-5-20250929")
        assert abs(cost - 0.0105) < 0.000001

    def test_typical_extraction(self):
        """Test typical label extraction (5000 in, 1000 out)."""
        # 5000 input = 0.005 MTok * $3 = $0.015
        # 1000 output = 0.001 MTok * $15 = $0.015
        # Total = $0.03
        cost = calculate_cost(5000, 1000, model="claude-sonnet-4-5-20250929")
        assert abs(cost - 0.03) < 0.000001

    def test_unknown_model_uses_default(self):
        """Unknown model should use default pricing."""
        cost_unknown = calculate_cost(1000, 500, model="unknown-model-xyz")
        cost_default = calculate_cost(1000, 500, model="default")
        assert cost_unknown == cost_default

    def test_haiku_cheaper_than_sonnet(self):
        """Haiku should be cheaper than Sonnet."""
        cost_sonnet = calculate_cost(10000, 2000, model="claude-sonnet-4-5-20250929")
        cost_haiku = calculate_cost(10000, 2000, model="claude-haiku-4-5-20251001")
        assert cost_haiku < cost_sonnet


class TestFormatCost:
    """Tests for format_cost function."""

    def test_micro_dollars(self):
        """Very small costs should show 4 decimal places."""
        assert format_cost(0.0001) == "$0.0001"
        assert format_cost(0.0099) == "$0.0099"

    def test_cents(self):
        """Costs under $1 should show 3 decimal places."""
        assert format_cost(0.015) == "$0.015"
        assert format_cost(0.999) == "$0.999"

    def test_dollars(self):
        """Costs $1+ should show 2 decimal places."""
        assert format_cost(1.0) == "$1.00"
        assert format_cost(18.50) == "$18.50"


class TestPricingTable:
    """Tests for pricing table completeness."""

    def test_has_default_pricing(self):
        """Pricing table should have default fallback."""
        assert "default" in PRICING

    def test_sonnet_in_table(self):
        """Claude Sonnet should be in pricing table."""
        assert "claude-sonnet-4-5-20250929" in PRICING

    def test_pricing_values_positive(self):
        """All pricing values should be positive."""
        for model, pricing in PRICING.items():
            assert pricing.input_per_mtok > 0, f"{model} input price should be positive"
            assert pricing.output_per_mtok > 0, f"{model} output price should be positive"
