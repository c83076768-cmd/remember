#!/usr/bin/env python3
"""
migrate_bucket_titles.py — 给旧版记忆桶的 name 加上时间戳前缀

旧版 Ombre Brain 创建的桶 name 没有 "YYYY-MM-DD HH-MM-SS " 前缀。
新版 bucket_manager.py:351 会自动加。本脚本把旧桶的 name 也补上，
时间戳取自桶的 created 字段（保留原始创建时间，不用当前时间）。

用法：
  python3 migrate_bucket_titles.py                    # dry-run，只看不改
  python3 migrate_bucket_titles.py --apply            # 实际修改
  python3 migrate_bucket_titles.py --apply --rename   # 同时重命名 .md 文件
  python3 migrate_bucket_titles.py --dir /path/to/buckets  # 指定 buckets 目录

依赖：仅 Python 3 标准库（不需要 PyYAML / 不需要 Ombre Brain 安装）
"""

import os
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

# 时间戳前缀正则：YYYY-MM-DD HH-MM-SS
TIMESTAMP_RE = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2} ')

# created 字段的各种格式
CREATED_PATTERNS = [
    # 2026-06-24T07:34:23 / 2026-06-24T07:34:23.123456 / 2026-06-24T07:34:23+08:00
    re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})"),
    # 2026-06-24（只有日期）
    re.compile(r"(\d{4}-\d{2}-\d{2})"),
]

# name 字段正则（处理引号和无引号两种情况）
NAME_RE = re.compile(r'^name:\s*(.+?)\s*$', re.MULTILINE)
CREATED_RE = re.compile(r'^created:\s*[\'"]?([^\'"\n]+?)[\'"]?\s*$', re.MULTILINE)

# 文件名中的非法字符（与 bucket_manager 的 sanitize_name 一致）
ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_name(name: str) -> str:
    """与 bucket_manager.sanitize_name 一致的清洗逻辑"""
    name = ILLEGAL_CHARS.sub('', name).strip()
    name = re.sub(r'\s+', ' ', name)
    return name[:80] if name else ""


def parse_created_to_timestamp(created_str: str) -> str | None:
    """把 created 字段解析为 'YYYY-MM-DD HH-MM-SS' 格式"""
    if not created_str:
        return None
    created_str = created_str.strip().strip("'\"")
    # 尝试完整时间戳
    for pattern in CREATED_PATTERNS:
        m = pattern.search(created_str)
        if m:
            try:
                if len(m.groups()) >= 2:
                    # 有日期+时间
                    date_part = m.group(1)
                    time_part = m.group(2)
                    # 把 HH:MM:SS 转成 HH-MM-SS（连字符替代冒号）
                    time_part = time_part.replace(':', '-')
                    return f"{date_part} {time_part}"
                else:
                    # 只有日期，补 00-00-00
                    return f"{m.group(1)} 00-00-00"
            except Exception:
                continue
    return None


def read_bucket_file(filepath: Path) -> tuple[str | None, str | None, str]:
    """
    读取 .md 文件，返回 (name, created, raw_content)。
    如果不是有效的 bucket 文件，返回 (None, None, raw)。
    """
    raw = filepath.read_text(encoding='utf-8', errors='replace')

    # 检查是否有 YAML frontmatter（--- 开头）
    if not raw.startswith('---'):
        return None, None, raw

    # 找 frontmatter 结束位置
    parts = raw.split('---', 2)
    if len(parts) < 3:
        return None, None, raw

    frontmatter = parts[1]

    # 提取 name
    name_match = NAME_RE.search(frontmatter)
    name = name_match.group(1).strip().strip("'\"") if name_match else None

    # 提取 created
    created_match = CREATED_RE.search(frontmatter)
    created = created_match.group(1).strip() if created_match else None

    return name, created, raw


def update_bucket_name(raw: str, old_name: str, new_name: str) -> str:
    """把 frontmatter 里的 name 字段替换为新值"""
    # 找到 name 行并替换
    def replacer(m):
        # 保留原有的引号风格
        original = m.group(1)
        if original.strip().startswith("'") and original.strip().endswith("'"):
            return f"name: '{new_name}'"
        elif original.strip().startswith('"') and original.strip().endswith('"'):
            return f'name: "{new_name}"'
        else:
            return f"name: {new_name}"

    return NAME_RE.sub(replacer, raw, count=1)


