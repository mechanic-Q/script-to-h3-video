#!/usr/bin/env python3
"""cleanup_480p.py — 清理 480P 文件夹中的旧项目残留（保留本次运行的新文件）。

用法: cleanup_480p.py <480P目录> <起始时间戳>
按文件 mtime 过滤：< 起始时间戳 的移入 480P_旧项目残留/（隔离不删，红线）
"""
import os, sys, shutil, glob, time

base = sys.argv[1]
cutoff = float(sys.argv[2]) if len(sys.argv) > 2 else time.time() - 3600
q = os.path.join(os.path.dirname(base), '480P_旧项目残留')
os.makedirs(q, exist_ok=True)

moved = []
for f in sorted(glob.glob(os.path.join(base, '*.mp4'))):
    if os.path.getmtime(f) < cutoff:
        dst = os.path.join(q, os.path.basename(f))
        if not os.path.exists(dst):
            shutil.move(f, dst)
        else:
            os.remove(f)
        moved.append(os.path.basename(f))

print(f'隔离旧文件 {len(moved)} 个 → {q}')
for m in moved[:10]:
    print('  ', m)
