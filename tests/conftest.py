"""pytest 配置。"""
import os
import sys

# 测试默认使用 Mock 天气，避免依赖外部网络（Open-Meteo），保证测试确定性。
# 具体数据源实现通过单独的单测（直接实例化服务）验证。
os.environ.setdefault("WEATHER_PROVIDER", "mock")
os.environ.setdefault("GOOGLE_MAPS_API_KEY", "")
os.environ.setdefault("LTA_ACCOUNT_KEY", "")
os.environ.setdefault("DEEPSEEK_API_KEY", "")

# 测试使用独立数据库，避免污染项目根目录的演示数据（smartcommute.db）。
# 必须用 setdefault + 显式赋值：pydantic-settings 会读取 .env，但真实环境变量优先级更高。
os.environ["DATABASE_URL"] = "sqlite:///./test_smartcommute.db"
os.environ.setdefault("SMARTCOMMUTE_CHECKPOINT_PATH", "./test_smartcommute.checkpoint.sqlite")

# 将 backend 目录加入路径，便于导入 app 包
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# MCP servers 目录
MCP_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp_servers")
)
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)