def generate_new_filename(new_name: str, bucket_id: str, original_ext: str = '.md') -> str:
    """生成新文件名：{sanitized_name}_{id}.md"""
    clean = sanitize_name(new_name)
    if not clean:
        clean = 'unnamed'
    # 文件名长度限制（留出 _{id}.md 的空间）
    max_name_len = 200 - len(bucket_id) - len(original_ext) - 1
    if len(clean) > max_name_len:
        clean = clean[:max_name_len]
    return f"{clean}_{bucket_id}{original_ext}"


def extract_bucket_id(raw: str) -> str | None:
    """从 frontmatter 提取 bucket id"""
    parts = raw.split('---', 2)
    if len(parts) < 3:
        return None
    frontmatter = parts[1]
    id_match = re.search(r'^id:\s*[\'"]?([^\'"\n]+?)[\'"]?\s*$', frontmatter, re.MULTILINE)
    return id_match.group(1).strip() if id_match else None


def main():
    parser = argparse.ArgumentParser(
        description='给旧版记忆桶的 name 加上时间戳前缀（取自 created 字段）'
    )
    parser.add_argument(
        '--dir', default='buckets',
        help='buckets 目录路径（默认: buckets）'
    )
    parser.add_argument(
        '--apply', action='store_true',
        help='实际执行修改（默认 dry-run，只看不改）'
    )
    parser.add_argument(
        '--rename', action='store_true',
        help='同时重命名 .md 文件（默认只改 name 字段，不改文件名）'
    )
    args = parser.parse_args()

    buckets_dir = Path(args.dir).resolve()
    if not buckets_dir.is_dir():
        print(f"错误：目录不存在: {buckets_dir}")
        sys.exit(1)

    print(f"buckets 目录: {buckets_dir}")
    print(f"模式: {'实际修改' if args.apply else 'DRY-RUN（只看不改）'}")
    print(f"重命名文件: {'是' if args.rename else '否'}")
    print()

    # 递归扫描所有 .md 文件
    md_files = sorted(buckets_dir.rglob('*.md'))
    total = len(md_files)
    already_has_ts = 0
    no_created = 0
    updated = 0
    errors = 0

    for filepath in md_files:
        try:
            raw = filepath.read_text(encoding='utf-8', errors='replace')
            name, created, raw_content = read_bucket_file(filepath)

            if name is None:
                # 不是有效的 bucket 文件（没有 frontmatter 或没有 name 字段）
                continue

            # 检查是否已有时间戳前缀
            if TIMESTAMP_RE.match(name):
                already_has_ts += 1
                continue

            # 解析 created 字段获取时间戳
            if not created:
                no_created += 1
                print(f"  跳过（无 created 字段）: {filepath.name}  name={name[:50]}")
                continue

            timestamp = parse_created_to_timestamp(created)
            if not timestamp:
                no_created += 1
                print(f"  跳过（created 格式无法解析）: {filepath.name}  created={created}")
                continue

            # 构造新 name
            if name and name != 'unnamed':
                new_name = f"{timestamp} {sanitize_name(name)}"
            else:
                new_name = timestamp
            new_name = new_name[:80]  # 与 bucket_manager 一致的长度限制

            print(f"  {'✓修改' if args.apply else '预览'}: {filepath.name}")
            print(f"    旧: {name[:60]}")
            print(f"    新: {new_name[:60]}")

            if args.apply:
                # 更新文件内容
                updated_raw = update_bucket_name(raw_content, name, new_name)
                filepath.write_text(updated_raw, encoding='utf-8')

                # 可选：重命名文件
                if args.rename:
                    bucket_id = extract_bucket_id(raw_content)
                    if bucket_id:
                        new_filename = generate_new_filename(new_name, bucket_id)
                        new_filepath = filepath.parent / new_filename
                        if new_filepath != filepath:
                            if new_filepath.exists():
                                print(f"    ⚠ 文件名冲突，跳过重命名: {new_filename}")
                            else:
                                filepath.rename(new_filepath)
                                print(f"    文件重命名: → {new_filename}")

                updated += 1
        except Exception as e:
            errors += 1
            print(f"  ✗ 错误: {filepath.name} — {e}")

    print()
    print("=" * 50)
    print(f"总计: {total} 个 .md 文件")
    print(f"  已有时间戳前缀（跳过）: {already_has_ts}")
    print(f"  无 created 字段（跳过）: {no_created}")
    print(f"  {'已修改' if args.apply else '待修改'}: {updated}")
    print(f"  错误: {errors}")
    if not args.apply and updated > 0:
        print()
        print("这是 DRY-RUN 预览。确认无误后加 --apply 实际执行：")
        print(f"  python3 {sys.argv[0]} --dir {args.dir} --apply")
        if not args.rename:
            print("  如需同时重命名 .md 文件，加 --rename")


if __name__ == '__main__':
    main()
