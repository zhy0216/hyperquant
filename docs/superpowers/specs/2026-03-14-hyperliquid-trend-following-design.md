# Hyperliquid 多品种趋势跟踪量化策略 — 设计文档

## 概述

基于事件驱动架构的全自动量化交易系统，在 Hyperliquid 永续合约上执行多品种趋势跟踪策略。系统从 10+ 品种中筛选趋势最强的品种，使用综合技术指标评分，ATR 自适应仓位管理，1h-4h 中周期持仓。

**目标用户：** 小资金 (<$10K) 个人交易者
**运行模式：** 全自动 7x24
**部署路径：** 本地开发 → 云端生产

---

## 1. 系统架构

事件驱动架构，基于 Python asyncio，所有组件通过事件总线解耦通信。

```
┌─────────────────────────────────────────────────┐
│                  Event Bus (asyncio)             │
│          publish / subscribe 事件分发             │
└──────┬──────┬──────┬──────┬──────┬──────────────┘
       │      │      │      │      │
  ┌────▼──┐┌──▼───┐┌─▼────┐┌▼─────┐┌▼──────────┐
  │ Data  ││Signal││Order ││Risk  ││ Portfolio  │
  │Feeder ││Engine││Execut││Mgr   ││  Tracker   │
  └───────┘└──────┘└──────┘└──────┘└────────────┘
       │                                  │
  ┌────▼──────────────────────────────────▼──────┐
  │          Storage (SQLite)                     │
  │   K线缓存 · 交易记录 · 持仓状态 · 系统日志    │
  └──────────────────────────────────────────────┘
```

### 核心组件

- **Event Bus** — 基于 asyncio 的轻量事件总线，所有组件通过 publish/subscribe 通信，彼此不直接依赖
- **Data Feeder** — 从 Hyperliquid 拉取 K线和市场数据，发布 `MarketDataEvent`
- **Signal Engine** — 订阅市场数据，计算技术指标，发布 `SignalEvent`（含品种评分和方向）
- **Risk Manager** — 订阅信号，校验风控规则（最大持仓数、单品种敞口、总敞口），通过后发布 `OrderRequestEvent`
- **Order Executor** — 订阅订单请求，通过 Hyperliquid SDK 执行下单，发布 `OrderFilledEvent`
- **Portfolio Tracker** — 跟踪持仓状态、盈亏、止盈止损逻辑，发布 `CloseSignalEvent`

### 事件流

```
MarketData → Signal → OrderRequest → OrderFilled → PortfolioUpdate
                                                  → CloseSignal → OrderRequest → ...
```

---

## 2. 数据层

### 数据获取

- 使用 `hyperliquid-python-sdk` 的 WebSocket 订阅实时 K线数据（1h 为主周期，4h 为确认周期）
- 启动时拉取历史 K线（至少 200 根）用于指标预热
- 每隔 5 分钟拉取一次全品种 ticker 数据，用于品种筛选和流动性过滤

### 品种筛选

从 Hyperliquid 全品种列表中，按以下条件过滤：

- 24h 交易量 > 阈值（可配置，默认 $1M）
- 排除刚上线不足 7 天的新币

过滤后的品种池（约 10-30 个）进入信号计算。

### 数据存储（SQLite）

| 表 | 用途 |
|---|---|
| `candles` | K线缓存，避免重启后重新拉取全量历史 |
| `trades` | 每笔交易记录（入场/出场价格、数量、PnL） |
| `positions` | 当前持仓快照 |
| `events_log` | 关键事件日志，用于调试和复盘 |

### 事件定义

```python
@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: float   # Unix timestamp (ms)

@dataclass
class MarketDataEvent:
    symbol: str
    timeframe: str          # "1h" | "4h"
    candles: list[Candle]   # 最新 N 根 K线（OHLCV）
    timestamp: float

@dataclass
class OrderRequestEvent:
    symbol: str
    direction: str       # "long" | "short"
    action: str          # "open" | "close"
    size: float          # 仓位数量（币本位）
    order_type: str      # "limit" | "market"
    limit_price: float | None
    stop_loss: float
    take_profit: float
    reason: str          # 触发原因描述
    timestamp: float

@dataclass
class OrderFilledEvent:
    symbol: str
    direction: str
    action: str          # "open" | "close"
    filled_size: float
    filled_price: float
    order_id: str
    fee: float
    timestamp: float

@dataclass
class PortfolioUpdateEvent:
    symbol: str
    unrealized_pnl: float
    current_price: float
    stop_loss: float     # 当前生效的止损价（可能已被移动止损更新）
    take_profit: float
    timestamp: float

@dataclass
class CloseSignalEvent:
    symbol: str
    reason: str          # "stop_loss" | "take_profit" | "trailing_stop" | "trend_reversal"
    close_price: float
    timestamp: float
```

---

## 3. 信号引擎

### 趋势评分体系

对每个品种计算综合趋势评分（0-100），分为三个维度：

