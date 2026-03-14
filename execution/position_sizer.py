def calculate_position_size(
    equity: float, atr: float, entry_price: float,
    risk_per_trade: float = 0.02, sl_atr_multiple: float = 2.0,
    max_single_exposure: float = 0.20, max_leverage: float = 3.0,
) -> dict:
    if atr <= 0 or entry_price <= 0 or equity <= 0:
        return {"size": 0, "notional": 0, "leverage": 0}
    risk_amount = equity * risk_per_trade
    size = risk_amount / (sl_atr_multiple * atr)
    notional = size * entry_price
    max_notional_exposure = equity * max_single_exposure
    if notional > max_notional_exposure:
        notional = max_notional_exposure
        size = notional / entry_price
    max_notional_leverage = equity * max_leverage
    if notional > max_notional_leverage:
        notional = max_notional_leverage
        size = notional / entry_price
    leverage = notional / equity
    return {"size": round(size, 6), "notional": round(notional, 2), "leverage": round(leverage, 4)}
