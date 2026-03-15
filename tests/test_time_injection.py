import pytest
from core.event_bus import EventBus
from execution.risk_manager import RiskManager


@pytest.fixture
def config():
    return {
        "risk": {
            "risk_per_trade": 0.02, "max_open_positions": 5,
            "max_single_exposure": 0.20, "max_total_exposure": 0.80,
            "max_leverage": 3.0, "max_daily_loss": 0.05,
            "consecutive_loss_limit": 5, "cooldown_hours": 24,
        },
        "stop_loss": {"initial_atr_multiple": 2.0, "take_profit_atr_multiple": 3.0},
    }


async def test_risk_manager_uses_injected_time(config: dict) -> None:
    bus = EventBus()
    fake_time = 1000000.0
    rm = RiskManager(bus=bus, config=config, equity=10000, time_fn=lambda: fake_time)

    # Trigger consecutive losses to activate cooldown
    for _ in range(5):
        rm.record_loss(100)

    # Cooldown should be at fake_time + 24*3600
    assert rm._cooldown_until == fake_time + 24 * 3600
