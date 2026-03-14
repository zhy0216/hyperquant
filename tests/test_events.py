from core.events import (
    Candle, MarketDataEvent, SignalEvent, OrderRequestEvent,
    OrderFilledEvent, PortfolioUpdateEvent, CloseSignalEvent,
)


def test_candle_creation():
    c = Candle(open=100.0, high=105.0, low=99.0, close=103.0, volume=1000.0, timestamp=1700000000000)
    assert c.close == 103.0
    assert c.timestamp == 1700000000000


def test_signal_event_fields():
    sig = SignalEvent(
        symbol="BTC", direction="long", score=78.5,
        entry_price=50000.0, atr=1500.0,
        stop_loss=47000.0, take_profit=54500.0,
        timestamp=1700000000000,
    )
    assert sig.direction == "long"
    assert sig.score == 78.5


def test_order_request_event_fields():
    ore = OrderRequestEvent(
        symbol="ETH", direction="short", action="open",
        size=1.5, order_type="limit", limit_price=3000.0,
        stop_loss=3300.0, take_profit=2550.0,
        reason="trend score 72", timestamp=1700000000000,
    )
    assert ore.action == "open"
    assert ore.limit_price == 3000.0


def test_market_data_event_with_candle_list():
    candles = [
        Candle(open=100, high=105, low=99, close=103, volume=1000, timestamp=1000),
        Candle(open=103, high=108, low=101, close=107, volume=1200, timestamp=2000),
    ]
    mde = MarketDataEvent(symbol="BTC", timeframe="1h", candles=candles, timestamp=3000)
    assert mde.symbol == "BTC"
    assert len(mde.candles) == 2
    assert mde.candles[0].close == 103


def test_order_filled_event_fields():
    ofe = OrderFilledEvent(
        symbol="ETH", direction="long", action="open",
        filled_size=1.5, filled_price=3000.0,
        order_id="ord_abc", fee=3.0, timestamp=1700000000000,
    )
    assert ofe.order_id == "ord_abc"
    assert ofe.fee == 3.0


def test_portfolio_update_event_fields():
    pue = PortfolioUpdateEvent(
        symbol="BTC", unrealized_pnl=500.0, current_price=50500.0,
        stop_loss=47000.0, take_profit=54500.0, timestamp=1700000000000,
    )
    assert pue.unrealized_pnl == 500.0


def test_order_request_with_none_limit_price():
    ore = OrderRequestEvent(
        symbol="ETH", direction="long", action="open",
        size=1.0, order_type="market", limit_price=None,
        stop_loss=2700.0, take_profit=3450.0,
        reason="market order", timestamp=1700000000000,
    )
    assert ore.limit_price is None


def test_close_signal_event_fields():
    cse = CloseSignalEvent(
        symbol="BTC", reason="trailing_stop",
        close_price=52000.0, timestamp=1700000000000,
    )
    assert cse.reason == "trailing_stop"
