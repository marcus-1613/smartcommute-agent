"""对照实验：大模型排序 vs 确定性评分排序。

用途：
    为「LLM 只负责理解与表达、路线排序交给确定性代码」这条设计决策
    提供实测依据（见 docs/design-decisions.md 决策 1）。

    没有这个实验，那条决策只是"我觉得大模型排序不可靠"；
    有了它，才是"我测过，不可靠到什么程度"。

测两个维度：
    1. **稳定性**：同一输入重复调用 N 次，排序结果是否变化。
       确定性评分器理论上恒为 0 次（纯函数）；大模型即便 temperature=0
       也可能因为推理实现（MoE 路由、浮点累加顺序、批次效应）而非确定。
    2. **一致性**：大模型给出的排序，与确定性评分器的排序是否吻合。
       即使大模型输出稳定，它也可能稳定地给出另一个顺序——那说明
       它并不真正遵循我们定义的偏好模型。

关于调用参数：
    实验刻意复用 `DeepSeekLLMService._chat_json`，因为它是**生产代码里
    真实使用的调用路径**（temperature=0 + JSON 模式）。换成别的调用方式
    测出来的结论不能代表线上的行为。

用法：
    python scripts/experiment_llm_ranking.py                # 每场景 10 次
    python scripts/experiment_llm_ranking.py --runs 5
    python scripts/experiment_llm_ranking.py --scenarios 2  # 只跑前 2 个场景
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from app.services.llm_service import DeepSeekLLMService  # noqa: E402
from app.services.route_scoring import UserPreferences, score_routes  # noqa: E402


# ============================================================
# 实验数据：一组刻意构造出"真实取舍"的候选路线
# ============================================================
# 关键在于每条路线在不同维度上各有优劣，没有一条全面占优——
# 这样"排序"才是一个真正的判断题，而不是一眼可辨。

CANDIDATE_ROUTES = [
    {
        "id": "A",
        "summary": "公共交通（EW / NS）",
        "duration_min": 31.4,
        "fare_sgd": 2.07,
        "walk_distance_m": 38.5,
        "transfers": 1,
    },
    {
        "id": "B",
        "summary": "公共交通（NS 直达）",
        "duration_min": 45.2,
        "fare_sgd": 1.20,
        "walk_distance_m": 120.0,
        "transfers": 0,
    },
    {
        "id": "C",
        "summary": "公共交通（EW 换乘 2 次）",
        "duration_min": 26.1,
        "fare_sgd": 2.80,
        "walk_distance_m": 250.0,
        "transfers": 2,
    },
    {
        "id": "D",
        "summary": "公共交通（DT / NS）",
        "duration_min": 38.0,
        "fare_sgd": 1.75,
        "walk_distance_m": 80.0,
        "transfers": 1,
    },
]

# 场景：同一条用户需求，不同的偏好侧重
SCENARIOS = [
    (
        "少换乘优先",
        "我明天早上 8 点从裕廊东去滨海湾，特别怕换乘，希望能少换乘。",
        UserPreferences(prefer_fewer_transfers=0.9),
    ),
    (
        "少走路优先",
        "我明天早上 8 点从裕廊东去滨海湾，腿脚不太方便，希望尽量少走路。",
        UserPreferences(prefer_less_walking=0.9),
    ),
    (
        "省钱优先",
        "我明天早上 8 点从裕廊东去滨海湾，想尽量省钱，便宜一点比较好。",
        UserPreferences(prefer_lower_cost=0.9),
    ),
    (
        "求快优先",
        "我明天早上 8 点从裕廊东去滨海湾，赶时间，希望越快越好。",
        UserPreferences(prefer_shorter_time=0.9),
    ),
]


def deterministic_ranking(preferences: UserPreferences) -> list[str]:
    """用项目里的确定性评分器排序，返回路线 id 列表。"""
    scored = score_routes(list(CANDIDATE_ROUTES), preferences=preferences)
    return [item["route"]["id"] for item in scored]


def build_llm_prompt(user_text: str) -> str:
    """构造要求大模型排序的提示词（只给事实，不给评分规则）。"""
    lines = [
        "你是新加坡通勤助手。下面是从裕廊东到滨海湾的 4 条候选路线：",
        "",
    ]
    for route in CANDIDATE_ROUTES:
        lines.append(
            f"{route['id']}. {route['summary']}｜耗时 {route['duration_min']} 分钟"
            f"｜票价 S${route['fare_sgd']}｜步行 {route['walk_distance_m']} 米"
            f"｜换乘 {route['transfers']} 次"
        )
    lines += [
        "",
        f"用户的原话是：「{user_text}」",
        "",
        "请根据用户的偏好，把这 4 条路线从最推荐到最不推荐排序。",
        '只输出 JSON：{"ranking": ["路线id", ...], "reason": "一句话理由"}',
    ]
    return "\n".join(lines)


def llm_ranking(service: DeepSeekLLMService, user_text: str) -> list[str] | None:
    """调用大模型排序，返回路线 id 列表；失败返回 None。

    复用生产代码的 _chat_json：temperature=0 + JSON 模式，
    与线上实际调用路径一致。
    """
    prompt = build_llm_prompt(user_text)
    try:
        data = service._chat_json(
            [{"role": "user", "content": prompt}], max_tokens=300
        )
    except Exception as exc:  # noqa: BLE001
        print(f"    [警告] 调用失败：{type(exc).__name__}: {exc}")
        return None

    if not isinstance(data, dict):
        return None
    ranking = data.get("ranking")
    if not isinstance(ranking, list):
        return None
    valid_ids = {r["id"] for r in CANDIDATE_ROUTES}
    return [str(x) for x in ranking if str(x) in valid_ids]


def main() -> None:
    parser = argparse.ArgumentParser(description="大模型排序 vs 确定性排序 对照实验")
    parser.add_argument("--runs", type=int, default=10, help="每个场景重复次数")
    parser.add_argument("--scenarios", type=int, default=None, help="只跑前 N 个场景")
    args = parser.parse_args()

    if not os.getenv("DEEPSEEK_API_KEY"):
        print("未检测到 DEEPSEEK_API_KEY，无法调用大模型。请在 .env 中配置后重试。")
        sys.exit(1)

    service = DeepSeekLLMService()
    scenarios = SCENARIOS[: args.scenarios] if args.scenarios else SCENARIOS

    print("=" * 72)
    print(f"对照实验：大模型排序 vs 确定性评分排序（每场景 {args.runs} 次）")
    print(f"调用参数：temperature=0，JSON 模式（与生产代码一致）")
    print("=" * 72)

    total_det_changes = 0
    total_llm_changes = 0
    total_llm_failures = 0
    total_agree = 0
    total_compared = 0
    scenario_rows: list[tuple[str, str, str, int, int, float]] = []

    for name, user_text, prefs in scenarios:
        print(f"\n【场景：{name}】")
        print(f"  用户原话：{user_text}")

        # --- 确定性排序 ---
        det_results = [deterministic_ranking(prefs) for _ in range(args.runs)]
        det_reference = det_results[0]
        det_changes = sum(1 for r in det_results if r != det_reference)
        print(f"  确定性评分排序：{det_reference}")
        print(f"    重复 {args.runs} 次，排序变化 {det_changes} 次")

        # --- 大模型排序 ---
        llm_results: list[list[str]] = []
        for i in range(args.runs):
            result = llm_ranking(service, user_text)
            if result is None:
                total_llm_failures += 1
                continue
            llm_results.append(result)
            print(f"    第 {i + 1:>2} 次：{result}")

        if not llm_results:
            print("  大模型全部调用失败，跳过该场景")
            continue

        llm_reference = llm_results[0]
        llm_changes = sum(1 for r in llm_results if r != llm_reference)
        agree = sum(1 for r in llm_results if r == det_reference)
        top1_counter = Counter(r[0] for r in llm_results if r)

        print(f"  大模型排序：重复 {len(llm_results)} 次，"
              f"排序变化 {llm_changes} 次（{llm_changes / len(llm_results):.0%}）")
        print(f"  与确定性排序一致：{agree}/{len(llm_results)}"
              f"（{agree / len(llm_results):.0%}）")
        print(f"  大模型首推分布：{dict(top1_counter)}"
              f"（确定性首推：{det_reference[0]}）")

        total_det_changes += det_changes
        total_llm_changes += llm_changes
        total_agree += agree
        total_compared += len(llm_results)
        scenario_rows.append(
            (
                name,
                det_reference[0],
                llm_reference[0],
                llm_changes,
                len(llm_results),
                agree / len(llm_results),
            )
        )

    # ---------------- 汇总 ----------------
    print("\n" + "=" * 72)
    print("汇总")
    print("=" * 72)
    header = (
        f"{'场景':<14}{'确定性首推':>10}{'大模型首推':>12}"
        f"{'排序变化':>10}{'一致率':>10}"
    )
    print(header)
    print("-" * 72)
    for name, det_top, llm_top, changes, runs, agree_rate in scenario_rows:
        print(
            f"{name:<14}{det_top:>10}{llm_top:>12}"
            f"{changes:>6}/{runs:<5}{agree_rate:>9.0%}"
        )

    print()
    print(f"确定性排序总变化次数：{total_det_changes} / "
          f"{args.runs * len(scenario_rows)}（纯函数，恒为 0）")
    if total_compared:
        print(f"大模型排序总变化次数：{total_llm_changes} / {total_compared}"
              f"（{total_llm_changes / total_compared:.0%}）")
        print(f"大模型与确定性排序的总体一致率：{total_agree}/{total_compared}"
              f"（{total_agree / total_compared:.0%}）")
    if total_llm_failures:
        print(f"大模型调用失败次数：{total_llm_failures}")


if __name__ == "__main__":
    main()
