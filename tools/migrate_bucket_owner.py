#!/usr/bin/env python3
"""
migrate_bucket_owner.py — 给旧版记忆桶补上 owner 字段

旧版 Ombre Brain 创建的桶没有 owner 字段，新版 owner_filter.py 会把无 owner
的桶视为 "shared"。本脚本给这些桶补上指定 owner（默认 alove）。

用法：
  python3 migrate_bucket_owner.py --dir /path/to/buckets              # dry-run
  python3 migrate_bucket_owner.py --dir /path/to/buckets --apply      # 实际修改
  python3 migrate_bucket_owner.py --dir /path/to/buckets --apply --owner pearl
  python3 migrate_bucket_owner.py --dir /path/to/buckets --apply --force  # 覆盖已有 owner

依赖：仅 Python 3 标准库
"""

import re
import sys
import argparse
from pathlib import Path

OWNER_RE = re.compile(r'^owner:\s*(.+?)\s*$', re.MULTILINE)


def read_bucket_frontmatter(filepath: Path) -> tuple[str | None, str]:
    """
    读取 .md 文件，返回 (owner_value_or_None, raw_content)。
    owner_value 为 None 表示没有 owner 字段。
    """
    raw = filepath.read_text(encoding='utf-8', errors='replace')
    if not raw.startswith('---'):
        return None, raw
    parts = raw.split('---', 2)
    if len(parts) < 3:
        return None, raw
    frontmatter = parts[1]
    m = OWNER_RE.search(frontmatter)
    if m:
        owner = m.group(1).strip().strip("'\"")
        return owner, raw
    return None, raw


def add_owner_to_frontmatter(raw: str, owner: str) -> str:
    """在 frontmatter 开头（第一行 --- 之后）插入 owner 字段"""
    # 找到第一个 --- 的位置
    idx = raw.index('---')
    after = raw[idx + 3:]
    # 如果 --- 后面紧跟换行，在换行后插入
    if after.startswith('\r\n'):
        return raw[:idx + 3] + '\r\nowner: ' + owner + after
    elif after.startswith('\n'):
        return raw[:idx + 3] + '\nowner: ' + owner + after
    else:
        return raw[:idx + 3] + '\nowner: ' + owner + after


def replace_owner_in_frontmatter(raw: str, owner: str) -> str:
    """替换已有的 owner 字段值"""
    def replacer(m):
        original = m.group(1)
        if original.strip().startswith("'") and original.strip().endswith("'"):
            return f"owner: '{owner}'"
        elif original.strip().startswith('"') and original.strip().endswith('"'):
            return f'owner: "{owner}"'
        else:
            return f"owner: {owner}"
    return OWNER_RE.sub(replacer, raw, count=1)


def main():
    parser = argparse.ArgumentParser(
        description='给旧版记忆桶补上 owner 字段（默认 alove）'
    )
    parser.add_argument(
        '--dir', default='buckets',
        help='buckets 目录路径（默认: buckets）'
    )
    parser.add_argument(
        '--owner', default='alove',
        help='要写入的 owner 值（默认: alove）'
    )
    parser.add_argument(
        '--apply', action='store_true',
        help='实际执行修改（默认 dry-run）'
    )
    parser.add_argument(
        '--force', action='store_true',
        help='覆盖已有 owner 值（默认只补缺失的）'
    )
    args = parser.parse_args()

    owner_val = args.owner.strip().lower()
    buckets_dir = Path(args.dir).resolve()
    if not buckets_dir.is_dir():
        print(f"错误：目录不存在: {buckets_dir}")
        sys.exit(1)

    print(f"buckets 目录: {buckets_dir}")
    print(f"目标 owner: {owner_val}")
    print(f"模式: {'实际修改' if args.apply else 'DRY-RUN（只看不改）'}")
    print(f"覆盖已有 owner: {'是' if args.force else '否（只补缺失的）'}")
    print()

    md_files = sorted(buckets_dir.rglob('*.md'))
    total = len(md_files)
    no_owner = 0
    already_correct = 0
    already_has_other = 0
    updated = 0
    skipped_not_bucket = 0
    errors = 0

    for filepath in md_files:
        try:
            owner, raw = read_bucket_frontmatter(filepath)
            if not raw.startswith('---'):
                skipped_not_bucket += 1
                continue

            if owner is None:
                # 没有 owner 字段，需要补上
                no_owner += 1
                print(f"  {'✓修改' if args.apply else '预览'}: {filepath.name}")
                print(f"    旧: (无 owner)")
                print(f"    新: owner: {owner_val}")
                if args.apply:
                    updated_raw = add_owner_to_frontmatter(raw, owner_val)
                    filepath.write_text(updated_raw, encoding='utf-8')
                    updated += 1
            elif owner.strip().lower() == owner_val:
                # 已经是目标 owner，跳过
                already_correct += 1
            else:
                # 有 owner 但不是目标值
                already_has_other += 1
                if args.force:
                    print(f"  {'✓覆盖' if args.apply else '预览覆盖'}: {filepath.name}")
                    print(f"    旧: owner: {owner}")
                    print(f"    新: owner: {owner_val}")
                    if args.apply:
                        updated_raw = replace_owner_in_frontmatter(raw, owner_val)
                        filepath.write_text(updated_raw, encoding='utf-8')
                        updated += 1
                else:
                    print(f"  跳过（已有 owner={owner}，用 --force 覆盖）: {filepath.name}")
        except Exception as e:
            errors += 1
            print(f"  ✗ 错误: {filepath.name} — {e}")

    print()
    print("=" * 50)
    print(f"总计: {total} 个 .md 文件")
    print(f"  无 owner 字段（{'已补上' if args.apply else '待补'}: {no_owner}")
    print(f"  已是 {owner_val}: {already_correct}")
    print(f"  有其他 owner: {already_has_other}")
    print(f"  非 bucket 文件（跳过）: {skipped_not_bucket}")
    print(f"  {'已修改' if args.apply else '待修改'}: {updated}")
    print(f"  错误: {errors}")
    if not args.apply and (no_owner > 0 or (args.force and already_has_other > 0)):
        print()
        print("这是 DRY-RUN。确认后加 --apply 执行：")
        print(f"  python3 {sys.argv[0]} --dir {args.dir} --owner {owner_val} --apply")


if __name__ == '__main__':
    main()
