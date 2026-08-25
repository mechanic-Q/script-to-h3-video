#!/usr/bin/env python3
"""segment_script.py — 阶段一：文稿分段器（按口播时长切段）。

规则（skill 硬约束）：
  - 每段 ≤70 汉字（≈15 秒口播 @4.5字/秒）
  - 段边界优先在句号/感叹号/问号处
  - 超长句强制二分（不硬切词中间）
  - 可短不可长

用法：
  segment_script.py <input.md> <output.json> [--max-chars 70]

输出：
  JSON 列表 [{id, section, text, chars, est_seconds}]
  id: shot01..shotNN, est_seconds = chars/4.5 (不含余量，增强时再加)
"""
import json, os, re, sys, argparse

CHAR_PER_SEC = 4.5


def split_sentences(text):
    """按中文标点切成句子（保留标点）。"""
    # 在句号/感叹号/问号/省略号后断开
    parts = re.split(r'(?<=[。！？…])', text)
    return [p.strip() for p in parts if p.strip()]


def split_long(sentence, max_chars):
    """超长句按逗号/分号/顿号二分，再不行按长度硬切。"""
    if len(sentence) <= max_chars:
        return [sentence]
    # 先按逗号分
    segs = re.split(r'(?<=[，；、])', sentence)
    if len(segs) > 1:
        # 贪心合并到 ≤max_chars
        merged = []
        cur = ""
        for s in segs:
            if len(cur) + len(s) <= max_chars:
                cur += s
            else:
                if cur:
                    merged.append(cur)
                cur = s
        if cur:
            merged.append(cur)
        # 合并后仍有超长片段（长句无内部逗号）→ 直接硬切，不递归
        out = []
        for m in merged:
            if len(m) > max_chars:
                out.extend([m[i:i+max_chars] for i in range(0, len(m), max_chars)])
            else:
                out.append(m)
        return out
    # 无逗号：按长度硬切
    return [sentence[i:i+max_chars] for i in range(0, len(sentence), max_chars)]


def extract_body(md):
    """提取正文：去标题/去引用，保留叙述段落和表格行（表格是口播信息的一部分）。"""
    lines = md.split('\n')
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith('#') or s.startswith('>') or s.startswith('---'):
            continue
        # 表格行去管道符与分隔行，保留单元格内容（口播会念配置/数据）
        if s.startswith('|'):
            if re.match(r'^\|[\s:\-|]+\|$', s):  # 分隔行 |---|
                continue
            cells = [c.strip() for c in s.strip('|').split('|')]
            if cells:
                out.append('，'.join(cells))
            continue
        # 去 markdown 强调符号
        s = re.sub(r'[*_`]', '', s)
        out.append(s)
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser(description="文稿分段器")
    ap.add_argument("input_md")
    ap.add_argument("output_json")
    ap.add_argument("--max-chars", type=int, default=70)
    args = ap.parse_args()

    md = open(args.input_md, encoding="utf-8").read()
    body = extract_body(md)
    sentences = split_sentences(body)

    segments = []
    cur = ""
    for s in sentences:
        if len(cur) + len(s) <= args.max_chars:
            cur += s
        else:
            if cur:
                segments.append(cur)
            # 超长句拆分
            if len(s) > args.max_chars:
                for part in split_long(s, args.max_chars):
                    segments.append(part)
                cur = ""
            else:
                cur = s
    if cur:
        segments.append(cur)

    out = []
    for i, seg in enumerate(segments):
        chars = len(seg)
        out.append({
            "id": f"shot{i+1:02d}",
            "section": "正文",
            "text": seg,
            "chars": chars,
            "est_seconds": round(chars / CHAR_PER_SEC, 1),
        })

    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    over = [s for s in out if s["chars"] > args.max_chars]
    print(f"=== 分段完成 ===")
    print(f"共 {len(out)} 段 | 超限 {len(over)} 段")
    for s in out[:3]:
        print(f"  [{s['id']}] {s['chars']}字 {s['est_seconds']}s: {s['text'][:40]}")
    if over:
        for s in over[:5]:
            print(f"  OVER [{s['id']}] {s['chars']}字: {s['text'][:30]}")
    print(f"→ {args.output_json}")


if __name__ == "__main__":
    main()
