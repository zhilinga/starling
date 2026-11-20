#!/usr/bin/env python3
"""把 Noto Sans SC 的子集并进启动器用的 Geist 四套字重。

Starling 的界面字体是 Geist（crates/horizon-theme/fonts/），只有拉丁字形。
界面文字走 ab_glyph 的 glyph_id(ch)，查不到就不画，所以只把 zh.json 换成中文
会得到一片空白。这里把界面语言文件里出现的每个非 ASCII 字符，从 Noto Sans SC
取子集，按字重实例化后合并进 Geist，拉丁字形保持 Geist 自己的。

    python3 tools/make_cjk_face.py            # 下载源字体并重写四个 ttf
    python3 tools/make_cjk_face.py --check    # 只检查现有 ttf 覆盖了哪些字符

需要 fonttools（pip install fonttools）。
"""
import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
import urllib.request

from fontTools import subset
from fontTools.merge import Merger
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "crates", "horizon-theme", "fonts")
CACHE = os.path.join(ROOT, "target", "cjk-face")

# Noto Sans SC 的可变字体，OFL 授权（OFL-NotoSansSC.txt 随仓库）。
SOURCE_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/"
    "NotoSansSC%5Bwght%5D.ttf"
)
SOURCE_SHA256 = "a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da"  # 首次运行时打印，填入以固定版本

# 每套 Geist 字重对应的 Noto 字重。
FACES = {
    "Geist-Regular": 400,
    "Geist-Medium": 500,
    "Geist-SemiBold": 600,
    "GeistMono-Regular": 400,
}

LANG_GLOBS = [
    "crates/horizon-client/assets/horizon/lang/zh_cn.json",
    "launcher/lang/zh.json",
]

# 兜底：语言文件里不一定出现、但界面会用到（诸如省略号、箭头、全角符号）。
FALLBACK = (
    "，。、；：？！“”‘’（）【】《》〈〉「」『』…—～·×÷±°℃№"
    "０１２３４５６７８９"
    "←→↑↓↔⇄★☆●○◆◇■□▲△▼▽"
    "①②③④⑤⑥⑦⑧⑨⑩"
    "／＼＿＾｜"
)

# 合并时丢掉 Noto 的排版表：Geist 的 GDEF/GSUB/GPOS 保留，Noto 的
# 变体表（HVAR 等）在实例化后无意义，且 Merger 不支持 VarStore。
DROP = ["DSIG", "GDEF", "GSUB", "GPOS", "BASE", "STAT", "HVAR", "VVAR",
        "MVAR", "vhea", "vmtx", "gasp", "prep", "cvt ", "fpgm"]


def wanted_chars():
    chars = set(FALLBACK)
    for pattern in LANG_GLOBS:
        for path in glob.glob(os.path.join(ROOT, pattern)):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            if isinstance(data, dict):
                for text in data.values():
                    if isinstance(text, str):
                        chars.update(text)
    return {c for c in chars if ord(c) > 0x7E}


def source_font():
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "NotoSansSC-VF.ttf")
    if not os.path.isfile(path):
        print(f"下载 {SOURCE_URL}")
        with urllib.request.urlopen(SOURCE_URL, timeout=300) as r:
            body = r.read()
        with open(path, "wb") as f:
            f.write(body)
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    print(f"源字体 {os.path.getsize(path)} B sha256 {digest}")
    if SOURCE_SHA256 and digest != SOURCE_SHA256:
        sys.exit(f"源字体校验失败：期望 {SOURCE_SHA256}")
    return path


def subset_for(weight, chars, out):
    """按字符集取子集，并把可变字体固定到 `weight`。"""
    font = TTFont(source_font())
    instancer.instantiateVariableFont(font, {"wght": weight}, inplace=True)
    options = subset.Options()
    options.glyph_names = False
    options.notdef_outline = True
    options.hinting = False
    options.drop_tables = DROP
    sub = subset.Subsetter(options=options)
    sub.populate(unicodes=[ord(c) for c in chars])
    sub.subset(font)
    font.save(out)
    have = set()
    for table in font["cmap"].tables:
        have.update(chr(cp) for cp in table.cmap)
    return have


def check(_faces=None):
    """每套 ttf 覆盖了语言文件里的哪些非 ASCII 字符。"""
    chars = wanted_chars()
    bad = 0
    for name in FACES:
        path = os.path.join(FONT_DIR, name + ".ttf")
        font = TTFont(path, lazy=True)
        have = set()
        for table in font["cmap"].tables:
            have.update(chr(cp) for cp in table.cmap)
        missing = sorted(chars - have)
        print(f"{name}.ttf {os.path.getsize(path)} B 缺 {len(missing)} 个")
        if missing:
            print("  " + "".join(missing[:60]))
            bad += 1
    return 1 if bad else 0


def restore_metrics(target, original):
    """把垂直度量恢复成 Geist 的值。

    ui_theme.rs 的 scale() 是 `px * font.height_unscaled() / upem`，而
    ab_glyph 的 height_unscaled() 取 hhea 的 ascent - descent。Merger 会把
    Noto 的 ascent（1160）盖到 Geist 的（1005）上，字号因此被放大 12%
    （1300 -> 1455）。这里把 hhea 与 OS/2 的垂直度量按原文件写回。
    """
    src = TTFont(original)
    dst = TTFont(target)
    for table, fields in (
        ("hhea", ("ascent", "descent", "lineGap")),
        ("OS/2", ("sTypoAscender", "sTypoDescender", "sTypoLineGap",
                  "usWinAscent", "usWinDescent")),
    ):
        a, b = src[table], dst[table]
        for field in fields:
            setattr(b, field, getattr(a, field))
    dst.save(target)


def build():
    chars = wanted_chars()
    print(f"{len(chars)} 个非 ASCII 字符要并入")
    os.makedirs(CACHE, exist_ok=True)
    subset_path = os.path.join(CACHE, "subset.ttf")
    for name, weight in FACES.items():
        have = subset_for(weight, chars, subset_path)
        missing = sorted(chars - have)
        if missing:
            print(f"  {name}: 源字体缺 {len(missing)} 个：{''.join(missing[:40])}")
        target = os.path.join(FONT_DIR, name + ".ttf")
        # 原字体留一份：合并后要把垂直度量恢复成它的。
        original = os.path.join(CACHE, name + ".original.ttf")
        if not os.path.isfile(original):
            shutil.copyfile(target, original)
        merged = Merger().merge([original, subset_path])
        merged.save(target + ".new")
        os.replace(target + ".new", target)
        restore_metrics(target, original)
        print(f"{name}.ttf -> {os.path.getsize(target)} B")
    os.remove(subset_path)
    return check(FACES)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="只检查不生成")
    args = ap.parse_args()
    return check() if args.check else build()


if __name__ == "__main__":
    sys.exit(main())