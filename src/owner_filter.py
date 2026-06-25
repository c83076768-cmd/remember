"""
========================================
owner_filter.py — 多 AI 记忆隔离（owner 字段）
========================================

为支持多 AI 共享同一 Ombre-Brain 实例，给记忆桶增加 owner 字段：
  - "alove"  → Alove 的私有记忆
  - "pearl"  → Pearl 的私有记忆
  - "shared" → 群聊/共享记忆（所有 AI 都可读）

关键行为：
- create() 写入 owner（调用方指定，默认 shared）
- search() 按 owner 预筛（支持逗号分隔的 OR 查询，如 "alove,shared"）
- 老数据没有 owner 字段 → 视为 "shared"（向后兼容）

实现策略（最小侵入 + 抗上游更新）：
- 用 contextvars 在 MCP 工具入口（server.py breath/hold）设置当前 owner
- bucket_manager.create/search 自动读取上下文作为默认值
- surface_default / surface_feels 等用 list_all() 的路径，读上下文过滤
- 中间层（dispatch/store_core/merge_or_create）完全不用改 → rebase 零冲突

不做什么（边界）：
- 不做权限校验（MCP 调用方默认可信）
- 不修改桶的 domain/tags（owner 是独立维度）

对外暴露：parse_owner_param / bucket_matches_owner / apply_owner_to_meta
          set_current_owner / reset_current_owner / get_current_owner
          filter_buckets_by_context_owner
========================================
"""

import contextvars
from typing import Optional, Set, List


# 默认 owner：老数据无 owner 字段时视为共享，保证向后兼容
DEFAULT_OWNER = "shared"

# 当前请求的 owner 上下文（asyncio 安全，每个请求独立）
_current_owner: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "_current_owner", default=None
)


def set_current_owner(owner: Optional[str]) -> contextvars.Token:
    """设置当前请求的 owner 上下文，返回 token 用于 reset。"""
    return _current_owner.set(owner)


def reset_current_owner(token: contextvars.Token) -> None:
    """重置 owner 上下文（配合 set_current_owner 使用）。"""
    _current_owner.reset(token)


def get_current_owner() -> Optional[str]:
    """读取当前请求的 owner 上下文（None = 未设置，不过滤）。"""
    return _current_owner.get()


def parse_owner_param(owner_str: Optional[str]) -> Optional[Set[str]]:
    """
    解析 owner 参数为集合。
    逗号分隔，支持 OR 查询：如 "alove,shared" → {"alove", "shared"}
    返回 None 表示不过滤（查所有 owner）。
    """
    if owner_str is None:
        return None
    parts = {p.strip().lower() for p in str(owner_str).split(",") if p.strip()}
    return parts or None


def get_bucket_owner(meta: dict) -> str:
    """
    读取桶的 owner，老数据无 owner 字段时返回 DEFAULT_OWNER（shared）。
    """
    owner = meta.get("owner")
    if not owner:
        return DEFAULT_OWNER
    return str(owner).strip().lower()


def bucket_matches_owner(meta: dict, owner_set: Optional[Set[str]]) -> bool:
    """
    检查桶是否匹配 owner 集合。
    owner_set 为 None 或空集合 → 不过滤（返回 True，查所有）
    """
    if not owner_set:
        return True
    return get_bucket_owner(meta) in owner_set


def apply_owner_to_meta(meta: dict, owner: Optional[str]) -> None:
    """
    写入 owner 到元数据（原地修改）。
    owner 为 None 或空 → 写入 DEFAULT_OWNER（shared）
    """
    if owner and str(owner).strip():
        meta["owner"] = str(owner).strip().lower()
    else:
        meta["owner"] = DEFAULT_OWNER


def filter_buckets_by_context_owner(buckets: List[dict]) -> List[dict]:
    """
    根据当前上下文 owner 过滤桶列表（用于 list_all() 路径）。
    无上下文 → 返回原列表（不过滤）。
    有上下文 → 只保留匹配 owner 的桶。
    """
    ctx_owner = get_current_owner()
    if not ctx_owner:
        return buckets
    owner_set = parse_owner_param(ctx_owner)
    if not owner_set:
        return buckets
    return [b for b in buckets if bucket_matches_owner(b.get("metadata", {}), owner_set)]
