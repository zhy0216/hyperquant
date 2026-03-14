import aiosqlite

from core.events import Candle, OrderFilledEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp REAL NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, timeframe, timestamp)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    action TEXT NOT NULL,
    filled_size REAL,
    filled_price REAL,
    order_id TEXT,
    fee REAL,
    timestamp REAL
);

CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY,
    direction TEXT NOT NULL,
    size REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    timestamp REAL
);

CREATE TABLE IF NOT EXISTS events_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    payload TEXT,
    timestamp REAL
);
"""


class Store:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    @property
    def _conn(self) -> aiosqlite.Connection:
        assert self._db is not None, "Store not initialized. Call initialize() first."
        return self._db

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        self._db.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # --- Candles ---

    async def save_candles(self, symbol: str, timeframe: str, candles: list[Candle]) -> None:
        await self._conn.executemany(
            """INSERT OR REPLACE INTO candles
               (symbol, timeframe, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (symbol, timeframe, c.timestamp, c.open, c.high, c.low, c.close, c.volume)
                for c in candles
            ],
        )
        await self._conn.commit()

    async def load_candles(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        cursor = await self._conn.execute(
            """SELECT open, high, low, close, volume, timestamp FROM (
                 SELECT open, high, low, close, volume, timestamp
                 FROM candles WHERE symbol = ? AND timeframe = ?
                 ORDER BY timestamp DESC LIMIT ?
               ) ORDER BY timestamp ASC""",
            (symbol, timeframe, limit),
        )
        rows = await cursor.fetchall()
        return [
            Candle(open=r[0], high=r[1], low=r[2], close=r[3], volume=r[4], timestamp=r[5])
            for r in rows
        ]

    # --- Trades ---

    async def record_trade(self, fill: OrderFilledEvent) -> None:
        await self._conn.execute(
            """INSERT INTO trades (symbol, direction, action, filled_size,
               filled_price, order_id, fee, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (fill.symbol, fill.direction, fill.action, fill.filled_size,
             fill.filled_price, fill.order_id, fill.fee, fill.timestamp),
        )
        await self._conn.commit()

    async def list_trades(self, symbol: str | None = None, limit: int = 50) -> list[dict]:
        if symbol:
            cursor = await self._conn.execute(
                "SELECT * FROM trades WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?",
                (symbol, limit),
            )
        else:
            cursor = await self._conn.execute(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # --- Positions ---

    async def save_position(self, pos: dict) -> None:
        await self._conn.execute(
            """INSERT OR REPLACE INTO positions
               (symbol, direction, size, entry_price, stop_loss, take_profit, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pos["symbol"], pos["direction"], pos["size"], pos["entry_price"],
             pos["stop_loss"], pos["take_profit"], pos["timestamp"]),
        )
        await self._conn.commit()

    async def remove_position(self, symbol: str) -> None:
        await self._conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
        await self._conn.commit()

    async def load_positions(self) -> list[dict]:
        cursor = await self._conn.execute("SELECT * FROM positions")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
