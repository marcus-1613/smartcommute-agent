"""新加坡常见地点与交通数据（用于 Mock / 演示模式）。

此文件仅包含静态的、明确标记为模拟的数据，绝不冒充实时数据。
用于在未配置外部 API Key 时保证项目可运行、可演示。
"""
from __future__ import annotations

# 地点库：名称 -> (标准化名称, 类型, 大致坐标 [lat, lng])
# 坐标仅用于演示，非精确值。
PLACES: dict[str, tuple[str, str, list[float]]] = {
    "jurong east": ("裕廊东", "MRT Station", [1.3331, 103.7421]),
    "jurong east mrt": ("裕廊东", "MRT Station", [1.3331, 103.7421]),
    "jurong east station": ("裕廊东", "MRT Station", [1.3331, 103.7421]),
    "裕廊东": ("裕廊东", "MRT Station", [1.3331, 103.7421]),
    "marina bay": ("滨海湾", "MRT Station", [1.2764, 103.8545]),
    "marina bay mrt": ("滨海湾", "MRT Station", [1.2764, 103.8545]),
    "滨海湾": ("滨海湾", "MRT Station", [1.2764, 103.8545]),
    "orchard": ("乌节路", "Shopping", [1.3048, 103.8318]),
    "乌节路": ("乌节路", "Shopping", [1.3048, 103.8318]),
    "changi airport": ("樟宜机场", "Airport", [1.3644, 103.9915]),
    "樟宜机场": ("樟宜机场", "Airport", [1.3644, 103.9915]),
    "raffles place": ("莱佛士坊", "MRT Station", [1.2841, 103.8510]),
    "莱佛士坊": ("莱佛士坊", "MRT Station", [1.2841, 103.8510]),
    "city hall": ("政府大厦", "MRT Station", [1.2931, 103.8516]),
    "政府大厦": ("政府大厦", "MRT Station", [1.2931, 103.8516]),
    "woodlands": ("兀兰", "MRT Station", [1.4369, 103.7865]),
    "兀兰": ("兀兰", "MRT Station", [1.4369, 103.7865]),
    "tampines": ("淡滨尼", "MRT Station", [1.3530, 103.9450]),
    "淡滨尼": ("淡滨尼", "MRT Station", [1.3530, 103.9450]),
}

# 简化的线路走向数据，用于生成演示路线。
# 每条路线包含：模式、线路段、换乘点。
_MRT_LINES = {
    "东西线 (EWL)": ["裕廊东", "政府大厦", "莱佛士坊", "淡滨尼", "樟宜机场"],
    "南北线 (NSL)": ["兀兰", "政府大厦", "莱佛士坊", "滨海湾"],
    "环线 (CCL)": ["滨海湾", "政府大厦", "乌节路", "滨海湾"],
    "汤申-东海岸线 (TEL)": ["兀兰", "乌节路", "滨海湾", "淡滨尼"],
}

MRT_LINES = _MRT_LINES


def is_mock() -> bool:
    return True


MOCK_SOURCE = "mock"
