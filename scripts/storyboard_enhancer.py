#!/usr/bin/env python3
"""storyboard_enhancer.py — 分镜增强中间件：raw.json → enhanced.json + 六项自检。

每段增强 4 字段（3d 镜头表 + minimalist 节拍表借鉴）：
  duration_est : 字数÷4.5字/秒 + 0.5-1s 余量（上限 15s）
  节奏意图      : 铺垫/建立/预备/冲击/制动/稳定（minimalist 意图词）
  info_point    : 本段信息点（提炼关键词，供画面设计）
  shot_type     : 建议镜头类型（远景/中景/特写/运镜）

六项自检门（3d 自检门简化版）：
  ① 每段时长 ≤15s
  ② 每段有节奏意图（在意图词表内）
  ③ 相邻段风格锁一致（节奏意图连续：相邻段意图差异不超过 2 级）
  ④ 开场/收尾段有强钩子（信息点含"钩子/悬念/转折"或意图为 冲击/铺垫）
  ⑤ 每段有信息点
  ⑥ 每段有镜头类型（在镜头词表内）

用法：
  storyboard_enhancer.py <raw.json> <enhanced.json> [--out-report <report.json>]

输出：
  enhanced.json（每段 4 新字段）+ 自检报告（pass/fail + 失败项）。
"""
import json, os, sys, argparse

RHYTHM_INTENTS = ["铺垫", "建立", "预备", "冲击", "制动", "稳定"]
RHYTHM_LEVEL = {r: i for i, r in enumerate(RHYTHM_INTENTS)}
SHOT_TYPES = ["远景", "中景", "特写", "运镜", "全景", "过肩"]
CHAR_PER_SEC = 4.5  # 中文口播字速（用户实测）
PAD_SEC = 0.75      # 进出场余量（0.5-1s 取中）
MAX_SEC = 15.0

# 节奏意图启发式：按段落内容信号推断
HOOK_WORDS = ["钩子", "悬念", "转折", "爆点", "关键", "惊人", "突然", "崩溃", "致命", "最"]
CLIMAX_WORDS = ["终于", "成功", "突破", "完成", "实现", "没想到", "结果", "真相", "原因", "根因"]
SETUP_WORDS = ["首先", "先", "开始", "介绍", "背景", "这个", "我们"]
RESOLVE_WORDS = ["总结", "所以", "因此", "结论", "最后", "总之", "下次", "下期", "关注"]


def infer_rhythm(text, section, idx, total):
    """按内容信号 + 位置推断节奏意图。"""
    if idx == 0:
        return "铺垫"
    if idx == total - 1:
        return "稳定"
    # 结尾段（后 10%）通常制动/稳定
    if idx >= total - 2:
        if any(w in text for w in CLIMAX_WORDS):
            return "冲击"
        return "制动"
    if any(w in text for w in CLIMAX_WORDS):
        return "冲击"
    if any(w in text for w in RESOLVE_WORDS):
        return "制动"
    if any(w in text for w in SETUP_WORDS):
        return "建立"
    if any(w in text for w in HOOK_WORDS):
        return "预备"
    # 段落内容密度：长段（信息密集）→ 建立/预备；短段（强调）→ 冲击
    if len(text) <= 15:
        return "冲击"
    if len(text) >= 60:
        return "预备"
    return "建立"  # 默认


def infer_shot_type(text, chars):
    """按内容密度/长度推断镜头类型。"""
    if any(w in text for w in ["特写", "近景", "细节", "手", "屏幕", "表情", "崩溃", "黑屏"]):
        return "特写"
    if any(w in text for w in ["全景", "房间", "场景", "环境", "远景", "办公室", "工作台"]):
        return "全景"
    if chars <= 25:
        return "特写"  # 短句 = 强调，特写
    if chars >= 60:
        return "运镜"  # 长段 = 信息多，运镜
    return "中景"


