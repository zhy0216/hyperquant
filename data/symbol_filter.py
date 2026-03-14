import time


def filter_symbols(
    tickers: list[dict],
    min_volume: float,
    min_listing_days: int,
) -> list[dict]:
    now = time.time()
    min_listing_seconds = min_listing_days * 86400
    return [
        t for t in tickers
        if t["volume_24h"] >= min_volume
        and (now - t["listing_time"]) >= min_listing_seconds
    ]
