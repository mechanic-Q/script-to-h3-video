#!/usr/bin/env python3
"""submit_accel.py — 用「▶▷MiniMaxH3-加速视频流整合」工作流串行生成 H3 视频。

流程：
  1. ui2api 转换工作流（覆盖 199 时长 + 194 prompt）
  2. powershell 桥接提交到 Windows ComfyUI
  3. 等待完成 → 拷贝到项目 480P 文件夹

用法：
  submit_accel.py <start> <end> <prompt_dir>
    prompt_dir: 项目 04_H3prompt/（每段 {id}.json: {prompt, video_seconds}）
"""
import json, os, sys, time, subprocess, random, re, shutil, glob

WORKFLOW = "/mnt/e/AI/Comfyui-WF-2026.8.8/Comfyui-WF-2026.8.8/ComfyUI/user/default/workflows/▶▷MiniMaxH3-加速视频流整合.json"
WIN_OUT = "/mnt/e/AI/Comfyui-WF-2026.8.8/Comfyui-WF-2026.8.8/ComfyUI/output/video/MiniMax_H3"
WIN_OUT_ROOT = "/mnt/e/AI/Comfyui-WF-2026.8.8/Comfyui-WF-2026.8.8/ComfyUI/output"
PROJ_OUT = "/mnt/e/AI/Comfyui-WF-2026.8.8/minimax-h3-5080/480P"
LOG = "/home/lmr/comfy/generated_480P_test.jsonl"
SLUG = ""  # 项目前缀（默认空=不重命名，兼容旧用法）
HERE = "/home/lmr/comfy"


def ps(cmd, timeout=60):
    """调用 Windows PowerShell（完整路径，WSL PATH 不一定含 System32）。"""
    PS = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    if "'" in cmd:
        escaped = cmd.replace('$', '\\$').replace('"', '\\"')
        full = f"{PS} -NoProfile -Command \"{escaped}\""
    else:
        full = f"{PS} -NoProfile -Command '{cmd}'"
    r = subprocess.run(full, shell=True, capture_output=True, text=True,
                       timeout=timeout, encoding='utf-8', errors='replace')
    return r.stdout + r.stderr


def fix_models(api):
    """只保留 194 T2V 主链路节点（193 SaveVideo 反向 BFS），其余移除 + 模型名修正。"""
    # 模型名映射（工作流引用 → 实际存在）——LoRA 原值（反斜杠）就是正确的，不映射
    model_fix = {
        "Minimax_H3\\minimax_h3_fl2va_pruned_int8_convrot.safetensors": "minimax_h3_fl2va_int8_convrot.safetensors",
        "minimax_h3_fl2va_pruned_int8_convrot.safetensors": "minimax_h3_fl2va_int8_convrot.safetensors",
        "qwen3vl_32b_minimax_h3_int8_convrot.safetensors": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        # LoRA 实际在 loras/ 根目录（无 minimax_h3 子目录），工作流反斜杠子目录引用会 400
        "minimax_h3\\minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors": "minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors",
        "minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors": "minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors",
    }
    # 194 主链路（193 SaveVideo 反向 BFS）
    from collections import deque
    visited = set()
    q = deque(["193"])
    while q:
        nid = q.popleft()
        if nid in visited or nid not in api:
            continue
        visited.add(nid)
        for k, v in api[nid]["inputs"].items():
            if isinstance(v, list) and len(v) == 2:
                q.append(str(v[0]))
    # 移除非主链路节点
    for nid in [n for n in api if n not in visited]:
        del api[nid]
    # 模型名修正
    for nid, node in api.items():
        for k, v in node["inputs"].items():
            if isinstance(v, str) and v in model_fix:
                node["inputs"][k] = model_fix[v]
    return api


