"""
========================================
parallel_dehydrate.py — 并行脱水 helper（custom 改造七）
========================================

把 tools/breath/search.py 里顺序 for-await dehydrate 改为 asyncio.gather 并行，
N 条记忆的脱水耗时从 N×3s 降到 ≈最慢一条（3-5s）。

设计要点：
- Semaphore(8) 限并发，避免 Gemini 免费层 429
- 脱水结果有 SQLite 缓存，已脱过的不重复调 LLM；并行只会多缓存几条
  （一次性成本），不改变返回内容
- return_exceptions=True 保留调用方原有的逐条异常处理逻辑
- 依赖注入：dehydrator / logger 由调用方传入，避免与 tools._runtime 循环 import

对外暴露：
  dehydrate_matches_parallel(matches, q_valence, dehydrator, logger, sem_limit=8)
    → list[(bucket, summary, is_core) | Exception]
  dehydrate_drift_parallel(drifted, dehydrator, logger, sem_limit=8)
    → list[str | Exception]
========================================
"""

import asyncio

from utils import strip_wikilinks


def _raw_core_fallback(content: str) -> str:
    """核心准则桶脱水失败/空摘要时的原始文本兜底。

    与上游 search.py 的 _raw_core_fallback 保持一致实现。
    """
    return strip_wikilinks(content)[:300].strip() or "（空记忆）"


async def dehydrate_matches_parallel(matches, q_valence, dehydrator, logger, sem_limit=8):
    """并行脱水所有候选桶。

    返回 list[(bucket, summary, is_core) | Exception]。
    Exception 由调用方按 return_exceptions 语义处理（跳过或记日志）。

    包含：
    - 展示层 valence ±0.1 微调（记忆重构）
    - is_core 桶的 fallback（脱水异常时用原始文本）
    - is_core 桶的空摘要兜底（上游 v2.4.2 新增：脱水成功但返回空字符串时回退）
    """
    sem = asyncio.Semaphore(sem_limit)

    async def _one(bucket):
        async with sem:
            clean_meta = {k: v for k, v in bucket["metadata"].items() if k != "tags"}
            meta_b = bucket["metadata"]
            is_core = (
                meta_b.get("pinned")
                or meta_b.get("protected")
                or meta_b.get("type") == "permanent"
            )
            # --- 记忆重构：根据当前情绪微调展示层 valence（±0.1）---
            if q_valence is not None and "valence" in clean_meta:
                original_v = float(clean_meta.get("valence") or 0.5)
                shift = (q_valence - 0.5) * 0.2
                clean_meta["valence"] = max(0.0, min(1.0, original_v + shift))
            try:
                summary = await dehydrator.dehydrate(
                    strip_wikilinks(bucket["content"]), clean_meta
                )
            except Exception as dehy_err:
                if not is_core:
                    raise
                logger.warning(
                    f"core search result dehydrate failed, using raw fallback: {dehy_err}"
                )
                summary = _raw_core_fallback(bucket["content"])
            # 上游 v2.4.2 新增：is_core 空摘要兜底
            if is_core and not str(summary or "").strip():
                summary = _raw_core_fallback(bucket["content"])
            return (bucket, summary, is_core)

    return await asyncio.gather(
        *[_one(b) for b in matches], return_exceptions=True
    )


async def dehydrate_drift_parallel(drifted, dehydrator, logger, sem_limit=8):
    """并行脱水随机浮现的 drift 桶。

    返回 list[str | Exception]，str 格式为 "[surface_type: random]\\n{summary}"。
    drift 桶不区分 core/non-core，失败直接作为 Exception 返回由调用方跳过。
    """
    sem = asyncio.Semaphore(sem_limit)

    async def _one(b):
        async with sem:
            clean_meta = {k: v for k, v in b["metadata"].items() if k != "tags"}
            summary = await dehydrator.dehydrate(
                strip_wikilinks(b["content"]), clean_meta
            )
            return f"[surface_type: random]\n{summary}"

    return await asyncio.gather(
        *[_one(b) for b in drifted], return_exceptions=True
    )
