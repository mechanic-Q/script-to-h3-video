#!/usr/bin/env python3
"""pipeline_contract.py — 流水线契约：环节间只传文件的强制机制。

用户三条要求（2026-08-25）：
  1. 每一个环节之间，必须从上一个环节获取文件
  2. 每一个环节分析完后，文件必须落地，不能只存在于 Agent 上下文中
  3. 每一次生成的文件都必须落地，下一个环节必须读取上一个环节的文件

机制：
  check_input(path, desc)  —— 环节开头校验上游文件存在且非空
  stamp_output(path, meta) —— 环节结尾写 .done.json 完成标记（含元数据）
  require_stamp(path, desc) —— 下游确认上游已完成标记

用法：每个环节脚本开头 import pipeline_contract as pc，
      check_input(上游产物) → ... 本环节逻辑 ... → stamp_output(本环节产物)
"""
import os, sys, json, hashlib


def file_hash(path):
    """SHA256 文件哈希（用于产物指纹）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def check_input(path, desc):
    """校验上游文件存在且非空。缺失/为空则报错退出。"""
    if not os.path.exists(path):
        print(f"ERROR: 上游[{desc}]缺失: {path}")
        print(f"请先运行上一环节，产物未落盘")
        sys.exit(2)
    if os.path.isdir(path):
        # 目录：校验非空
        if not os.listdir(path):
            print(f"ERROR: 上游[{desc}]为空目录: {path}")
            sys.exit(2)
        return
    if os.path.getsize(path) == 0:
        print(f"ERROR: 上游[{desc}]为空文件: {path}")
        sys.exit(2)


def stamp_output(path, meta=None):
    """环节结尾写完成标记（含产物哈希），供下游确认。

    meta: dict，如 {"total": 107, "checks_pass": 107}
    返回标记文件路径。
    """
    stamp_path = path + ".done.json"
    stamp = {
        "output": path,
        "hash": file_hash(path) if os.path.isfile(path) else None,
        "meta": meta or {},
    }
    with open(stamp_path, "w", encoding="utf-8") as f:
        json.dump(stamp, f, ensure_ascii=False, indent=2)
    return stamp_path


def require_stamp(path, desc):
    """下游确认上游已完成（.done.json 存在）。缺失则报错退出。"""
    stamp_path = path + ".done.json"
    if not os.path.exists(stamp_path):
        print(f"ERROR: 上游[{desc}]未完成（无完成标记 {stamp_path}）")
        print(f"请先运行上一环节，产物完成标记未落盘")
        sys.exit(2)
    # 校验产物本身仍在
    if os.path.isfile(path) and os.path.getsize(path) == 0:
        print(f"ERROR: 上游[{desc}]产物为空: {path}")
        sys.exit(2)


def read_stamp(path):
    """读取上游完成标记元数据，不存在返回 None。"""
    stamp_path = path + ".done.json"
    if not os.path.exists(stamp_path):
        return None
    try:
        return json.load(open(stamp_path, encoding="utf-8"))
    except Exception:
        return None


if __name__ == "__main__":
    # 自检
    import tempfile
    tmp = tempfile.mkdtemp(prefix="contract_test_")
    f = os.path.join(tmp, "test.txt")
    open(f, "w").write("hello")
    stamp = stamp_output(f, {"n": 1})
    assert os.path.exists(stamp), "stamp not written"
    require_stamp(f, "测试")
    assert read_stamp(f)["meta"]["n"] == 1
    print("pipeline_contract 自检通过 ✓")
