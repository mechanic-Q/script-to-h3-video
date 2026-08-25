#!/usr/bin/env python3
"""director_to_h3_llm.py — 导演设计 → H3 三字段 prompt（LLM 转换版）。

流程：读 04_风格化文案/shotXX.md → LLM 转英文三字段 → 校验约束 → 写回 06_H3prompt/shotXX.json

约束校验（写回前强制）：
  - 三字段齐全
  - off-screen voiceover + lips remain completely closed（无则自动插入）
  - non_diegetic_music: N/A
  - paper collage 风格标记（大小写不敏感）
  - POV 段（idx%5==0）要求第一人称描述

用法：director_to_h3_llm.py <设计目录> <输出目录> --start N --end M [--pov-ratio 0.2]
"""
import json, os, sys, re, time, argparse, urllib.request

API = "http://localhost:20128/v1/chat/completions"

SYSTEM = """你是 MiniMax H3 视频生成提示词专家。把中文视觉导演设计转成 H3 官方三字段英文 prompt。

必须遵守：
1. integrated_multimodal_description: 用英文详细描述画面（场景/主体/镜头/动作时间轴/材质风格），保留导演设计的全部创意细节和动作时间轴结构
2. overall_soundscape: 英文环境音描述（赛博朋克太空工业风：霓虹灯电流嗡鸣、雨落在金属棚顶、液压机械运转声、全息屏幕数据流嗡鸣、火箭点火低频轰鸣）
3. non_diegetic_music: N/A
4. 画面内无人声：结尾必须写 "The visuals play as off-screen voiceover narration while lips remain completely closed. No on-screen text, no subtitles, no captions."
5. POV 段（标记为第一人称）：开头写 "A first-person POV at a neon-lit control console, the narrator's own hands visible in frame operating holographic panels"，强调从叙述者视角看手部操作，无脸无全身
6. 非 POV 段：写 "No person appears in this shot"
7. 赛博朋克太空工业风：cyberpunk space industrial style, neon-drenched city skyline at night (rain-slick streets, neon signs, holographic billboards), metallic mechanical surfaces (riveted steel plates, pipes, hydraulic machinery), information interfaces (holographic consoles, data streams, orbital maps, radar screens), hard geometric outlines, cool high contrast (cyan and magenta lighting), symbolic elements (rocket silhouettes, orbital paths, satellite arrays, mission control big screens)
8. 输出严格三字段格式，字段间空一行"""

CONSTRAINT = ("The visuals play as off-screen voiceover narration while lips remain completely closed. "
              "No on-screen text, no subtitles, no captions.")


def llm_call(messages, max_tokens=900, timeout=120, retries=2):
    body = json.dumps({
        "model": "low",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": max_tokens,
        "thinking": {"type": "disabled"},
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
            # deepseek-v4-flash: 正文常落在 reasoning 尾部（content 截断） -> 取最后完整段
            if len(content.strip()) < 60:
                reasoning = msg.get("reasoning") or ""
                if "integrated_multimodal_description" in reasoning:
                    idx = reasoning.rfind("integrated_multimodal_description")
                else:
                    idx = reasoning.rfind("overall_soundscape")
                if idx != -1:
                    tail = reasoning[idx:]
                    # 截到 reasoning 的注释/补写噪音前（常见 "I'll output" / 中文说明）
                    for marker in ["\n\nI will", "\n\nI'll", "\n\nLet me", "```"]:
                        mi = tail.find(marker)
                        if mi != -1:
                            tail = tail[:mi]
                            break
                    if len(tail) > 100:
                        content = tail
            return content.strip()
        except Exception as e:
            if attempt == retries:
                return f"ERROR: {e}"
            time.sleep(3)


def enforce_constraints(prompt, is_pov):
    """校验 + 强制约束。返回 (修正后prompt, 问题列表)。"""
    issues = []
    p = prompt
    if "integrated_multimodal_description" not in p:
        issues.append("缺 imd 字段")
    if "overall_soundscape" not in p:
        issues.append("缺 soundscape 字段")
    if "non_diegetic_music: N/A" not in p:
        p = p.rstrip() + "\n\nnon_diegetic_music: N/A"
        issues.append("music 补 N/A")
    has_vo = "voiceover narration" in p and ("lips remain completely closed" in p or "lips remaining completely closed" in p)
    if not has_vo:
        p = p.replace("overall_soundscape:", f"{CONSTRAINT}\n\noverall_soundscape:")
        issues.append("补 off-screen 约束")
    if is_pov and "first-person pov" not in p.lower():
        issues.append("POV 段缺第一人称标记")
    if "cyberpunk" not in p.lower() and "neon" not in p.lower():
        issues.append("缺 cyberpunk 风格标记")
    return p, issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("design_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=9999)
    ap.add_argument("--pov-ratio", type=float, default=0.2)
    ap.add_argument("--durations", default=None, help="增强清单 json（补 video_seconds）")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    pov_interval = max(1, round(1 / args.pov_ratio)) if args.pov_ratio > 0 else 0

    durs = {}
    if args.durations:
        shots = json.load(open(args.durations, encoding="utf-8"))
        durs = {s["id"]: s.get("duration_est", s.get("est_seconds", 12)) for s in shots}

    done = 0
    for n in range(args.start, args.end + 1):
        sid = f"shot{n:02d}"
        md_fp = os.path.join(args.design_dir, f"{sid}.md")
        if not os.path.exists(md_fp):
            print(f"[MISS] {sid} 导演设计不存在")
            continue
        design = open(md_fp, encoding="utf-8").read()
        is_pov = (pov_interval > 0 and (n - 1) % pov_interval == 0)
        user = (f"导演设计（{'第一人称 POV 段' if is_pov else '第三人称场景段'}）：\n\n{design}\n\n"
                f"请转成 H3 三字段 prompt。")
        prompt = llm_call([{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": user}])
        if prompt.startswith("ERROR"):
            print(f"[FAIL] {sid}: {prompt}")
            continue
        prompt, issues = enforce_constraints(prompt, is_pov)
        rec = {
            "id": sid, "prompt": prompt,
            "video_seconds": durs.get(sid, 12),
            "mode": "pov" if is_pov else "t2v",
            "reference": None, "scene_source": "director_llm",
        }
        json.dump(rec, open(os.path.join(args.out_dir, f"{sid}.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        done += 1
        status = "OK" + (f"({len(issues)}修正)" if issues else "")
        print(f"[{status}] {sid} [{rec['mode']}] {len(prompt)}字")
        time.sleep(1)

    print(f"\n完成: {done} 段 → {args.out_dir}")


if __name__ == "__main__":
    main()
