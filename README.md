# ForecastLab — 事件预测 Agent

一个交互式、前瞻、会自我进化的事件预测工具(MVP)。流程:

> **选盘 → Agent 分析 → 用户手动记假性押注 → 揭晓自动结算 → 复盘 → 写入 RAG 知识库让 Agent 进化**

Agent **只做分析**(概率 + 依据,无未来函数:分析都在揭晓前做出);**押注是用户手动行为**(手输方向/注码/入场价,纯纸面、不接支付);一个**带本金的虚拟账户**按当前市场价**盯市**跟踪持仓与盈亏。详见 [`预测agent_PRD_ForecastLab.md`](预测agent_PRD_ForecastLab.md)。

> ⚠️ 仅供研究与分析,非投资建议。无任何真实下单/交易/支付/钱包代码;押注与账户均为纸面记账。

---

## 依赖与配置(全部真实环境,无 mock)

| 能力 | 实现 | 配置 |
|---|---|---|
| 市场数据 | Polymarket **官方 API**(只读) | 无需 key;API 故障返回空,不伪造 |
| LLM(分析/复盘) | **DeepSeek `deepseek-v4-flash`**(默认)/ Anthropic | **必填** `DEEPSEEK_API_KEY`(或 `ANTHROPIC_API_KEY`) |
| 搜索 | **Tavily**(默认)/ Serper | **必填** `SEARCH_API_KEY`(Tavily 每月 1000 免费) |
| 嵌入(RAG) | 本地嵌入(免费,真实算法) | 可选 `sentence-transformers` / `voyage` 提质 |
| 虚拟账户 | 纸面记账(**唯一刻意保留的模拟部分**) | `STARTING_BALANCE_USD` |

无 LLM/搜索 key 时,分析会**报错而非伪造**(健康徽章标 ⚠)。揭晓只来自真实 Polymarket。

---

## 快速开始

### Docker(推荐,一条命令起两端)

```bash
cp .env.example .env          # 填 DEEPSEEK_API_KEY + SEARCH_API_KEY(真实环境必填)
docker compose up --build     # 前端 http://localhost:8080 · 后端 http://localhost:8000
```

前端容器内 nginx 把 `/api` 反代到 backend;SQLite/缓存持久化在 `fl_data` 卷。

### 后端(Python 3.11+,已在 3.14 验证)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1            # bash: source .venv/Scripts/activate
pip install -r requirements.txt
python scripts/reset.py               # 清空并拉取真实 Polymarket 盘子(随时可重跑)
uvicorn app.api:app --reload --port 8000
```

启动时会自动拉取 Polymarket 开放盘(可关:`AUTO_INGEST=0`),并启动后台轮询(盯市 + 揭晓)。

### 前端(Node 18+)

```powershell
cd frontend
npm install
npm run dev                           # http://localhost:5173(开发代理 /api → :8000)
```

### 配置真实 provider

把 `.env.example` 复制为 `.env`,填:
- `DEEPSEEK_API_KEY`(默认 `deepseek-v4-flash`,OpenAI 兼容 `/chat/completions`)——或 `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`
- `SEARCH_API_KEY`(默认 Tavily;[tavily.com](https://www.tavily.com/pricing) 每月 1000 免费额度)

`python scripts/reset.py` 随时清空并重新拉取真实盘子。DeepSeek V4 是推理模型,默认**关闭思考模式**(`DEEPSEEK_THINKING=0`)以稳定产出结构化 JSON。每次「分析」消耗真实额度,`MAX_SPEND_USD` 软上限兜底。

---

## 测试

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q   # 20 passed, 2 skipped:纯逻辑 + API,不调用真实 API
```

核心打分(Brier、盈亏、账户结算)是纯函数、零外部依赖,全部单测覆盖。默认测试**不花任何 key**;真实端到端用 `RUN_LIVE_TESTS=1 pytest tests/test_live.py`(需 key,会消耗额度)。

---

## API(节选)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/markets?status=open` | 浏览开放盘子 |
| POST | `/api/forecasts` `{market_id}` | 触发 Agent 分析(不押注) |
| GET | `/api/positions` | 统一列表:分析 + 押注 + 市场 |
| POST | `/api/bets` `{forecast_id, side, stake, entry_prob}` | **用户手动押注**(每个分析至多一笔,校验余额) |
| GET | `/api/account` · `/api/holdings` | 虚拟账户权益 / 当前持仓盯市 |
| POST | `/api/forecasts/{id}/review` | 「分析」按钮:生成复盘 → 写 RAG 知识库 |
| GET | `/api/eval/summary` | Agent vs 市场 Brier、校准、组合盈亏 |
| POST | `/api/poll` | 立即跑一次盯市 + 揭晓检查(揭晓来自 Polymarket) |

---

## 结构

```
backend/app/
  data/        Polymarket 客户端 + 拉取 + 后台轮询(盯市+揭晓)
  research/    query-gen → search → fetch → relevance → summarize(+KB 检索)
  forecast/    分类专属 agent(LangChain,按 category 路由)+ 集成 + 聚合;加密 agent 带 CoinGecko 实时价工具
  portfolio/   虚拟账户:开仓扣减、盯市、结算入账
  kb/          RAG:嵌入 + 向量库 + 复盘生成/检索
  eval/        Brier / P&L / 校准(纯函数 + 测试)
  providers/   LLM(DeepSeek/Anthropic)· Search(Tavily/Serper)· Embedding(本地/可选语义)
  lib/         models(pydantic)、db(sqlite)、cache、cost_tracker
frontend/src/  Vite+React+TS:盘子浏览 / 分析押注统一列表 / 虚拟组合 / 战绩评估
```

---

## Open Questions(留给维护者)

- **分类专属 agent(LangChain)**:`forecast/agents.py` 按 `market.category` 路由到领域 agent(加密/政治/体育/…),各有领域 system prompt + 工具。**加密 agent 带 CoinGecko 实时价工具**——它先取现价再对比盘子阈值,不再被过时文章价误导。后端经 `langchain-openai` 接 DeepSeek。要加新领域工具(政治民调、体育赔率)在 `agents.py` 里加 `@tool` 即可。RAG 仍是自封装向量库(`kb/store.py`),未用 LangChain 的检索抽象。
- **向量库 Chroma**:默认用内置 SQLite 向量表(余弦,零依赖)。语料变大或要持久化检索质量时,可在 `kb/store.py` 背后换 Chroma,接口不变。
- **嵌入质量**:默认本地哈希嵌入足够做相似复盘召回;要更强语义可装 `sentence-transformers` 并设 `EMBEDDING_PROVIDER`。
- **揭晓判定**:Polymarket 用 `closed` + 价格≈1/0 判定;UMA 争议/作废标 `void` 并退还押注。复杂结算(0.5、多段)未覆盖。
- **盯市价格质量**:冷门盘价差大,浮盈仅作参考、不可兑现(持仓页已注明)。
- **冷启动**:知识库空库起步,前几次分析无复盘可注入(优雅降级);随真实揭晓逐步进化。
- **成本**:默认按需选盘 + Haiku 过滤/摘要 + 全缓存;`MAX_SPEND_USD` 软上限超限即停。真实 forecaster 模型可在 `.env` 调(Opus/Sonnet 取舍)。

---

## 与 PRD 里程碑对应

P0 脚手架 · P1 数据接入+选盘 · P2 检索+集成预测+Forecast · P2.5 虚拟账户+手动押注 · P3 后台轮询(盯市+揭晓结算) · P4 复盘→RAG 知识库→检索注入(进化闭环) · P5 看板(战绩+组合) · P6 README/测试。M7(Metaculus)留作拉伸。
