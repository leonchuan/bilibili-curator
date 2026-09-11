#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bilibili-curator 打包脚本

把技能目录打成可发布的分发包（.zip），自动排除运行时数据、虚拟环境和缓存。

用法：
    python build_zip.py                 # 输出到 dist/<name>-v<version>.zip
    python build_zip.py --out D:/x.zip  # 指定输出路径
    python build_zip.py --list          # 只列清单，不打包
    python build_zip.py --no-prefix     # 不套顶层目录（根目录直接放 SKILL.md）

排除规则是硬编码在 EXCLUDE_* 里的，不依赖 .gitignore —— 因为 .data/ 里有
浏览器登录态，这类东西一旦误打进包上传就是事故，不能靠"记得排除"。
"""

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
ROOT_NAME = SKILL_DIR.name
SIZE_LIMIT_MB = 3.0

# ---------- 排除规则 ----------

# 目录名命中即整枝跳过
EXCLUDE_DIRS = {
    ".venv", "venv", "env",              # 虚拟环境（120MB+）
    ".data", "browser_profile",          # ★ 运行时数据，含 B站 登录态
    "__pycache__", ".pytest_cache",      # Python 缓存
    ".git", ".idea", ".vscode",          # 版本控制 / 编辑器
    "dist", "build", "release",          # 构建产物 / 已发布版本归档
    "node_modules",
}

# 文件名命中即跳过
EXCLUDE_FILES = {
    "build_zip.py",                      # 本脚本自身（开发工具，非技能本体）
    ".DS_Store", "Thumbs.db",            # 系统垃圾
}

# 扩展名命中即跳过
EXCLUDE_SUFFIXES = {
    ".pyc", ".pyo", ".pyd",              # 编译产物
    ".zip", ".tar", ".gz",               # 归档
    ".log",                              # 日志
    ".bak", ".tmp", ".swp",              # 临时文件
}

# 必须存在，否则视为目录不完整
REQUIRED = ["SKILL.md"]

# WorkBuddy 开放平台要求的 frontmatter 字段（缺一个就上传失败）
PLATFORM_FIELDS = (
    "name", "display_name", "display_name_en",
    "description", "description_zh", "description_en",
    "category", "version", "author",
)


def parse_frontmatter(text: str):
    """取出 SKILL.md 的 frontmatter 原文（首个 --- 与下一个 --- 之间）"""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return None
    body = stripped[3:]
    end = body.find("\n---")
    return body[:end] if end != -1 else None


def read_version() -> str:
    """从 SKILL.md 的 frontmatter 读版本号。"""
    skill_md = SKILL_DIR / "SKILL.md"
    if not skill_md.exists():
        return "0.0.0"
    fm = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="ignore"))
    if not fm:
        return "0.0.0"
    m = re.search(r"^version: (\S+)", fm, re.M)
    return m.group(1) if m else "0.0.0"


def validate() -> list:
    """打包含前的自检，返回错误列表。"""
    errs = []
    for req in REQUIRED:
        if not (SKILL_DIR / req).exists():
            errs.append(f"缺少必需文件：{req}")

    # 敏感目录不得被纳入（保险起见，即使规则写错也能拦住）
    for probe in ("browser_profile", ".data"):
        p = SKILL_DIR / probe
        if p.exists() and p.is_dir():
            pass  # 存在是正常的，只要没被打进去即可

    # SKILL.md frontmatter 校验（按 WorkBuddy 开放平台规范）
    skill_md = SKILL_DIR / "SKILL.md"
    if skill_md.exists():
        fm = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="ignore"))
        if fm is None:
            errs.append("SKILL.md 缺少 frontmatter（应以 --- 开头，并有结束 ---）")
        else:
            for field in PLATFORM_FIELDS:
                if not re.search(rf"^{field}: .+", fm, re.M):
                    errs.append(f"frontmatter 缺少字段（或冒号后没空格）：{field}")
            for line in fm.strip().split("\n"):
                if not line.strip():
                    continue
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_-]*: .+$", line):
                    errs.append(f"frontmatter 行格式不对（冒号后必须空一格）：{line[:46]}")
                if '"' in line or "\u201c" in line or "\u201d" in line:
                    errs.append(f"frontmatter 含引号（平台易解析失败）：{line[:46]}")
            m = re.search(r"^name: (\S+)", fm, re.M)
            if m and m.group(1).strip() != ROOT_NAME:
                errs.append(
                    f"目录名({ROOT_NAME}) 与 frontmatter name({m.group(1)}) 不一致"
                )
    return errs


def collect() -> list:
    """遍历技能目录，返回待打包文件（Path 列表，已排序）。"""
    picked = []
    for dirpath, dirnames, filenames in os.walk(SKILL_DIR):
        # 就地剪枝，避免走进排除目录
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS)

        for name in filenames:
            if name in EXCLUDE_FILES:
                continue
            if Path(name).suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            picked.append(Path(dirpath) / name)
    return sorted(picked, key=lambda p: str(p.relative_to(SKILL_DIR)).lower())


def arc_name(path: Path, with_prefix: bool) -> str:
    rel = str(path.relative_to(SKILL_DIR)).replace(os.sep, "/")
    return f"{ROOT_NAME}/{rel}" if with_prefix else rel


def human(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} MB"


# ---------- 发布前审查 ----------

# 绝不该出现在发布包里的内容特征
SENSITIVE = (
    ("疑似个人用户名", re.compile(r"Chuan")),
    ("绝对路径（F: 盘）", re.compile(r"\bF:[\\/]")),
    ("绝对路径（C:\\Users）", re.compile(r"C:[\\/]Users")),
    ("旧技能名", re.compile(r"bilibili-toolkit|BILIBILI_TOOLKIT")),
)


def audit(files: list):
    """发布前内容审查，返回 (errors, warnings)。

    这是「内容」审查，与 validate() 的「结构」审查互补——
    结构对了不代表内容干净，个人信息混进去照样是事故。
    """
    errors, warnings = [], []

    # 1) 敏感痕迹：个人路径、用户名、旧命名
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = p.relative_to(SKILL_DIR)
        for label, rx in SENSITIVE:
            for m in rx.finditer(text):
                line = text[: m.start()].count("\n") + 1
                errors.append(f"{rel}:{line} 命中「{label}」")

    # 2) 文档引用的脚本必须真的在包里
    doc = ""
    for name in ("SKILL.md", "README.md"):
        q = SKILL_DIR / name
        if q.exists():
            doc += q.read_text(encoding="utf-8", errors="ignore")
    packed = {str(p.relative_to(SKILL_DIR)).replace(os.sep, "/") for p in files}
    for ref in sorted(set(re.findall(r"scripts/[A-Za-z_]+\.py", doc))):
        if ref not in packed:
            errors.append(f"文档引用了不存在的脚本：{ref}")

    # 3) 分类规则里不该带开发者自己的数据
    rf = SKILL_DIR / "assets" / "organize-rules.json"
    if rf.exists():
        try:
            data = json.loads(rf.read_text(encoding="utf-8"))
            ups = data.get("entertainment_uppers") or []
            if ups:
                warnings.append(
                    f"assets/organize-rules.json 里有 {len(ups)} 个 UP主兜底名单，"
                    f"确认不是从自己账号提取的个人数据再发布"
                )
            if not data.get("folders"):
                warnings.append(
                    "assets/organize-rules.json 的 folders 为空，使用者将无法分类")
        except Exception as e:
            errors.append(f"assets/organize-rules.json 解析失败：{e}")

    # 4) 长数字串可能是账号 / 收藏夹 ID
    for p in files:
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".ico"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for num in sorted(set(re.findall(r"\d{7,}", text))):
            warnings.append(
                f"{p.relative_to(SKILL_DIR)} 含长数字串 {num}，确认不是账号/收藏夹 ID")

    # 5) 图片不该夹带文本元数据（软件名、原始路径等）
    for p in files:
        if p.suffix.lower() != ".png":
            continue
        raw = p.read_bytes()
        for tag in (b"tEXt", b"iTXt", b"zTXt"):
            if tag in raw:
                warnings.append(
                    f"{p.relative_to(SKILL_DIR)} 含 PNG 文本块 {tag.decode()}，"
                    f"可能携带软件或路径信息")

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="bilibili-curator 打包")
    ap.add_argument("--out", help="输出 zip 路径")
    ap.add_argument("--list", action="store_true", help="只列清单，不打包")
    ap.add_argument("--check", action="store_true",
                    help="只做发布前审查，不打包")
    ap.add_argument("--prefix", action="store_true",
                    help="套一层 <name>/ 目录（默认平铺：SKILL.md 直接放 zip 根目录）")
    ap.add_argument("--limit", type=float, default=SIZE_LIMIT_MB,
                    help=f"体积上限 MB（默认 {SIZE_LIMIT_MB}）")
    args = ap.parse_args()

    version = read_version()
    print(f"技能名称：{ROOT_NAME}")
    print(f"版本号：  v{version}")
    print(f"源目录：  {SKILL_DIR}")
    print()

    errs = validate()
    if errs:
        print("❌ 打包前自检未通过：")
        for e in errs:
            print(f"   · {e}")
        return 1

    files = collect()
    if not files:
        print("❌ 没有可打包的文件")
        return 1

    # ---- 发布前审查（内容层） ----
    a_errs, a_warns = audit(files)
    print("发布前审查：")
    if a_errs:
        print("  ❌ 必须修复：")
        for e in a_errs:
            print(f"     · {e}")
    if a_warns:
        print("  ⚠️  请确认：")
        for w in a_warns:
            print(f"     · {w}")
    if not a_errs and not a_warns:
        print("  ✅ 未发现问题")
    print()

    if a_errs:
        print("❌ 审查未通过，已中止打包（个人信息/断链不能进发布包）。")
        return 1
    if args.check:
        print("（--check 模式：仅审查，未打包）")
        return 0

    # ---- 清单 ----
    print("待打包文件：")
    raw_total = 0
    for p in files:
        size = p.stat().st_size
        raw_total += size
        print(f"  {arc_name(p, args.prefix):<48} {human(size):>10}")
    print(f"  {'─' * 48} {'─' * 10}")
    print(f"  {'合计 ' + str(len(files)) + ' 个文件':<48} {human(raw_total):>10}")
    print()

    if args.list:
        return 0

    # ---- 打包 ----
    out = Path(args.out) if args.out else (
        SKILL_DIR / "dist" / f"{ROOT_NAME}-v{version}.zip"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            z.write(p, arc_name(p, args.prefix))

    # ---- 校验 ----
    bad = zipfile.ZipFile(out).testzip()
    if bad:
        print(f"❌ 压缩包损坏，首个异常项：{bad}")
        return 1

    size = out.stat().st_size
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    ratio = (1 - size / raw_total) * 100 if raw_total else 0

    print("打包完成：")
    print(f"  输出：    {out}")
    print(f"  包内文件：{len(files)} 个")
    print(f"  原始大小：{human(raw_total)}")
    print(f"  压缩后：  {human(size)}（压缩率 {ratio:.1f}%）")
    print(f"  SHA256：  {sha}")

    limit = args.limit * 1024 * 1024
    if size > limit:
        print()
        print(f"❌ 体积超限：{human(size)} > {args.limit} MB")
        print("   请检查是否误把 .data/ 或 .venv/ 打进去了。")
        return 1

    print()
    print(f"✅ 体积合规（{human(size)} / 上限 {args.limit} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