| 维度 | 指标 | 权重 | 逻辑 |
|---|---|---|---|
| 趋势方向 | EMA(20) vs EMA(60) | 40% | 快线在慢线上方且间距扩大 → 高分 |
| 动量强度 | RSI(14) + MACD 柱状图 | 35% | RSI 50-70 区间 + MACD 柱放大 → 高分 |
| 突破确认 | Donchian Channel(20) | 25% | 价格突破通道上/下轨 → 加分确认 |

### 入场逻辑

1. 每根 1h K线收盘时，对品种池所有品种计算趋势评分
2. 用 4h 周期做方向过滤：只做与 4h 趋势方向一致的交易
3. 过滤：评分 > 阈值（可配置，默认 65）且该品种当前无持仓
4. 按评分降序排序，取前 `max_new_positions` 个（可配置，默认 3），受限于 `max_open_positions`（5）减去当前持仓数的剩余空位
5. 对符合条件的品种发出 `SignalEvent`

**反向信号处理：** 若某品种已有持仓，收到反向信号时，先发出 `CloseSignalEvent` 平仓，下一轮信号周期再评估是否开反向仓位。不在同一周期内反手。

### 信号定义

```python
@dataclass
class SignalEvent:
    symbol: str
    direction: str       # "long" | "short"
    score: float         # 0-100 趋势评分
    entry_price: float   # 当前价格
    atr: float           # 当前 ATR(14) 值
    stop_loss: float     # long: entry - 2*ATR, short: entry + 2*ATR
    take_profit: float   # long: entry + 3*ATR, short: entry - 3*ATR (reward:risk = 1.5:1)
    timestamp: float
```

### 出场逻辑

- **止损：** long: entry - 2×ATR, short: entry + 2×ATR
- **止盈：** long: entry + 3×ATR, short: entry - 3×ATR
- **移动止损（分三阶段）：**
  - 盈利 < 1×ATR：止损保持在初始位置不动
  - 盈利 1×ATR ~ 2×ATR：止损移动到入场价（保本），此后不再回退
  - 盈利 > 2×ATR：止损跟随价格移动，保持距最高盈利点 1.5×ATR 的距离（trailing stop）
- **趋势反转出场：** 评分跌破 30 或 EMA(20) 与 EMA(60) 交叉反转 → 平仓

---

## 4. 风控与仓位管理

### 仓位计算（ATR 自适应）

```
单笔风险金额 = 总资金 × 单笔风险比例（默认 2%）
仓位大小 = 单笔风险金额 / (2 × ATR)
实际杠杆 = 仓位名义价值 / 账户净值
```

示例：$10K 账户，BTC ATR=$1500，单笔风险 2%（$200）
→ 仓位 = $200 / $3000 = 0.067 BTC ≈ $4500 名义价值 → 约 0.45x 杠杆

### 风控规则

| 规则 | 限制 | 说明 |
|---|---|---|
| 单笔最大风险 | 总资金的 2% | 每笔交易最多亏损 2% |
| 最大同时持仓数 | 5 个品种 | 避免过度分散，小资金集中 |
| 单品种最大敞口 | 总资金的 20% | 防止单一品种过度集中 |
| 总敞口上限 | 总资金的 80% | 保留 20% 作为安全边际 |
| 最大杠杆 | 3x | 小资金也不过度加杠杆 |
| 日最大亏损 | 总资金的 5% | 触发后当日暂停开新仓（UTC 00:00 重置） |
| 连续亏损熔断 | 连亏 5 次 | 暂停交易 24h，等待人工确认 |

### 风控事件流

```
SignalEvent → RiskManager 校验:
  ├─ 通过 → 发布 OrderRequestEvent（含计算好的仓位大小）
  └─ 拒绝 → 记录日志，丢弃信号
```

---

## 5. 订单执行

- 使用 Hyperliquid SDK 的限价单，以对手价 ± 滑点容忍度（可配置，默认 0.1%）挂单
- 挂单后 30 秒未成交 → 取消并以市价成交（避免错过信号）
- **部分成交处理：** 限价单超时时若已部分成交，取消剩余部分，以市价补足到目标仓位
- 止盈止损通过 Hyperliquid 的 TP/SL 原生订单实现（交易所端执行，不依赖本地进程存活）
- 每次下单后发布 `OrderFilledEvent`，Portfolio Tracker 更新持仓
- **余额不足：** 如果计算出的仓位所需保证金超过可用余额，按可用余额的 90% 重新计算仓位大小；若仍不足最小下单量则跳过该信号

---

## 6. 容错与恢复

### WebSocket 重连

- 断线后立即尝试重连，使用指数退避（1s → 2s → 4s → ... 最大 60s）
- 重连成功后：重新订阅所有数据流，拉取断线期间缺失的 K线数据
- 若连续 5 分钟无法重连，发送 Telegram 告警

### 崩溃恢复（启动时）

1. 从 Hyperliquid API 拉取当前真实持仓，与本地 `positions` 表对比
2. 若发现不一致（如本地有记录但交易所无持仓），以交易所数据为准，更新本地状态
3. 检查是否有未完成的订单（pending orders），取消所有挂单后重新评估
4. 恢复指标计算状态（拉取足够的历史 K线重新计算）

### API 错误处理

