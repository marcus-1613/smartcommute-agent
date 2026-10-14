# SmartCommute AI 智慧通勤 Agent

一个面向新加坡通勤场景的全栈 AI Agent 应用。用户用自然语言描述通勤需求，系统通过 **LangGraph 状态化工作流 + MCP 工具 + 确定性路线评分** 完成需求解析、数据查询、路线比较与推荐，并在 Web 界面展示结果。

> 本项目为个人学习与工程能力展示项目，采用 **Mock 演示模式** 默认运行，未配置真实 API Key 时也能完整演示核心链路。

---

## 目录

- [核心功能](#核心功能)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [架构设计](#架构设计)
- [快速开始](#快速开始)
- [环境变量说明](#环境变量说明)
- [API Key 申请与配置](#api-key-申请与配置)
- [Mock 演示模式说明](#mock-演示模式说明)
- [运行测试](#运行测试)
- [MCP Server 单独启动与验证](#mcp-server-单独启动与验证)
- [Docker 部署](#docker-部署)
- [端到端演示步骤](#端到端演示步骤)
- [当前已知限制](#当前已知限制)
- [后续优化清单](#后续优化清单)

---

## 核心功能

### Agent（LangGraph）
- 状态化工作流：`解析需求 → 检查缺失字段 →（澄清 | 并行查询）→ 规范化 → 评分 → 推荐`
- 多轮对话：缺失信息时主动澄清，支持补充/修改（如"换一条少走路的路线"）
- 稳定 `thread_id`（等价 `session_id`）恢复会话，**SQLite Checkpointer 持久化**（服务重启后可恢复）
- 并行执行路线、天气、交通事件查询
- 重试与错误隔离：单点数据失败不影响整体流程
- **真实 DeepSeek 接入**：自然语言需求解析 + 推荐解释生成（未配置 Key 时自动降级规则解析）

### MCP（两个独立 Server）
- **Mobility MCP Server**：`search_place`、`get_routes`、`get_traffic_incidents`
- **Weather MCP Server**：`get_weather_forecast`、`check_weather_risk`
- 统一结构化输出：`status / data / source / queried_at / error`
- **可插拔数据源**：Mobility Server 根据 `GOOGLE_MAPS_API_KEY` 自动选择 Google Maps Routes API（真实）或 Mock（演示）

### 后端（FastAPI）
- `GET /api/health`、`POST /api/chat`、`GET /api/sessions`、`GET /api/sessions/{id}`、
  `GET /api/commutes`、`GET /api/commutes/{id}`、`GET/PUT /api/preferences`
- SQLAlchemy + SQLite（预留 PostgreSQL）
- 业务数据（用户、会话、消息、通勤计划、路线、工具调用日志）独立持久化

### 前端（React + TypeScript + Vite）
- 通勤助手聊天界面（含路线对比、评分明细、模拟数据标识）
- 历史会话 / 历史通勤计划
- 用户偏好设置

### 路线评分
- 纯确定性 Python 代码，支持硬约束与软偏好、权重归一化、缺失指标中性处理
- 输出可解释的评分明细

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+、FastAPI、LangGraph、LangChain、DeepSeek（OpenAI 兼容）、Pydantic、SQLAlchemy |
| MCP | 官方 `mcp` Python SDK（FastMCP） |
| 前端 | React 18、TypeScript、Vite |
| 数据库 | SQLite（默认）/ PostgreSQL（预留） |
| 测试 | pytest |
| 部署 | Docker、Docker Compose |

---

## 项目结构

```
SmartCommute-Agent/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口
│   │   ├── config.py          # 配置（pydantic-settings）
│   │   ├── api/               # 路由：chat/sessions/commutes/preferences
│   │   ├── agent/             # LangGraph 工作流（graph/state/checkpointer）
│   │   ├── services/          # MCP client、路线评分
│   │   ├── schemas/           # Pydantic 请求/响应模型
│   │   ├── models/            # SQLAlchemy 实体与数据库
│   │   └── repositories/      # 数据访问层
│   ├── requirements.txt
│   └── Dockerfile
├── mcp_servers/
│   ├── mobility_server.py     # Mobility MCP Server
│   ├── weather_server.py      # Weather MCP Server
│   └── shared/                # 共享服务、Mock 实现、新加坡静态数据
├── frontend/                  # React + TS + Vite
│   ├── src/
│   ├── package.json
│   └── Dockerfile
├── tests/                     # pytest 测试
├── docs/                      # 架构与开发记录
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## 架构设计

```
用户 ──> React 前端 ──> FastAPI 后端
                            │
                            ├──> LangGraph 工作流（状态机）
                            │       ├── 解析需求
                            │       ├── 澄清（缺失字段）
                            │       ├── 并行查询 ──> MCP Client ──> Mobility MCP / Weather MCP
                            │       ├── 规范化
                            │       ├── 路线评分（确定性）
                            │       └── 生成推荐
                            │
                            ├──> SQLAlchemy（业务数据）
                            └──> Checkpointer（SQLite 持久化，默认启用）
```

详细架构说明见 [docs/architecture.md](docs/architecture.md)。

---

## 快速开始

### 前置要求
- Python 3.11+
- Node.js 18+（推荐 20+）
- npm

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY 等（缺省时自动使用 Mock 模式）
```

### 2. 安装后端依赖

```bash
# Windows（建议）
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

pip install -r backend/requirements.txt
```

### 3. 启动后端

```bash
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload
```

后端默认运行在 `http://localhost:8000`，OpenAPI 文档见 `http://localhost:8000/docs`。

### 4. 安装并启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在 `http://localhost:5173`，已配置 `/api` 代理到后端。

---

## 环境变量说明

| 变量 | 作用 | 是否必填 |
|---|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API Key（理解自然语言/生成解释） | 否（缺省用规则解析） |
| `DEEPSEEK_BASE_URL` | DeepSeek 接口地址 | 否 |
| `DEEPSEEK_MODEL` | 模型名 | 否 |
| `GOOGLE_MAPS_API_KEY` | Google Maps Routes API Key | 否（缺省用 Mock） |
| `LTA_ACCOUNT_KEY` | 新加坡 LTA DataMall Key | 否 |
| `WEATHER_API_KEY` / `WEATHER_API_BASE_URL` | 天气 API | 否（缺省用 Mock） |
| `DATABASE_URL` | 数据库连接串 | 否（默认 SQLite） |
| `CORS_ORIGINS` | 允许跨域的前端地址 | 否 |
| `SMARTCOMMUTE_CHECKPOINT_PATH` | SQLite Checkpointer 文件路径 | 否（默认项目根 `smartcommute.checkpoint.sqlite`） |

> 所有真实 API Key 仅保存在后端 `.env`，不写入源码、前端或 Git。

---

## API Key 申请与配置

### DeepSeek
1. 访问 <https://platform.deepseek.com> 注册并创建 API Key。
2. 将 Key 填入 `.env` 的 `DEEPSEEK_API_KEY`。

### Google Maps Platform Routes API
1. 访问 <https://console.cloud.google.com> 启用 **Routes API** 并创建 API Key。
2. 将 Key 填入 `.env` 的 `GOOGLE_MAPS_API_KEY`。
3. 注意：Routes API 为付费服务，需注意配额与计费。
4. 配置后运行验证脚本，确认真实调用与字段转换：
   ```bash
   python scripts/verify_google_maps.py
   ```
   该脚本会依次验证公交（transit）、驾车（driving）路线，以及中文地名解析，并打印实际返回字段。未配置 Key 时会明确提示跳过，不会伪造成功。

### 新加坡 LTA DataMall（可选）
1. 访问 <https://datamall.lta.gov.sg> 注册并申请 Account Key。
2. 填入 `.env` 的 `LTA_ACCOUNT_KEY`。

### 天气 API（可选）
选择文档清晰、免费额度充足的天气服务，填入 `WEATHER_API_KEY` 与 `WEATHER_API_BASE_URL`。

> 本项目默认使用 Mock 模式，**不配置任何 Key 也能完整运行和演示**。

---

## Mock 演示模式说明

当未配置外部 API Key 时，系统自动使用 **Mock 演示模式**：

- 路线、天气、交通事件均由 `mcp_servers/shared/` 下的静态数据与规则生成。
- 所有 Mock 数据在响应中明确标记 `source: "mock"`，前端显示"模拟数据演示模式"标签。
- Mock 数据**绝不冒充实时数据**，仅用于保证项目可运行、可演示。

---

## 运行测试

```bash
# 全部测试
pytest -v

# 分类运行
pytest tests/test_route_scoring.py -v   # 路线评分确定性
pytest tests/test_mcp.py -v             # MCP 工具
pytest tests/test_api.py -v             # 后端 API
```

---

## MCP Server 单独启动与验证

两个 MCP Server 可独立启动（stdio 模式）：

```bash
# Mobility MCP Server
python mcp_servers/mobility_server.py

# Weather MCP Server
python mcp_servers/weather_server.py
```

验证工具暴露：

```bash
python -c "from mcp_servers.mobility_server import mcp; print([t.name for t in mcp._tool_manager.list_tools()])"
```

（项目已通过 MCP Client 的 stdio 连接验证了工具发现与调用。）

---

## Docker 部署

```bash
docker compose up --build
```

- 后端：`http://localhost:8000`
- 前端：`http://localhost`

---

## 端到端演示步骤

1. 启动后端与前端（见"快速开始"）。
2. 浏览器打开 `http://localhost:5173`。
3. 在通勤助手输入：
   > 我明天早上 8 点从 Jurong East 去 Marina Bay，希望尽量少换乘，最好不要走太多路。
4. 系统返回推荐路线 + 路线对比卡片（耗时/费用/步行/换乘）+ 评分明细 + 天气提示 + 模拟数据标识。
5. 测试澄清：输入"我想去滨海湾"，系统会提示补充出发地。
6. 测试修改：继续输入"换一条少走路的路线"，系统重新规划。
7. 在"历史记录"查看会话与通勤计划；在"用户偏好"调整偏好并保存。

---

## 当前已知限制

1. **DeepSeek 已接通**（本轮）：`DEEPSEEK_API_KEY` 已配置时，需求解析与推荐解释由真实 DeepSeek 生成；未配置时自动降级规则解析 + 模板。
2. **路线数据源**：`GOOGLE_MAPS_API_KEY` 未配置时使用 Mock 路线（明确标记 `source=mock`）；配置后自动切换 Google Maps Routes API 真实路线。**当前未配置 Google Key，真实路线尚未验证。**
3. **交通事件 / 天气**：仍为 Mock 数据。Google Routes API 本身不提供交通事件接口，LTA DataMall 与天气 API 的适配器尚未实现。
4. **地图展示**：未接入地图 UI，暂以路线列表 + 路线对比代替（符合需求"不要让地图功能阻塞核心交付"）。
5. **流式响应**：当前为稳定的普通请求-响应，未实现 SSE 流式。

---

## 后续优化清单

1. 配置 Google Maps API Key，验证新加坡地点、公交与驾车路线的真实返回，并接入地图展示。
2. 接入 LTA DataMall（交通事件）与天气 API 适配器。
3. 实现流式响应（SSE）提升交互体验。
4. 补充 PostgreSQL 部署验证与数据库迁移工具（Alembic）。
