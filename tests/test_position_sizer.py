import pytest

from execution.position_sizer import calculate_position_size


class TestPositionSizer:
    def test_basic_calculation(self):
        result = calculate_position_size(
            equity=10_000, atr=1500, entry_price=50_000,
            risk_per_trade=0.02, sl_atr_multiple=2.0,
            max_single_exposure=0.20, max_leverage=3.0,
        )
        # Uncapped size would be 200/(2*1500)=0.0667, but capped by max_single_exposure
        # max_notional = 10000*0.20 = 2000, so size = 2000/50000 = 0.04
        assert abs(result["size"] - 0.04) < 0.001
        assert result["notional"] == pytest.approx(result["size"] * 50_000, rel=0.01)

    def test_capped_by_max_single_exposure(self):
        result = calculate_position_size(
            equity=10_000, atr=1.0, entry_price=100,
            risk_per_trade=0.02, sl_atr_multiple=2.0,
            max_single_exposure=0.20, max_leverage=3.0,
        )
        assert result["notional"] <= 10_000 * 0.20

    def test_capped_by_max_leverage(self):
        result = calculate_position_size(
            equity=1_000, atr=0.5, entry_price=10,
            risk_per_trade=0.02, sl_atr_multiple=2.0,
            max_single_exposure=1.0, max_leverage=3.0,
        )
        assert result["notional"] <= 1_000 * 3.0

    def test_zero_atr_returns_zero(self):
        result = calculate_position_size(
            equity=10_000, atr=0, entry_price=50_000,
            risk_per_trade=0.02, sl_atr_multiple=2.0,
            max_single_exposure=0.20, max_leverage=3.0,
        )
        assert result["size"] == 0
