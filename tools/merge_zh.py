#!/usr/bin/env python3
"""把 data/tr_game_*.json 合并进 zh_cn.json，并按上游测试的规则校验。

校验项（对应 crates/horizon-client-core/src/lang.rs 的
`bundled_files_are_served_and_have_no_stale_or_repeated_keys`）：
1. 每个 key 都在 en_us.json 里，没有多余 key；
2. 值与英文不重复（除了本来就该一致的专有名词白名单）；
3. %s / %d / %f / %1$s / %.2f / %% 占位符与英文完全相同；
4. 值非空。
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANG_DIR = os.path.join(ROOT, "crates", "horizon-client", "assets", "horizon", "lang")
DATA = os.path.join(ROOT, "tools", "zh-cn")

# 这些英文串本身就是通用词/专有名词，中英一致是正常的。
SAME_OK = {
    "Microsoft", "X", "Boss", "BlueMap", "Ely.by", "Minecraft", "Xbox",
    "Xbox Live", "GitHub", "Java", "Java Edition", "Horizon", "Starling",
    "PNG", "ZIP", "GPU", "FPS", "LOD", "AFK", "VSync", "Boss",
}


def placeholders(text):
    """与 Rust 的 placeholders() 同样的算法。"""
    found = []
    rest = text
    while True:
        at = rest.find("%")
        if at < 0:
            break
        rest = rest[at + 1:]
        spec = len(rest)
        for i, ch in enumerate(rest):
            if not (ch.isdigit() or ch in "$."):
                spec = i
                break
        after = rest[spec:spec + 1]
        if after and after in "sdf%":
            end = spec + 1
            found.append("%" + rest[:end])
            rest = rest[end:]
        if not rest:
            break
    return sorted(found)


def main():
    en = json.load(open(os.path.join(LANG_DIR, "en_us.json"), encoding="utf-8"))
    zh = json.load(open(os.path.join(LANG_DIR, "zh_cn.json"), encoding="utf-8"))
    before = len(zh)

    added = {}
    for path in sorted(glob.glob(os.path.join(DATA, "tr_game_*.json"))):
        part = json.load(open(path, encoding="utf-8"))
        for key, said in part.items():
            if key in zh:
                print(f"已在 zh_cn 中，跳过：{key!r}")
                continue
            added[key] = said
    print(f"zh_cn {before} 条，新增 {len(added)} 条")

    missing = [k for k in en if k not in zh and k not in added]
    extra = [k for k in added if k not in en]
    if extra:
        print(f"多出 {len(extra)} 个 en_us 里没有的 key：")
        for k in extra[:20]:
            print("  " + repr(k))
    if missing:
        print(f"仍缺 {len(missing)} 条：")
        for k in missing:
            print("  " + k)

    bad_ph, bad_empty, bad_same = [], [], []
    for key, said in added.items():
        if not isinstance(said, str) or not said.strip():
            bad_empty.append(key)
            continue
        english = en.get(key)
        if english is None:
            continue
        if placeholders(said) != placeholders(english):
            bad_ph.append((key, placeholders(english), placeholders(said)))
        if said.strip() == english.strip() and english not in SAME_OK:
            bad_same.append(key)

    for key, want, got in bad_ph:
        print(f"占位符不符 {key!r}: 期望 {want} 得到 {got}")
    if bad_empty:
        print(f"空值 {len(bad_empty)} 条：{bad_empty[:10]}")
    if bad_same:
        print(f"与英文相同 {len(bad_same)} 条：")
        for k in bad_same[:30]:
            print(f"  {k!r}")

    if "--write" in sys.argv and not (extra or missing or bad_ph or bad_empty):
        merged = dict(zh)
        merged.update(added)
        # 保持 en_us 的顺序，便于和上游对比 diff。
        ordered = {k: merged[k] for k in en if k in merged}
        with open(os.path.join(LANG_DIR, "zh_cn.json"), "w", encoding="utf-8") as f:
            json.dump(ordered, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"已写入 zh_cn.json：{len(ordered)} 条")
    elif "--write" in sys.argv:
        print("有未通过项，未写入")
        return 1
    return 0 if not (extra or missing or bad_ph or bad_empty) else 1


if __name__ == "__main__":
    sys.exit(main())