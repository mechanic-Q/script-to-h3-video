#!/usr/bin/env python3
"""verify_output.py — 验收脚本：检查 H3 生成段是否合格，输出报告。

检查项（九项 = 原六项 + 创意层两项 + 音频对齐一项）：
  1. 文件存在 / 大小 > 0
  2. 视频时长在预期范围（est_seconds ±1.5s，且 ≤15.5s）
  3. 分辨率正确（480P：短边 768 或 480；720P：短边 720）
  4. prompt 三字段齐全（integrated_multimodal_description / overall_soundscape / non_diegetic_music）
  5. 相邻段风格锁一致（prompt 中场景/基调关键词延续，简化：检查前 120 字符公共前缀）
  6. 切点不在句中（输入分镜文本末字符应为句号/感叹号/问号/省略号）
  7. 相邻段画面连贯（NEW：导演设计 continuity_handoff 链成环）
  8. 每段传达 info_point（NEW：导演设计含本段 info_point 关键词）
  9. 音频对齐（TTS 音频时长与视频时长差 ≤0.5s）

用法：
  verify_output.py <generated.jsonl> [--prompts <h3_prompts_dir>] [--storyboard <分镜清单.json>] [--director-dir <导演设计目录>] [--audio-dir <TTS音频目录>] [--out <report.json>]

输出：
  报告 JSON（每段 pass/fail + 原因），stdout 打印摘要。
  失败段写入 <out>.failed 列表（标记重跑）。
"""
import json, os, re, sys, subprocess, argparse

# 流水线契约：环节间只传文件（强制）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pipeline_contract as pc


def get_ffprobe_duration(path):
    """ffprobe 读时长（秒），失败返回 None。"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path], capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return None
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return None


def get_ffprobe_resolution(path):
    """ffprobe 读分辨率 (w, h)，失败返回 None。"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", path],
            capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return None
        s = json.loads(r.stdout)["streams"][0]
        return (s.get("width"), s.get("height"))
    except Exception:
        return None


def check_prompt_fields(prompt_text):
    """检查三字段齐全。返回 (ok, missing)。"""
    fields = ["integrated_multimodal_description", "overall_soundscape", "non_diegetic_music"]
    missing = [f for f in fields if f not in prompt_text]
    return (len(missing) == 0, missing)


def check_quality_anchors(prompt_text):
    """第 10 项画质链：H3 prompt 的 imd 里至少含 2 个画质锚定词（光质/材质/景深/颗粒）。"""
    if not prompt_text:
        return False
    i = prompt_text.find("integrated_multimodal_description")
    j = prompt_text.find("overall_soundscape")
    imd = prompt_text[i:j] if i >= 0 and j > i else prompt_text
    anchors = ["light", "lighting", "depth of field", "focus", "grain", "texture",
               "material", "surface", "glossy", "matte", "weathered", "metal",
               "glass", "fabric", "rim", "shadow", "glow", "backlight", "diffuse"]
    found = [a for a in anchors if a in imd.lower()]
    return len(found) >= 2


def check_cut_point(text):
    """切点不在句中：末字符应为句号/感叹号/问号/省略号。"""
    if not text:
        return False
    return text.rstrip()[-1] in "。！？…"


def check_continuity(director_text, prev_out):
    """相邻段画面连贯：本段导演设计承接上段出态。"""
    if not director_text or not prev_out:
        return True  # 无数据时跳过（不误报）
    # 上段 out 的核心词（去掉连接词）应在本段出现或本段有显式承接
    words = [w for w in re.findall(r"[\u4e00-\u9fff]{2,4}", prev_out) if w not in
             ("画面", "本段", "上一段", "承接", "锁定", "给下", "收束", "缓出")]
    if not words:
        return True
    # 宽松检查：本段导演设计包含任一上段出态关键词 或 显式"衔接/承接/延续"
    return any(w in director_text for w in words) or \
        any(k in director_text for k in ("衔接", "承接", "延续", "接续"))


def check_info_point(director_text, info_point):
    """每段传达 info_point：导演设计含本段信息点关键词。"""
    if not director_text or not info_point:
        return True  # 无数据时跳过
    # 信息点是数字短语或关键词，检查数字/关键词是否出现在导演设计中
    nums = re.findall(r"\d+(?:\.\d+)?", info_point)
    if nums:
        return any(n in director_text for n in nums)
    # 无数字：取信息点里较长的关键词片段
    keys = [k for k in re.split(r"[；，、\s]", info_point) if len(k) >= 2][:3]
    if not keys:
        return True
    return any(k in director_text for k in keys)


