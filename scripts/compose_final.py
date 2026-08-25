#!/usr/bin/env python3
"""compose_final.py — 阶段五：拼接完整视频（视频段 + 口播音频 + BGM）。

流程：
  1. 按 shot01..shotNN 顺序收集 480P 视频段
  2. 收集对应口播音频（04_TTS语音/shotXX.wav）
  3. ffmpeg 逐段合并（视频+音频）→ 4. concat 全部段 → 5. 叠 BGM（mixkit 322/580，0.2-0.33x + fade）

用法：
  compose_final.py <video_dir> <audio_dir> <output_dir> [--bgm <path>] [--bgm-volume 0.25]
"""
import json, os, sys, subprocess, argparse, glob, re


def ff(cmd, timeout=300):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout[-300:], r.stderr[-300:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video_dir")   # 480P 视频目录
    ap.add_argument("audio_dir")   # 口播音频目录
    ap.add_argument("output_dir")  # 05_成片 输出
    ap.add_argument("--bgm", default=None)
    ap.add_argument("--bgm-volume", type=float, default=0.25)
    ap.add_argument("--max-shots", type=int, default=9999)
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    # 收集视频段（按 shotNN 排序，兼容带项目前缀名如 icehouse-20260812_shot01_00006_.mp4）
    vids = {}
    for f in glob.glob(os.path.join(args.video_dir, "*_shot*.mp4")) + glob.glob(os.path.join(args.video_dir, "shot*.mp4")):
        m = re.search(r"shot(\d+)", os.path.basename(f))
        if m:
            vids[m.group(0)] = f
    shot_ids = sorted(vids.keys(), key=lambda x: int(re.search(r"\d+", x).group()))
    shot_ids = [s for s in shot_ids if int(s.replace("shot", "")) <= args.max_shots]
    print(f"收集到 {len(shot_ids)} 个视频段")

    # 逐段合并视频+音频（如果音频存在）
    merged_dir = os.path.join(args.output_dir, "_merged")
    os.makedirs(merged_dir, exist_ok=True)
    concat_list = []
    missing_audio = []
    for sid in shot_ids:
        v = vids[sid]
        a = os.path.join(args.audio_dir, f"{sid}.wav")
        out = os.path.join(merged_dir, f"{sid}.mp4")
        if os.path.exists(a):
            # 视频+音频合并（音频对齐视频时长，不足循环/超出裁剪）
            cmd = ["ffmpeg", "-y", "-i", v, "-i", a,
                   "-c:v", "copy", "-c:a", "aac", "-shortest",
                   "-map", "0:v:0", "-map", "1:a:0", out]
        else:
            # 无音频：仅视频（保持静音）
            missing_audio.append(sid)
            cmd = ["ffmpeg", "-y", "-i", v, "-c:v", "copy", "-an", out]
        rc, so, se = ff(cmd)
        if rc != 0:
            print(f"[FAIL] {sid} merge: {se[-200:]}")
            continue
        concat_list.append(f"file '{out}'")
    print(f"合并完成 {len(concat_list)} 段" + (f"，{len(missing_audio)} 段无音频: {missing_audio[:5]}" if missing_audio else ""))

    if not concat_list:
        print("无可拼接段")
        sys.exit(1)

    # concat 全部段
    list_file = os.path.join(args.output_dir, "_concat.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        f.write("\n".join(concat_list))
    final = os.path.join(args.output_dir, "成片_无BGM.mp4")
    rc, so, se = ff(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                     "-i", list_file, "-c", "copy", final])
    if rc != 0:
        print(f"[FAIL] concat: {se[-200:]}")
        sys.exit(1)
    print(f"拼接完成: {final}")

    # BGM 叠加
    if args.bgm and os.path.exists(args.bgm):
        final_bgm = os.path.join(args.output_dir, "成片_最终.mp4")
        # 先取成片时长
        rc, so, se = ff(["ffprobe", "-v", "error", "-show_entries",
                         "format=duration", "-of", "csv=p=0", final])
        dur = float(so.strip() or 0)
        # BGM 循环铺满全片 + fade（-stream_loop -1 循环，-t 裁剪到成片时长）
        bgm_cut = os.path.join(args.output_dir, "_bgm_cut.mp3")
        ff(["ffmpeg", "-y", "-stream_loop", "-1", "-i", args.bgm, "-t", str(dur),
            "-af", f"volume={args.bgm_volume},afade=t=in:d=0.5,afade=t=out:st={max(0, dur-2)}:d=2",
            "-c:a", "libmp3lame", bgm_cut])
        # 混合
        rc, so, se = ff(["ffmpeg", "-y", "-i", final, "-i", bgm_cut,
                         "-filter_complex", "[0:a]volume=1.0[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                         "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", final_bgm])
        if rc == 0:
            print(f"BGM 叠加完成: {final_bgm}")
        else:
            print(f"[FAIL] bgm mix: {se[-200:]}")
    else:
        print(f"无 BGM（或文件不存在）: {args.bgm}")
        print(f"最终成片: {final}")


if __name__ == "__main__":
    main()