def convert_workflow(prompt_text, duration):
    """ui2api 转换 + 覆盖 199(时长) + 194(prompt)。"""
    # 用 ui2api 模块转换
    sys.path.insert(0, HERE)
    import importlib.util
    spec = importlib.util.spec_from_file_location("ui2api", f"{HERE}/ui2api.py")
    ui2api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ui2api)
    wf = json.load(open(WORKFLOW, encoding='utf-8'))
    api = ui2api.convert(wf)
    api = fix_models(api)
    # 覆盖 199 时长
    api["199"]["inputs"]["value"] = duration
    # 覆盖 194 prompt（T2V 主分支）
    api["194"]["inputs"]["prompt"] = prompt_text
    # 输出文件名带 pid（193 SaveVideo 的 filename_prefix）
    # 自适应：相对路径 480P/ 输出 + 项目前缀（如 480P/icehouse-hyperthermal-event_shot01）
    # ComfyUI 输出到 output/480P/，拷贝阶段再转到稿子同级 480P/
    prefix = os.environ.get("CUR_PID", "shot")
    if SLUG:
        prefix = f"{SLUG}_{prefix}"
    api["193"]["inputs"]["filename_prefix"] = "480P/" + prefix

    # === T08: prompt 覆盖校验（防静默失败）===
    # 特征串：我们的现实写实 prompt 必有 "photorealistic"（大小写不敏感）
    marker = os.environ.get("H3_MARKER", "paper collage")
    actual_prompt = api["194"]["inputs"].get("prompt", "")
    if marker not in actual_prompt.lower():
        raise ValueError(
            f"[OVERRIDE_CHECK] 194 prompt 覆盖校验失败: 不含特征串 '{marker}'\n"
            f"实际 prompt 前 100 字: {actual_prompt[:100]!r}"
        )
    # 确认不是工作流默认值（"精灵女子"示例）：只要含我们的 marker 就是覆盖成功
    if "精灵女子" in actual_prompt and marker not in actual_prompt and "integrated_multimodal_description" not in actual_prompt:
        raise ValueError("[OVERRIDE_CHECK] 194 prompt 疑似为工作流默认值（未覆盖成功）")
    return api


def submit(api):
    with open("/tmp/api_accel.json", "w", encoding="utf-8") as f:
        json.dump({"prompt": api}, f, ensure_ascii=False)
    subprocess.run(["cp", "/tmp/api_accel.json",
                    "/mnt/c/Users/LMR/AppData/Local/Temp/api_accel.json"], check=True)
    cmd = (
        "$body = [System.IO.File]::ReadAllBytes('C:\\Users\\LMR\\AppData\\Local\\Temp\\api_accel.json'); "
        "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8188/prompt' -Method Post -Body $body "
        "-ContentType 'application/json' -TimeoutSec 15 -UseBasicParsing; Write-Host $r.Content } "
        "catch { Write-Host ('ERROR ' + $_.Exception.Message); if ($_.ErrorDetails) { Write-Host $_.ErrorDetails.Message } }"
    )
    return ps(cmd)


def wait_done(prompt_id, timeout=900):
    start = time.time()
    while time.time() - start < timeout:
        out = ps(f"$h = Invoke-WebRequest -Uri 'http://127.0.0.1:8188/history/{prompt_id}' -UseBasicParsing -TimeoutSec 5; $h.Content")
        try:
            h = json.loads(out.strip())
            if h and prompt_id in h:
                st = h[prompt_id].get("status", {})
                return st.get("status_str"), st.get("completed")
        except Exception:
            pass
        time.sleep(20)
    return "TIMEOUT", False


def queue_status():
    out = ps("$q = Invoke-WebRequest -Uri 'http://127.0.0.1:8188/queue' -UseBasicParsing -TimeoutSec 5; $q.Content")
    out = out.strip().lstrip('\ufeff')
    s, e = out.find('{'), out.rfind('}')
    if s >= 0 and e > s:
        try:
            return json.loads(out[s:e+1])
        except Exception:
            return {"queue_running": [1], "queue_pending": []}
    return {"queue_running": [1], "queue_pending": []}


