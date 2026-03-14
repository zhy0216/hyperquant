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
class MarketDataEvent:
    symbol: str
    timeframe: str    # "1h" | "4h"
    candles: list     # 最新 N 根 K线
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
3. 按评分排序，选取前 N 个（可配置，默认 3-5 个）最强趋势品种
4. 评分 > 阈值（默认 65）且当前无持仓 → 发出 `SignalEvent`

### 信号定义

```python
@dataclass
class SignalEvent:
    symbol: str
    direction: str       # "long" | "short"
    score: float         # 0-100 趋势评分
    entry_price: float   # 当前价格
    atr: float           # 当前 ATR(14) 值
    stop_loss: float     # 入场价 ± 2*ATR
    take_profit: float   # 入场价 ± 3*ATR (1.5:1 盈亏比)
    timestamp: float
```

### 出场逻辑

- **止损：** 入场价 ± 2×ATR
- **止盈：** 入场价 ± 3×ATR
- **移动止损：** 盈利超过 1×ATR 后，止损移动到入场价（保本）；盈利超过 2×ATR 后，止损跟随价格移动（回撤 1.5×ATR 出场）
- **趋势反转出场：** 评分跌破 30 或 EMA 交叉反转 → 平仓

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
| 日最大亏损 | 总资金的 5% | 触发后当日暂停开新仓 |
| 连续亏损熔断 | 连亏 5 次 | 暂停交易 24h，等待人工确认 |

### 风控事件流

```
SignalEvent → RiskManager 校验:
  ├─ 通过 → 发布 OrderRequestEvent（含计算好的仓位大小）
  └─ 拒绝 → 记录日志，丢弃信号
```

---

## 5. 订单执行

- 使用 Hyperliquid SDK 的限价单，以对手价 ± 滑点容忍度挂单
- 挂单后 30 秒未成交 → 取消并以市价成交（避免错过信号）
- 止盈止损通过 Hyperliquid 的 TP/SL 原生订单实现（交易所端执行，不依赖本地进程存活）
- 每次下单后发布 `OrderFilledEvent`，Portfolio Tracker 更新持仓

---

## 6. 系统运行

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

- 所有参数（风控阈值、指标周期、品种过滤条件等）集中在 `config.yaml`
- 敏感信息（API Key/Secret）通过环境变量或 `.env` 文件注入，不进入代码仓库

### 日志与监控

- 结构化日志（JSON 格式），分级别输出到文件和控制台
- 关键事件（开仓、平仓、风控触发、异常）通过 Telegram Bot 推送通知
- 每日自动生成交易报告（当日 PnL、持仓、信号统计）

### 部署

- **本地开发：** `python main.py` 运行，支持 `--dry-run` 模式（只生成信号不下单）
- **云端生产：** Docker 容器化，`docker-compose` 一键部署，systemd 或 supervisor 做进程守护

---

## 7. 项目结构

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