def infer_info_point(text, section):
    """提炼信息点：取完整数字短语/关键实体（正则，避免截断）。"""
    import re
    points = []
    # 完整数字短语（含前后最多 8 字，尽量从词边界截）
    for n in re.findall(r"\d+(?:\.\d+)?", text):
        m = re.search(r"[\u4e00-\u9fffA-Za-z0-9]{0,8}" + re.escape(n) + r"[\u4e00-\u9fffA-Za-z0-9]{0,8}", text)
        if m:
            points.append(m.group(0).strip())
    if not points:
        # 取第一句完整句（到句号）
        first = text.split("。")[0]
        if len(first) > 20:
            first = first[:20]
        points.append(first)
    return "；".join(points[:3])


def main():
    ap = argparse.ArgumentParser(description="分镜增强中间件")
    ap.add_argument("raw_json", help="分镜清单_raw.json 路径")
    ap.add_argument("enhanced_json", help="输出增强版路径")
    ap.add_argument("--out-report", default=None, help="自检报告输出路径")
    args = ap.parse_args()

    if not os.path.exists(args.raw_json):
        print(f"ERROR: {args.raw_json} not found")
        sys.exit(2)

    sb = json.load(open(args.raw_json, encoding="utf-8"))
    if not isinstance(sb, list):
        print("ERROR: raw.json 应为列表")
        sys.exit(2)

    total = len(sb)
    enhanced = []
    for i, s in enumerate(sb):
        sid = s.get("id", f"shot{i+1:02d}")
        text = s.get("text", "")
        chars = s.get("chars", len(text))
        section = s.get("section", "")
        est = s.get("est_seconds")

        # duration_est：字数÷字速 + 余量，上限 15s
        dur = round(chars / CHAR_PER_SEC + PAD_SEC, 1)
        dur = min(dur, MAX_SEC)

        rhythm = infer_rhythm(text, section, i, total)
        info = infer_info_point(text, section)
        shot = infer_shot_type(text, chars)

        enhanced.append({
            **s,
            "duration_est": dur,
            "节奏意图": rhythm,
            "info_point": info,
            "shot_type": shot,
        })

    # 六项自检
    checks = []
    for i, e in enumerate(enhanced):
        eid = e["id"]
        # ① 时长 ≤15s
        checks.append(("①时长≤15s", eid, e["duration_est"] <= MAX_SEC,
                       f"{e['duration_est']}s"))
        # ② 节奏意图合法
        checks.append(("②节奏意图", eid, e["节奏意图"] in RHYTHM_INTENTS,
                       e["节奏意图"]))
        # ③ 相邻风格锁（意图差 ≤2 级）
        if i > 0:
            prev = enhanced[i - 1]["节奏意图"]
            diff = abs(RHYTHM_LEVEL[e["节奏意图"]] - RHYTHM_LEVEL[prev])
            checks.append(("③风格锁连续", eid, diff <= 2,
                           f"{prev}→{e['节奏意图']}"))
        # ④ 开场/收尾强钩子
        if i == 0 or i == total - 1:
            has_hook = e["节奏意图"] in ("铺垫", "冲击") or "钩子" in e.get("info_point", "")
            checks.append(("④开场/收尾钩子", eid, has_hook, e["节奏意图"]))
        # ⑤ 有信息点
        checks.append(("⑤信息点", eid, bool(e.get("info_point", "").strip()),
                       e.get("info_point", "")[:20]))
        # ⑥ 镜头类型合法
        checks.append(("⑥镜头类型", eid, e["shot_type"] in SHOT_TYPES,
                       e["shot_type"]))

    fails = [c for c in checks if not c[1]]
    report = {
        "total": total,
        "checks_total": len(checks),
        "pass": len(checks) - len(fails),
        "fail": len(fails),
        "failed_items": [{"check": c[0], "id": c[1], "detail": c[3]} for c in fails],
        "all_pass": len(fails) == 0,
    }

    with open(args.enhanced_json, "w", encoding="utf-8") as f:
        json.dump(enhanced, f, ensure_ascii=False, indent=2)
    if args.out_report:
        with open(args.out_report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"=== storyboard_enhancer 报告 ===")
    print(f"共 {total} 段 → {args.enhanced_json}")
    print(f"自检 {report['checks_total']} 项 | PASS {report['pass']} | FAIL {report['fail']}")
    if fails:
        for c in fails[:10]:
            print(f"  FAIL {c[0]} {c[1]}: {c[3]}")
    sys.exit(0 if report["all_pass"] else 1)


if __name__ == "__main__":
    main()
