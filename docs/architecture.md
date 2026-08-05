# SmartCommute AI 架构说明

## 1. 总体架构

```
┌─────────────┐     HTTP/JSON      ┌──────────────────────────────┐
│   React 前端 │ ─────────────────▶ │        FastAPI 后端           │
│  (Vite)     │                    │  ┌────────────────────────┐  │
└─────────────┘                    │  │   LangGraph 工作流      │  │
                                   │  │  (状态机 + Checkpointer) │  │
                                   │  └───────────┬────────────┘  │
                                   │              │ MCP Client     │
                                   │  ┌───────────┴────────────┐  │
                                   │  │  Mobility MCP Server    │  │
                                   │  │  Weather MCP Server     │  │
                                   │  └────────────────────────┘  │
                                   │  ┌────────────────────────┐  │
                                   │  │  SQLAlchemy (业务数据)  │  │
                                   │  └────────────────────────┘  │
                                   └──────────────────────────────┘
```

## 2. 数据流

1. 用户在前端输入自然语言 → `POST /api/chat`。
2. 后端将消息交给 LangGraph 工作流，携带 `thread_id`（= session_id）与已累积的 `commute_request`。
3. 工作流依次执行：
   - **parse_request**：规则解析出发地、目的地、时间、偏好、硬约束。
   - **check_missing**：检查必要字段，缺失则进入澄清分支。
   - **query_data**：通过 MCP Client 并行调用 Mobility 与 Weather 工具。
   - **normalize_data**：识别部分失败，收集错误。
   - **score**：确定性路线评分。
   - **generate_recommendation**：生成中文推荐 + 可解释理由。
4. 结果写回业务数据库（会话、消息、通勤计划、路线、工具日志），并返回前端。

## 3. MCP 设计

- 两个独立 MCP Server，通过 **stdio** 子进程方式由 MCP Client 连接。
- 每个工具返回统一结构：`status / data / source / queried_at / error`。
- Windows 下子进程强制 UTF-8（`PYTHONUTF8=1`）以正确处理中文参数。
- 数据源以适配器模式封装：`MobilityService` / `WeatherService` 抽象接口。
  - Mobility 路线：`GoogleMapsRoutesService`（真实，需 `GOOGLE_MAPS_API_KEY`）、`MockMobilityService`（演示）。
  - 交通事件：`LTATrafficService`（真实，需 `LTA_ACCOUNT_KEY`，与路线解耦）、`MockMobilityService`（演示）。
  - 天气：`OpenMeteoWeatherService`（真实，免费无需 Key，默认启用）、`MockWeatherService`（演示）。
  - Server 启动时根据环境变量自动选择数据源。

## 3.1 数据来源语义（source 汇总）

各数据源（路线 / 天气 / 交通事件）分别记录 `source`（来源名）与 `status`（ok/partial/error），后端在 `normalize_data` 阶段汇总为 `data_sources`，并计算整体状态 `overall`：

| overall | 含义 |
|---|---|
| `mock` | 全部为模拟数据（无真实源启用） |
| `live` | 全部为真实源且成功 |
| `degraded` | 混合状态（部分真实、部分模拟、部分失败） |
| `error` | 全部失败 |

原则：
- **绝不把混合数据源统一标记为「实时数据」**。
- **不凭"请求成功"就认定真实**：仅当 source 为真实来源名且 status=ok 才视为真实。
- 真实调用失败（status=error）既不冒充真实，也不冒充 mock，归入 `degraded` 或 `error`。
- 前端按维度展示各数据来源标签（路线/天气/交通事件各自真实/模拟/不可用）。

## 4. LLM 接入（DeepSeek）

- `LLMService` 抽象接口，两个实现：`DeepSeekLLMService`（真实）、`MockLLMService`（降级）。
- DeepSeek 通过 OpenAI 兼容接口调用，使用 `response_format=json_object` 做结构化需求解析。
- `parse_request` 节点优先调用 LLM 解析，失败/未配置时降级为确定性规则解析。
- `generate_recommendation` 节点优先调用 LLM 生成解释，失败时降级为模板。
- 调用失败时明确标记 `source`，绝不把降级结果冒充真实模型输出。

## 5. 路线评分

评分完全由确定性 Python 代码完成，维度与归一化策略：

| 指标 | 归一化 | 缺失策略 |
|---|---|---|
| 耗时 | 越小越好 | 中性 0.5 |
| 费用 | 越小越好 | 中性 0.5 |
| 步行距离 | 越小越好 | 中性 0.5 |
| 换乘次数 | 越小越好 | 中性 0.5 |
| 天气风险 | 低/中/高 → 0/0.5/1 | 默认 0 |
| 交通异常 | 严重程度映射 | 默认 0 |

- 权重可配置，并根据用户偏好微调后归一化。
- 硬约束（如 `max_transfers`、`max_walk_m`）优先，违反则标记不可行并降序排列。
- 输出 `score_detail` 支持逐项解释。

## 6. 数据持久化分层

| 存储 | 用途 |
|---|---|
| SQLAlchemy + SQLite | 用户、偏好、会话、消息、通勤计划、路线、工具日志 |
| LangGraph Checkpointer（SQLite，默认启用） | 工作流状态快照，按 `thread_id` 恢复 |

两者职责分离，Checkpointer 不作为业务数据库使用。

### Checkpointer 生命周期与 Windows 说明

- 使用 `AsyncSqliteSaver`（异步），通过 `CheckpointerManager` 管理创建与关闭。
- 在 FastAPI lifespan 的 shutdown 阶段关闭底层 aiosqlite 连接，保证优雅退出。
- `ainvoke` 时通过 `thread_id` 从 Checkpointer 读取上一轮的 `commute_request` 合并，实现真正的多轮会话。
- 之前曾误判为"aiosqlite 线程兼容问题"；实际根因是**连接未关闭**导致进程退出 SIGTERM，以及 config 缺少 `checkpoint_ns`。均已修复，SQLite 方案在 Windows 下稳定可用。

## 7. 错误处理与降级

- 外部 API 超时、限流、无结果、无权限均返回明确状态，不伪造数据。
- 单点数据缺失（如天气失败）不影响路线推荐主体。
- 无 API Key 时自动进入 Mock 模式，明确标记数据来源。
- 模型调用失败时降级为规则/模板，并标记 `source`，不冒充真实结果。
- 重试次数受控（`agent_max_retries`），避免无限循环。
