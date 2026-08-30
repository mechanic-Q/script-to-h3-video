#!/usr/bin/env python3
"""director_llm.py — 用 LLM（9router）做全篇+逐段的视觉导演设计。

两阶段（用户要求：既是分开的，又是整体的一部分）：
  阶段A 全篇视觉把控：LLM 通读所有段台词 → 产出整体视觉方案
    （视觉主线 / 场景系统 / 重复母题 / 色彩节奏 / 节奏曲线 / 段间衔接原则）
  阶段B 逐段创意设计：每段基于整体方案 + 本段台词（含节奏意图/信息点/景别）
    → 独立视觉导演设计（环境 / 主体 / 镜头 / 动作时间轴 / 风格渗透）

用法：
  director_llm.py <enhanced.json> --out-dir <输出目录> [--model low] [--only-scenes]
    --only-scenes 只做逐段（跳过整体方案，用于续跑）
输出：
  整体方案: <out>/00_整体视觉方案.md
  逐段:     <out>/shotXX.md
"""
import json, os, sys, argparse, urllib.request, time, re

# 流水线契约：环节间只传文件（强制）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline_contract as pc

API = "http://localhost:20128/v1/chat/completions"

SYSTEM_SHOT = """你是资深影视视觉导演，专长"赛博朋克太空工业"（cyberpunk space industrial）风格的短片视觉设计。

对每段中文口播台词，你要做完整的视觉导演设计（中文输出），包含以下部分：

【场景】这一段发生的环境（赛博朋克化的什么空间，要有具体场景感，不能抽象）
【主体】画面核心物体/元素（霓虹机械造型的什么，与台词内容直接相关）
【镜头】景别 + 运镜方式（节奏意图决定：铺垫=缓慢推近/远景、建立=平稳横移/全景、预备=轻微推进/中景、冲击=快速推近/特写、制动=缓慢拉远/中景、稳定=静止微移/全景）
【画质】本段画面质感三件套：光质锚定词 1 个 + 材质词 1 个 + 景深/镜头词 1 个（按风格从 quality-modifiers 决策表选；如"侧光+旧化金属+浅景深"；禁止堆砌形容词，动词名词优先）
【动作时间轴】按段时长分 3 段（0-1/3、1/3-2/3、2/3-1），每段一个明确的机械动作，与台词语义呼应
【风格渗透】本段如何延续赛博朋克太空工业风（霓虹/金属/全息），并点出与前段/后段的视觉衔接

硬性要求：
1. 每段设计必须**与台词内容强相关**——台词讲什么，画面就演什么（数字、专有名词、因果都要有赛博朋克对应物）
2. 必须**有创意**：每段的场景/主体/动作要不同，不能套用相同模板；同一场景系统内的段落要有递进或变化
3. 赛博朋克太空工业风：**霓虹光污染城市天际线（雨夜街巷霓虹招牌、全息广告）、金属机械表面（铆接钢板、管线、液压机构）、信息界面（全息控制台、数据流、轨道图、雷达屏）**，硬朗几何轮廓、冷调高对比（青/品红灯光）、象征符号化（火箭剪影、轨道线、卫星阵列、控制中心大屏）
4. 画面内无人声（口播是旁白）：不要设计"人物说话"
5. 输出中文，200-300 字，直接给设计内容，不要解释过程"""

SYSTEM_DIRECTIONS = """你是资深影视视觉导演，负责一部 AI 视频短片的**整体视觉方向提案**。

以下是整部分镜清单（每段的台词、节奏意图、信息点）。请通读后，给出 **3 个不同的整体视觉方案方向**（中文），每个方向必须：
1. 有清晰的视觉主线（用什么视觉线索贯穿全片）
2. 有明确的美术风格关键词（色调/质感/象征符号系统）
3. 说明这个方向最擅长表达什么情绪/主题
4. 说明风险或局限（什么内容这个方向表达不好）

输出格式（严格按此结构，不要解释过程）：

## 方向一：<方向名>
【视觉主线】...
【美术风格】...
【最适合表达】...
【局限】...

## 方向二：<方向名>
...

## 方向三：<方向名>
...
"""

