#!/usr/bin/env python3
"""verify.py — 仓库结构最小验证器（ad-hoc verification，非测试套件）。

检查项：
1. SKILL.md frontmatter 和调用名
2. 必需文件存在
3. Markdown 本地链接
4. 常见秘密模式（API key / token / password）
5. 无生成物（480P/流水线/成片）混入仓库
"""
import os, re, sys, pathlib

ROOT = pathlib.Path(__file__).parent
FAIL = 0

def check(cond, msg):
    global FAIL
    status = "PASS" if cond else "FAIL"
    if not cond: FAIL += 1
    print(f"  [{status}] {msg}")

print("=== verify.py ===")

# 1. SKILL.md frontmatter
skill = ROOT / "skill" / "SKILL.md"
check(skill.exists(), "skill/SKILL.md 存在")
if skill.exists():
    content = skill.read_text(encoding="utf-8")
    check(content.startswith("---"), "SKILL.md frontmatter 存在")
    check("name:" in content[:200], "SKILL.md 有 name 字段")
    check("description:" in content[:200], "SKILL.md 有 description 字段")

# 2. 必需文件
required = ["LICENSE.md", "README.md", "skill/SKILL.md"]
for f in required:
    check((ROOT / f).exists(), f"必需文件 {f}")

# references
refs = ROOT / "skill" / "references"
check(refs.exists() and any(refs.iterdir()), "skill/references/ 非空")

# scripts
scripts = ROOT / "scripts"
expected_scripts = ["segment_script.py", "storyboard_enhancer.py", "submit_accel.py",
                   "compose_final.py", "tts_batch.py", "verify_output.py"]
for s in expected_scripts:
    check((scripts / s).exists(), f"scripts/{s}")

# 3. Markdown 本地链接
for md in ROOT.rglob("*.md"):
    text = md.read_text(encoding="utf-8")
    links = re.findall(r'\[.*?\]\(([^)]+)\)', text)
    for link in links:
        if link.startswith(("http://", "https://", "#", "mailto:")):
            continue
        target = (md.parent / link).resolve()
        if not target.exists():
            check(False, f"{md.name} 死链: {link}")

# 4. 秘密模式
secret_patterns = [
    (r'(?:sk-[a-zA-Z0-9]{20,})', "OpenAI API key (sk-)"),
    (r'(?:ghp_[a-zA-Z0-9]{36})', "GitHub token (ghp_)"),
    (r'(?:FEISHU_APP_SECRET\s*=\s*\S+)', "Feishu secret"),
    (r'(?:SESSDATA\s*=\s*[a-f0-9%]+)', "Bilibili SESSDATA"),
]
for py in scripts.glob("*.py"):
    text = py.read_text(encoding="utf-8")
    for pattern, name in secret_patterns:
        matches = re.findall(pattern, text)
        # 反向用例：os.environ / os.getenv 不算硬编码
        for m in matches:
            ctx = text[max(0, text.find(m)-30):text.find(m)+len(m)+10]
            if "os.environ" not in ctx and "getenv" not in ctx:
                check(False, f"{py.name} 含疑似 {name}")

# 5. 无生成物
banned = ["480P", "流水线", "成片", "05_TTS语音", "06_H3prompt", "07_成片"]
for b in banned:
    matches = list(ROOT.rglob(f"*{b}*"))
    check(not matches, f"无生成物 {b} 混入")

print(f"\n{'全部通过' if FAIL == 0 else f'{FAIL} 项失败'}")
sys.exit(0 if FAIL == 0 else 1)