def free_memory():
    cmd = (
        "try { $body = '{\"unload_models\": true, \"free_memory\": true}'; "
        "$r = Invoke-WebRequest -Uri 'http://127.0.0.1:8188/free' -Method Post -Body $body "
        "-ContentType 'application/json' -UseBasicParsing -TimeoutSec 15; "
        "if ($r.StatusCode -eq 200) { Write-Host 'OK' } else { Write-Host ('HTTP ' + $r.StatusCode) } } "
        "catch { Write-Host ('ERR ' + $_.Exception.Message) }"
    )
    return "OK" in ps(cmd)


def verify_history_prompt(prompt_id, expected_marker, timeout=30):
    """T08: 提交后查 history，确认实际执行的 prompt 含我们的特征串。"""
    marker = os.environ.get("H3_MARKER", "paper collage")
    start = time.time()
    while time.time() - start < timeout:
        out = ps(f"$h = Invoke-WebRequest -Uri 'http://127.0.0.1:8188/history/{prompt_id}' -UseBasicParsing -TimeoutSec 5; $h.Content")
        try:
            h = json.loads(out.strip())
            if h and prompt_id in h:
                # 从 history 的 prompt 字段检查
                hist_prompt = json.dumps(h.get(prompt_id, {}).get("prompt", {}), ensure_ascii=False)
                return marker in hist_prompt.lower()
        except Exception:
            pass
        time.sleep(5)
    return False