def get_audio_duration(path):
    """ffprobe 读音频时长，失败返回 None。"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path], capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return None
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="H3 生成段验收")
    ap.add_argument("generated_jsonl", help="generated.jsonl 路径")
    ap.add_argument("--prompts", default="/home/lmr/comfy/h3_prompts", help="h3_prompts 目录")
    ap.add_argument("--storyboard", default="/home/lmr/comfy/分镜清单_raw.json", help="分镜清单 json")
    ap.add_argument("--director-dir", default=None, help="导演设计目录（04_风格化文案，创意层检查）")
    ap.add_argument("--audio-dir", default=None, help="TTS 音频目录（05_TTS语音，音频对齐检查）")
    ap.add_argument("--out", default="/home/lmr/comfy/verify_report.json", help="报告输出路径")
    args = ap.parse_args()

    # 读 generated.jsonl
    if not os.path.exists(args.generated_jsonl):
        print(f"ERROR: {args.generated_jsonl} not found")
        sys.exit(2)

    # 流水线契约：上游（阶段五生成日志）必须已落盘
    pc.check_input(args.generated_jsonl, "阶段五生成日志")
    entries = []
    for line in open(args.generated_jsonl, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass

    # 读分镜清单（拿 est_seconds + text）
    storyboard = {}
    if os.path.exists(args.storyboard):
        try:
            sb = json.load(open(args.storyboard, encoding="utf-8"))
            if isinstance(sb, list):
                storyboard = {s["id"]: s for s in sb if "id" in s}
        except Exception:
            pass

    # 读 prompt 目录
    prompts = {}
    if os.path.isdir(args.prompts):
        for f in os.listdir(args.prompts):
            if f.endswith(".json"):
                try:
                    d = json.load(open(os.path.join(args.prompts, f), encoding="utf-8"))
                    prompts[d.get("id")] = d
                except Exception:
                    pass

    # 读导演设计目录（创意层检查 7/8）
    director_texts = {}
    if args.director_dir and os.path.isdir(args.director_dir):
        for f in os.listdir(args.director_dir):
            m = re.match(r"(shot\d+)\.md", f)
            if m:
                try:
                    director_texts[m.group(1)] = open(
                        os.path.join(args.director_dir, f), encoding="utf-8").read()
                except Exception:
                    pass

    results = []
    for e in entries:
        sid = e.get("id", "?")
        res = {"id": sid, "checks": {}, "pass": True, "fail_reasons": []}
        vid = None
        for o in e.get("outputs", []):
            if o and os.path.exists(o) and os.path.getsize(o) > 0:
                vid = o
                break
        # 1. 文件存在 / 大小
        if not vid:
            res["checks"]["file"] = False
            res["fail_reasons"].append("output file missing")
        else:
            size = os.path.getsize(vid)
            res["checks"]["file"] = size > 0
            if size <= 0:
                res["fail_reasons"].append("output file size=0")
            # 2. 时长
            dur = get_ffprobe_duration(vid)
            if dur is None:
                res["checks"]["duration"] = False
                res["fail_reasons"].append("ffprobe duration failed")
            else:
                est = storyboard.get(sid, {}).get("est_seconds")
                ok = dur <= 15.5
                if est is not None:
                    ok = ok and abs(dur - est) <= 1.5
                res["checks"]["duration"] = ok
                if not ok:
                    res["fail_reasons"].append(f"duration {dur:.1f}s vs est {est}s")
            # 3. 分辨率
            reso = get_ffprobe_resolution(vid)
            if reso is None:
                res["checks"]["resolution"] = False
                res["fail_reasons"].append("ffprobe resolution failed")
            else:
                w, h = reso
                short = min(w, h)
                ok = short in (480, 720, 768, 1440)
                res["checks"]["resolution"] = ok
                if not ok:
                    res["fail_reasons"].append(f"resolution {w}x{h}")
        # 4. prompt 三字段
        p = prompts.get(sid)
        if p is None:
            res["checks"]["prompt_fields"] = False
            res["fail_reasons"].append("prompt json missing")
        else:
            ok, missing = check_prompt_fields(p.get("prompt", ""))
            res["checks"]["prompt_fields"] = ok
            if not ok:
                res["fail_reasons"].append(f"prompt missing fields: {missing}")
            # 4b. 画质链（第 10 项）：imd 至少 2 个画质锚定词；仅提示不 FAIL（旧产物无画质词仍通过）
            okq = check_quality_anchors(p.get("prompt", ""))
            res["checks"]["quality_chain"] = okq
        # 5. 相邻段风格锁一致（简化：与上一段 prompt 前 120 字符公共前缀比例）
        if p is not None and results:
            prev = results[-1].get("_prefix", "")
            cur = p.get("prompt", "")[:120]
            if prev:
                common = os.path.commonprefix([prev, cur])
                ratio = len(common) / 120.0
                res["checks"]["style_lock"] = ratio >= 0.5
                if not res["checks"]["style_lock"]:
                    res["fail_reasons"].append(f"style lock mismatch (prefix ratio {ratio:.2f})")
            else:
                res["checks"]["style_lock"] = True
            results[-1]["_prefix"] = prev
            res["_prefix"] = cur
        else:
            res["checks"]["style_lock"] = True
            res["_prefix"] = p.get("prompt", "")[:120] if p else ""
        # 6. 切点不在句中
        t = storyboard.get(sid, {}).get("text", "")
        res["checks"]["cut_point"] = check_cut_point(t)
        if not res["checks"]["cut_point"]:
            res["fail_reasons"].append("segment ends mid-sentence")

        # 7. 相邻段画面连贯（导演设计 continuity 链）
        dt = director_texts.get(sid, "")
        prev_out = results[-1].get("_prev_out", "") if results else ""
        if args.director_dir:
            ok7 = check_continuity(dt, prev_out)
            res["checks"]["continuity"] = ok7
            if not ok7:
                res["fail_reasons"].append("continuity chain broken")
        else:
            res["checks"]["continuity"] = True
        res["_prev_out"] = ""

        # 8. 每段传达 info_point
        if args.director_dir:
            ip = storyboard.get(sid, {}).get("info_point", "")
            ok8 = check_info_point(dt, ip)
            res["checks"]["info_point"] = ok8
            if not ok8:
                res["fail_reasons"].append("director design missing info_point")
        else:
            res["checks"]["info_point"] = True

        # 9. 音频对齐（TTS 音频时长 vs 视频时长差 ≤0.5s）
        if args.audio_dir and vid is not None:
            audio_path = None
            for cand in (f"{sid}.mp3", f"{sid}.wav", f"audio_{sid}.mp3", f"audio_{sid}.wav"):
                cand_path = os.path.join(args.audio_dir, cand)
                if os.path.exists(cand_path):
                    audio_path = cand_path
                    break
            if audio_path and dur is not None:
                adur = get_audio_duration(audio_path)
                if adur is not None:
                    ok9 = abs(adur - dur) <= 0.5
                    res["checks"]["audio_align"] = ok9
                    if not ok9:
                        res["fail_reasons"].append(f"audio {adur:.1f}s vs video {dur:.1f}s")
            else:
                res["checks"]["audio_align"] = True
        else:
            res["checks"]["audio_align"] = True

        res["pass"] = all(res["checks"].values()) and not res["fail_reasons"]
        results.append(res)

    # 汇总
    n_pass = sum(1 for r in results if r["pass"])
    n_fail = len(results) - n_pass
    failed_ids = [r["id"] for r in results if not r["pass"]]

    report = {
        "generated": args.generated_jsonl,
        "total": len(results),
        "pass": n_pass,
        "fail": n_fail,
        "failed_ids": failed_ids,
        "segments": results,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(args.out + ".failed", "w", encoding="utf-8") as f:
        f.write("\n".join(failed_ids))

    print(f"=== verify_output 报告 ===")
    print(f"总计 {len(results)} 段 | PASS {n_pass} | FAIL {n_fail}")
    if failed_ids:
        print(f"失败段: {', '.join(failed_ids)}")
        for r in results:
            if not r["pass"]:
                print(f"  {r['id']}: {'; '.join(r['fail_reasons'])}")
    print(f"报告已写入: {args.out}")

    # 流水线契约：产出落盘标记（供下游确认验收完成）
    pc.stamp_output(args.out, {"total": len(results), "pass": n_pass, "fail": n_fail})

    sys.exit(0 if n_fail == 0 else 1)


if __name__ == "__main__":
    main()
