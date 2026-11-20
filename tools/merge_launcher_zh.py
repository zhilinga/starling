#!/usr/bin/env python3
"""把 data/tr_launcher.json 合并进 launcher/lang/zh.json。

启动器的 i18n 用英文原文当 key（launcher/src/i18n.rs: HashMap<String, &str>），
测试 `every_language_has_every_string_the_code_asks_for` 要求每个语言表的
key 集合完全一致，`holes()` 校验 {name} 占位符，值不得为空。
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG_DIR = os.path.join(ROOT, "launcher", "lang")
DATA = os.path.join(ROOT, "tools", "zh-cn")

# 中英一致是正常的：专有名词、品牌、缩写。
SAME_OK = {
    "Microsoft", "Beta", "Alpha", "Horizon", "MangoHud",
    "Install ID {prefix}…{suffix}", "Minecraft {version}",
    "Launcher {version}  {percent}%", "Launcher {version}",
}


def holes(text):
    """与 launcher/src/i18n/tests.rs 的 holes() 同样的算法。"""
    out = set()
    for part in text.split("{")[1:]:
        if "}" in part:
            out.add(part.split("}", 1)[0])
    return out


def main():
    ref = json.load(open(os.path.join(LANG_DIR, "fr.json"), encoding="utf-8"))
    zh = json.load(open(os.path.join(LANG_DIR, "zh.json"), encoding="utf-8"))
    print(f"参考表 {len(ref)} 条，zh 现有 {len(zh)} 条")

    part = {}
    for path in sorted(glob.glob(os.path.join(DATA, "tr_launcher*.json"))):
        part.update(json.load(open(path, encoding="utf-8")))

    added = {k: v for k, v in part.items() if k in ref and zh.get(k) != v}
    unknown = [k for k in part if k not in ref]
    if unknown:
        print(f"{len(unknown)} 个 key 不在参考表里：")
        for k in unknown[:10]:
            print("  " + repr(k))

    bad_holes, bad_empty, bad_same = [], [], []
    for key, said in added.items():
        if not said.strip():
            bad_empty.append(key)
        if holes(said) != holes(key):
            bad_holes.append((key, holes(key), holes(said)))
        if said.strip() == key.strip() and key not in SAME_OK:
            bad_same.append(key)
    for key, want, got in bad_holes:
        print(f"占位符不符 {key!r}: 期望 {want} 得到 {got}")
    if bad_empty:
        print(f"空值：{bad_empty}")
    if bad_same:
        print(f"仍与英文相同 {len(bad_same)} 条：{bad_same[:20]}")

    print(f"本次改动 {len(added)} 条")
    if "--write" in sys.argv and not (unknown or bad_holes or bad_empty):
        merged = dict(zh)
        merged.update(added)
        ordered = {k: merged[k] for k in ref if k in merged}
        with open(os.path.join(LANG_DIR, "zh.json"), "w", encoding="utf-8") as f:
            json.dump(ordered, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"已写入 zh.json：{len(ordered)} 条")
    elif "--write" in sys.argv:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())