- **Rate limit (429)：** 指数退避重试，最多 3 次，间隔 1s → 2s → 4s
- **Server error (5xx)：** 重试 3 次，若仍失败则跳过本次操作并记录日志
- **Network timeout：** 10 秒超时，重试 2 次
- 所有重试失败后发送 Telegram 告警，不阻塞主循环（跳过本周期）

### 通知服务降级

- Telegram 发送失败不影响交易逻辑，仅记录到本地日志
- 通知队列设上限（100 条），溢出时丢弃最旧的消息

---

## 7. 系统运行

### 运行循环

```
┌─ 启动 ──────────────────────────────────────┐
│  1. 加载配置 & 连接交易所                      │
│  2. 拉取历史K线，预热指标                      │
│  3. 同步当前持仓状态                           │
│  4. 启动 WebSocket 订阅                       │
├─ 运行循环 ──────────────────────────────────┤
│  · 每根 1h K线收盘 → 全量信号计算              │
│  · 实时监控持仓盈亏 → 移动止损更新             │
│  · 每 5 分钟 → 品种池刷新                     │
│  · 每 1 分钟 → 健康检查 & 持仓同步             │
└─────────────────────────────────────────────┘
```

### 配置管理

- 所有参数集中在 `config.yaml`，敏感信息通过环境变量或 `.env` 文件注入

```yaml
# config.yaml 完整示例
exchange:
  network: "mainnet"        # "mainnet" | "testnet"
  slippage_tolerance: 0.001 # 0.1% 滑点容忍
  order_timeout_sec: 30     # 限价单超时秒数

data:
  min_volume_24h: 1000000   # 品种最低 24h 交易量 ($)
  min_listing_days: 7       # 最短上线天数
  warmup_candles: 200       # 指标预热所需 K线数量
  pool_refresh_interval: 300 # 品种池刷新间隔（秒）

strategy:
  primary_timeframe: "1h"
  confirm_timeframe: "4h"
  score_threshold: 65       # 入场最低评分
  max_new_positions: 3      # 每轮最多新开仓数
  ema_fast: 20
  ema_slow: 60
  rsi_period: 14
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  donchian_period: 20
  atr_period: 14
  exit_score_threshold: 30  # 趋势反转出场评分

risk:
  risk_per_trade: 0.02      # 单笔风险 2%
  max_open_positions: 5
  max_single_exposure: 0.20 # 单品种最大敞口 20%
  max_total_exposure: 0.80  # 总敞口上限 80%
  max_leverage: 3.0
  max_daily_loss: 0.05      # 日最大亏损 5%（UTC 00:00 重置）
  consecutive_loss_limit: 5 # 连亏熔断次数
  cooldown_hours: 24        # 熔断冷却时间

stop_loss:
  initial_atr_multiple: 2.0
  take_profit_atr_multiple: 3.0
  breakeven_trigger_atr: 1.0
  trailing_trigger_atr: 2.0
  trailing_distance_atr: 1.5

notify:
  enabled: true
  daily_report_hour: 8     # UTC 时间

logging:
  level: "INFO"            # DEBUG | INFO | WARNING | ERROR
  file: "logs/hyperquant.log"
  max_size_mb: 50
  backup_count: 5
```

### 日志与监控

- 结构化日志（JSON 格式），分级别输出到文件和控制台
- 关键事件（开仓、平仓、风控触发、异常）通过 Telegram Bot 推送通知
- 每日自动生成交易报告（当日 PnL、持仓、信号统计）

### 部署

- **本地开发：** `python main.py` 运行，支持 `--dry-run` 模式（只生成信号不下单）
- **云端生产：** Docker 容器化，`docker-compose` 一键部署，systemd 或 supervisor 做进程守护

---

## 8. 项目结构

```
hyperquant/
├── config.yaml              # 策略参数配置
├── main.py                  # 入口，启动事件循环
├── core/
│   ├── event_bus.py         # 事件总线
│   └── events.py            # 事件类型定义
├── data/
│   ├── feeder.py            # 数据获取（K线、ticker）
│   └── store.py             # SQLite 存储层
├── strategy/
│   ├── indicators.py        # 技术指标计算
│   ├── scorer.py            # 趋势评分引擎
│   └── signal.py            # 信号生成逻辑
├── execution/
│   ├── risk.py              # 风控管理
│   ├── position.py          # 仓位计算
│   └── executor.py          # 订单执行
├── portfolio/
│   └── tracker.py           # 持仓跟踪、止盈止损
├── notify/
│   └── telegram.py          # Telegram 通知
├── utils/
│   └── logger.py            # 日志工具
├── tests/                   # 单元测试 & 回测
├── Dockerfile
├── docker-compose.yaml
└── requirements.txt
```

---

## 技术栈

- **语言：** Python 3.11+
- **异步：** asyncio
- **交易所接入：** hyperliquid-python-sdk
- **数据处理：** pandas, numpy
- **技术指标：** ta (Technical Analysis library)
- **存储：** SQLite (aiosqlite)
- **通知：** python-telegram-bot
- **部署：** Docker, docker-compose
- **日志：** structlog
