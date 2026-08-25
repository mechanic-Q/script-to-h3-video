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

API = "http://localhost:20128/v1/chat/completions"

SYSTEM_SHOT = """你是资深影视视觉导演，专长"复古纸质拼贴定格动画"（vintage handmade paper collage stop-motion）风格的短片视觉设计。画面是用纸、卡纸、牛皮纸手工剪贴搭建的立体纸艺场景，有毛糙手剪边缘、纸纹颗粒、硬边纸片投影，明确不是实拍、不是3D渲染、不是平面插画。

对每段中文口播台词，你要做完整的视觉导演设计（中文输出），包含以下部分：

【场景】这一段发生的环境（纸艺手工搭建的什么立体场景，要有具体场景感，不能抽象）
【主体】画面核心物体/元素（纸剪出来的什么造型，与台词内容直接相关）
【镜头】景别 + 运镜方式（节奏意图决定：铺垫=缓慢推近/远景、建立=平稳横移/全景、预备=轻微推进/中景、冲击=快速推近/特写、制动=缓慢拉远/中景、稳定=静止微移/全景）
【动作时间轴】按段时长分 3 段（0-1/3、1/3-2/3、2/3-1），每段一个明确的机械动作，与台词语义呼应
【风格渗透】本段如何延续复古纸质拼贴定格风（纸张纹理/手剪边缘/纸艺质感），并点出与前段/后段的视觉衔接

硬性要求：
1. 每段设计必须**与台词内容强相关**——台词讲什么，画面就演什么（数字、专有名词、因果都要有纸艺对应物）
2. 必须**有创意**：每段的场景/主体/动作要不同，不能套用相同模板；同一场景系统内的段落要有递进或变化
3. 复古纸质拼贴定格动画风：**做旧纸张/卡纸/牛皮纸材质、毛糙手剪边缘、硬边纸片投影、纸纹颗粒、剪刀/胶水/尺子等纸艺工具、桌面立体小场景（diorama）、定格动画逐帧手推动作**，暖色纸艺质感（旧纸黄/牛皮纸棕/少量高饱和点缀色）、象征符号化（纸剪加速器管道、纸折药瓶、纸拼贴原子轨道）
4. 画面内无人声（口播是旁白）：不要设计"人物说话"
5. 输出中文，200-300 字，直接给设计内容，不要解释过程"""

SYSTEM_OVERALL = """你是资深影视视觉导演，负责一部"复古纸质拼贴定格动画"（vintage handmade paper collage stop-motion）AI 视频短片的**全篇视觉把控**。

以下是整部分镜清单（每段的台词、节奏意图、信息点）。请通读后输出整体视觉方案（中文）：

【视觉主线】全篇用什么视觉线索贯穿（如：一枚"太空摆渡车"上面级从装配车间到轨道投送的命运；或一座发射台从霓虹夜景到深空轨道） 
【场景系统】设计 3-5 个核心纸艺场景（如：深夜书房纸艺工作台/纸板拼贴的加速器舱段/牛皮纸药瓶与纸剪原子轨道/档案馆旧报纸墙），说明每个场景在哪些段落出现、如何演进
【重复母题】1-2 个反复出现的纸艺母题（如：剪刀剪下原子轨道的动作/牛皮纸信封里倒出一枚纸剪同位素），作为视觉记忆点
【色彩节奏】全篇色彩如何变化（开场/中段/高潮/结尾的色调走向——从旧纸泛黄到牛皮纸棕到少量高饱和点缀色到结尾暖黄纸灯）
【节奏曲线】全篇节奏意图（铺垫/建立/预备/冲击/制动/稳定）的分布规律，说明视觉上如何配合
【段间衔接】相邻段之间视觉如何衔接（动作连续/场景切换/母题延续），保证"既是分开的又是整体的一部分"

硬性要求：
1. 全篇 6 段是一个完整叙事（太空摆渡车要来了→网友疑问→它干嘛的→三件事→5211秒试车→民营航天同台），视觉必须有整体演进
2. 复古纸质拼贴定格动画风：**做旧纸张/卡纸/牛皮纸材质、毛糙手剪边缘、硬边纸片投影、纸纹颗粒、剪刀/胶水/尺子等纸艺工具、桌面立体小场景（diorama）、定格动画逐帧手推动作**，暖色纸艺质感（旧纸黄/牛皮纸棕/少量高饱和点缀色）、象征符号化（纸剪加速器管道、纸折药瓶、纸拼贴原子轨道）
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
    ap.add_argument("--max-shots", type=int, default=9999)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    shots = json.load(open(args.enhanced_json, encoding="utf-8"))
    shots = [s for s in shots if int(s["id"][4:]) <= args.max_shots]
    print(f"共 {len(shots)} 段")

    # 阶段A：整体视觉方案（只跑一次）
    overall_file = os.path.join(args.out_dir, "00_整体视觉方案.md")
    if not args.only_scenes and not os.path.exists(overall_file):
        summary = "\n".join(
            f"[{s['id']}] {s['text'][:50]}...（节奏:{s.get('节奏意图','建立')}）"
            for s in shots
        )
        print("[阶段A] LLM 生成整体视觉方案（118 段通读）...")
        plan = llm_call(
            [{"role": "system", "content": SYSTEM_OVERALL},
             {"role": "user", "content": f"分镜清单（共 {len(shots)} 段）：\n\n{summary}"}],
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


if __name__ == "__main__":
    main()
