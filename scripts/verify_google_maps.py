"""Google Maps Routes API 真实调用验证脚本。

用途：在配置了 GOOGLE_MAPS_API_KEY 后，验证真实 API 调用、新加坡地点解析、
公交/驾车模式映射、响应字段转换是否正常。

用法（在项目根目录，已激活 venv）：
    python scripts/verify_google_maps.py

脚本只做验证，不写入任何业务数据。未配置 Key 时会明确提示并退出。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp_servers")))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from shared.google_maps_service import GoogleMapsRoutesService


def main() -> None:
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        print("[跳过] 未配置 GOOGLE_MAPS_API_KEY，无法进行真实调用验证。")
        print("       请在项目根目录 .env 中填写 GOOGLE_MAPS_API_KEY 后重新运行。")
        return

    svc = GoogleMapsRoutesService(api_key=api_key)

    print("=== 1. 公交路线（transit）===")
    r = svc.get_routes("Jurong East", "Marina Bay", "transit")
    _print_result(r)

    print("\n=== 2. 驾车路线（driving）===")
    r2 = svc.get_routes("Jurong East", "Marina Bay", "driving")
    _print_result(r2)

    print("\n=== 3. 中文地名解析（transit）===")
    r3 = svc.get_routes("裕廊东", "滨海湾", "transit")
    _print_result(r3)


def _print_result(r) -> None:
    print(f"  status : {r.get('status')}")
    print(f"  source : {r.get('source')}")
    print(f"  error  : {r.get('error') or '(无)'}")
    data = r.get("data") or {}
    routes = data.get("routes", [])
    print(f"  路线数 : {len(routes)}")
    for rt in routes:
        print(
            f"    - {rt.get('summary')} | 耗时 {rt.get('duration_min')}min "
            f"| 费用 S${rt.get('fare_sgd')} | 步行 {rt.get('walk_distance_m')}m "
            f"| 换乘 {rt.get('transfers')}"
        )


if __name__ == "__main__":
    main()