SYSTEM_OVERALL = """你是资深影视视觉导演，负责一部 AI 视频短片的**全篇视觉把控**。

以下是整部分镜清单（每段的台词、节奏意图、信息点）。请通读后输出整体视觉方案（中文）：

【视觉主线】全篇用什么视觉线索贯穿（如：一枚"太空摆渡车"上面级从装配车间到轨道投送的命运；或一座发射台从霓虹夜景到深空轨道） 
【场景系统】设计 3-5 个核心场景（如：赛博朋克发射基地夜景/火箭装配车间/轨道控制大厅/深空轨道霓虹景象），说明每个场景在哪些段落出现、如何演进
【重复母题】1-2 个反复出现的机械母题（如：上面级发动机点火/全息轨道投送图/卫星阵列），作为视觉记忆点
【色彩节奏】全篇色彩如何变化（开场/中段/高潮/结尾的色调走向——从冷青蓝霓虹到高饱和火红到深空靛蓝）
【画面质感基调】全篇的画面质感基线：光质（柔光/硬光/霓虹/丁达尔）、颗粒与胶片感（是否加 film grain 去 AI 味）、景深策略（浅景深聚焦 or 全景深交代）、材质语言（金属/玻璃/织物/纸张），从 quality-modifiers 决策表按本片风格选
【节奏曲线】全篇节奏意图（铺垫/建立/预备/冲击/制动/稳定）的分布规律，说明视觉上如何配合
【段间衔接】相邻段之间视觉如何衔接（动作连续/场景切换/母题延续），保证"既是分开的又是整体的一部分"

硬性要求：
1. 全篇 6 段是一个完整叙事（太空摆渡车要来了→网友疑问→它干嘛的→三件事→5211秒试车→民营航天同台），视觉必须有整体演进
2. 赛博朋克太空工业风：**霓虹光污染城市天际线（雨夜街巷霓虹招牌、全息广告）、金属机械表面（铆接钢板、管线、液压机构）、信息界面（全息控制台、数据流、轨道图、雷达屏）**，硬朗几何轮廓、冷调高对比（青/品红灯光）、象征符号化（火箭剪影、轨道线、卫星阵列、控制中心大屏）
3. 输出中文，400-600 字，直接给方案，不要解释过程"""