def main():
    start, end = int(sys.argv[1]), int(sys.argv[2])
    prompt_dir = sys.argv[3]
    # 自适应项目目录（用户 2026-08-13 要求）：
    # 480P 输出到"稿子所在目录/480P"，不是 prompt_dir 上一级。
    # 用法：submit_accel.py <start> <end> <prompt_dir> --script <稿子路径>
    global LOG, PROJ_OUT, SLUG
    script_path = None
    if "--script" in sys.argv:
        script_path = sys.argv[sys.argv.index("--script") + 1]
    if script_path and os.path.isfile(script_path):
        # 稿子目录 = 480P 输出位置；slug 从稿子文件名提取（去掉日期前缀和"-稿.md"后缀）
        script_dir = os.path.dirname(os.path.abspath(script_path))
        PROJ_OUT = os.path.join(script_dir, "480P")
        os.makedirs(PROJ_OUT, exist_ok=True)
        LOG = os.path.join(script_dir, "generated_480P.jsonl")
        base = os.path.basename(script_path)
        slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", base)
        slug = re.sub(r"-稿\.md$|\.md$", "", slug)
        SLUG = slug
        print(f"[PROJ] 稿子: {script_path}")
        print(f"[PROJ] 480P 输出: {PROJ_OUT}")
        print(f"[PROJ] 记录文件: {LOG}")
        print(f"[PROJ] 项目前缀: {SLUG}")
    else:
        # 兼容旧用法：prompt_dir 上一级 / 480P
        _pd = os.path.abspath(prompt_dir)
        _proj = os.path.dirname(_pd)
        if os.path.basename(_pd) in ("06_H3prompt", "04_H3prompt", "h3_prompts") and os.path.isdir(_proj):
            PROJ_OUT = os.path.join(_proj, "480P")
            os.makedirs(PROJ_OUT, exist_ok=True)
            LOG = os.path.join(_proj, "generated_480P.jsonl")
            print(f"[PROJ] 产物目录: {PROJ_OUT}")
            print(f"[PROJ] 记录文件: {LOG}")
            SLUG = os.path.basename(_proj)
    done = set()
    if os.path.exists(LOG):
        for line in open(LOG, encoding="utf-8"):
            try:
                done.add(json.loads(line)["id"])
            except Exception:
                pass

    for n in range(start, end + 1):
        pid = f"shot{n:02d}"
        if pid in done:
            print(f"[SKIP] {pid} already done")
            continue
        pf = os.path.join(prompt_dir, f"{pid}.json")
        if not os.path.exists(pf):
            print(f"[MISS] {pid} no prompt file")
            continue
        shot = json.load(open(pf, encoding="utf-8"))
        # 队列确认
        q = queue_status()
        while q.get("queue_running"):
            print(f"[WAIT] {pid} queue busy...")
            time.sleep(30)
            q = queue_status()
        free_ok = free_memory()
        print(f"[FREE] {pid} {'ok' if free_ok else 'failed'}")
        os.environ["CUR_PID"] = pid
        # === T08: 提交前覆盖校验（失败自动重试 2 次）===
        api = None
        for attempt in range(3):
            try:
                api = convert_workflow(shot["prompt"], shot["video_seconds"])
                break
            except ValueError as e:
                print(f"[OVERRIDE_RETRY] {pid} attempt {attempt+1}/3: {e}")
                if attempt == 2:
                    print(f"[FAIL] {pid} override check failed after 3 attempts, skip")
                    api = None
                    break
        if api is None:
            continue
        resp = submit(api)
        m = re.search(r'"prompt_id"\s*:\s*"([^"]+)"', resp)
        if not m:
            print(f"[FAIL] {pid} submit error: {resp[:300]}")
            continue
        pid_id = m.group(1)
        # === T08: 提交后 history 验证实际执行的 prompt ===
        print(f"[RUN] {pid} submitted ({shot['video_seconds']}s) id={pid_id}")
        verify = verify_history_prompt(pid_id, shot["prompt"])
        if not verify:
            print(f"[WARN] {pid} history prompt 与提交不一致（可能未生效），继续但标记")
        status, completed = wait_done(pid_id)
        if completed:
            # 只拷贝本次 prompt_id 的实际输出（防跨项目残留混入）
            hist = ps(f"$h = Invoke-WebRequest -Uri 'http://127.0.0.1:8188/history/{pid_id}' -UseBasicParsing -TimeoutSec 5; $h.Content")
            hist = hist.strip().lstrip('\ufeff')
            new_files = []
            try:
                h = json.loads(hist[hist.find('{'):hist.rfind('}')+1])
                outs = h.get(pid_id, {}).get("outputs", {})
                for node_id, node_out in outs.items():
                    for f in node_out.get("gifs", []) + node_out.get("videos", []):
                        fn = f.get("filename", "")
                        if fn:
                            # filename 是相对 ComfyUI output 根的路径（如 480P/xxx.mp4 或 video/MiniMax_H3/xxx.mp4）
                            new_files.append(os.path.join(WIN_OUT_ROOT, fn.lstrip("/\\")))
            except Exception:
                new_files = []
            if not new_files:
                # 兜底：按 pid 匹配（兼容带项目前缀名）+ 最近 10 分钟产出（全 output 树）
                import time as _t
                cutoff = _t.time() - 600
                new_files = [f for f in glob.glob(os.path.join(WIN_OUT_ROOT, "**", f"*{pid}*"), recursive=True)
                             if os.path.getmtime(f) >= cutoff]
            copied = []
            for f in sorted(set(new_files), key=os.path.getmtime):
                try:
                    src_name = os.path.basename(f)
                    # 输出文件名加项目前缀，防跨项目同名混淆（如 icehouse-20260812_shot01_00006_.mp4）
                    # 若源文件已带 SLUG 前缀（工作流 filename_prefix 已注入），不重复加
                    if SLUG and not src_name.startswith(SLUG + "_"):
                        dst_name = f"{SLUG}_{src_name}"
                    else:
                        dst_name = src_name
                    dst = os.path.join(PROJ_OUT, dst_name)
                    shutil.copy2(f, dst)
                    copied.append(dst)
                except Exception as e:
                    print(f"[COPY_WARN] {e}")
            rec = {"id": pid, "prompt_id": pid_id, "status": status,
                   "outputs": sorted(new_files), "copied": copied}
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"[OK] {pid}: {len(new_files)} 个新输出 → copied {len(copied)}")
        else:
            print(f"[WARN] {pid} status={status}")


if __name__ == "__main__":
    main()