def llm_call(messages, model, max_tokens=800, timeout=120, retries=2):
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.85,
        "max_tokens": max_tokens,
        "thinking": {"type": "disabled"},  # 请求级关闭 thinking，不影响 9router 全局
    }).encode()
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(API, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode()
            if "data: [DONE]" in raw:
                raw = raw[:raw.find("data: [DONE]")].strip()
            resp = json.loads(raw)
            msg = resp["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content") or ""
            # deepseek-v4-flash: 正文常落在 reasoning 尾部（content 被截断）
            if len(content.strip()) < 60:
                reasoning = msg.get("reasoning") or ""
                # 1) Draft/最终块后的设计正文
                m = re.search(r"(?:Draft\s*\d*[:：]?\s*\n?)((?:【场景】|场景[:：]|【环境】)[\s\S]*)$", reasoning, re.MULTILINE)
                if m:
                    content = m.group(1)
                else:
                    # 2) 最后一个 【场景】 块
                    matches = list(re.finditer(r"【场景】", reasoning))
                    if matches:
                        content = reasoning[matches[-1].start():]
                    else:
                        # 3) 退化：最后一个 '场景' 起
                        idx = reasoning.rfind("场景")
                        if idx != -1:
                            content = reasoning[idx:]
            return content.strip()
        except Exception as e:
            if attempt == retries:
                return f"ERROR: {e}"
            time.sleep(3)


def shot_prompt(shot):
    return (
        f"段号：{shot['id']}\n"
        f"台词：{shot['text']}\n"
        f"节奏意图：{shot.get('节奏意图', '建立')}\n"
        f"信息点：{shot.get('info_point', '')}\n"
        f"预计时长：{shot.get('duration_est', shot.get('est_seconds', 10))} 秒\n\n"
        f"请为这段设计完整的视觉导演方案。"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("enhanced_json")
    ap.add_argument("--out-dir", default="04_风格化文案")
    ap.add_argument("--model", default="low")
    ap.add_argument("--only-scenes", action="store_true", help="跳过整体方案（续跑）")
    ap.add_argument("--directions", action="store_true", help="阶段A前出3个创意方向供用户选")
    ap.add_argument("--selected-direction", default=None, help="指定选定的方向名（配合--directions使用后手动传入）")
    ap.add_argument("--max-shots", type=int, default=9999)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # 流水线契约：上游（阶段二分镜增强）必须已落盘
    pc.check_input(args.enhanced_json, "阶段二分镜增强产物")

    shots = json.load(open(args.enhanced_json, encoding="utf-8"))
    shots = [s for s in shots if int(s["id"][4:]) <= args.max_shots]
    print(f"共 {len(shots)} 段")

    # 阶段A-前置：创意方向卡（出 2-3 个方向供用户选）
    directions_file = os.path.join(args.out_dir, "00_创意方向卡.md")
    if args.directions and not os.path.exists(directions_file):
        summary = "\n".join(
            f"[{s['id']}] {s['text'][:50]}...（节奏:{s.get('节奏意图','建立')}）"
            for s in shots
        )
        print("[阶段A-前置] LLM 生成 3 个创意方向...")
        directions = llm_call(
            [{"role": "system", "content": SYSTEM_DIRECTIONS},
             {"role": "user", "content": f"分镜清单（共 {len(shots)} 段）：\n\n{summary}"}],
            args.model, max_tokens=1200, timeout=180)
        if not directions.startswith("ERROR"):
            with open(directions_file, "w", encoding="utf-8") as f:
                f.write("# 创意方向卡（3 选 1）\n\n" + directions + "\n\n---\n请选择一个方向（回复“方向一/二/三”或方向名），选定后将据此出整体视觉方案。\n")
            print(f"[阶段A-前置] → {directions_file}")
            print("请用户选择方向后，用 --selected-direction '<方向名>' 重新运行")
            return  # 等用户选方向
        else:
            print(f"[阶段A-前置] FAIL: {directions}，跳过直接出方案")

    # 阶段A：整体视觉方案（只跑一次）
    overall_file = os.path.join(args.out_dir, "00_整体视觉方案.md")
    if not args.only_scenes and not os.path.exists(overall_file):
        summary = "\n".join(
            f"[{s['id']}] {s['text'][:50]}...（节奏:{s.get('节奏意图','建立')}）"
            for s in shots
        )
        print("[阶段A] LLM 生成整体视觉方案（118 段通读）...")
        direction_ctx = ""
        if args.selected_direction:
            direction_ctx = f"\n\n用户已选定创意方向：{args.selected_direction}\n请基于此方向出整体视觉方案。\n"
        elif os.path.exists(directions_file):
            direction_ctx = "\n\n参考已生成的创意方向卡（见 00_创意方向卡.md），自由选择最适合的方向出方案。\n"
        plan = llm_call(
            [{"role": "system", "content": SYSTEM_OVERALL},
             {"role": "user", "content": f"分镜清单（共 {len(shots)} 段）：\n\n{summary}{direction_ctx}"}],
            args.model, max_tokens=1000, timeout=180)
        if not plan.startswith("ERROR"):
            with open(overall_file, "w", encoding="utf-8") as f:
                f.write(f"# 全篇整体视觉方案（{len(shots)} 段）\n\n{plan}\n")
            print(f"[阶段A] → {overall_file}")
        else:
            print(f"[阶段A] FAIL: {plan}")
            plan = ""
    else:
        plan = open(overall_file, encoding="utf-8").read() if os.path.exists(overall_file) else ""
        print(f"[阶段A] 已有整体方案（{len(plan)} 字），跳过")

    # 阶段B：逐段导演设计
    done = set()
    for f in os.listdir(args.out_dir):
        m = re.match(r"shot(\d+)\.md", f)
        if m:
            done.add(f"shot{int(m.group(1)):02d}")

    print(f"[阶段B] 逐段设计：已完成 {len(done)}/{len(shots)}")
    for shot in shots:
        sid = shot["id"]
        out_fp = os.path.join(args.out_dir, f"{sid}.md")
        if sid in done:
            continue
        ctx = f"整体视觉方案（用于保持全篇一致）：\n{plan[:2000]}\n\n---\n" if plan else ""
        design = llm_call(
            [{"role": "system", "content": SYSTEM_SHOT},
             {"role": "user", "content": ctx + shot_prompt(shot)}],
            args.model, max_tokens=700, timeout=120)
        if design.startswith("ERROR"):
            print(f"[FAIL] {sid}: {design}")
            continue
        with open(out_fp, "w", encoding="utf-8") as f:
            f.write(f"# {sid}\n\n{design}\n")
        print(f"[OK] {sid}")
        time.sleep(1)  # 限速

    print(f"\n完成: {len(os.listdir(args.out_dir))} 个文件 → {args.out_dir}")

    # 流水线契约：产出落盘标记（供下游 director_to_h3_llm 确认）
    pc.stamp_output(args.out_dir, {"shots": len(shots)})


if __name__ == "__main__":
    main()
