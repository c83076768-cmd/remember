"""
========================================
web/reranker.py — Reranker 配置与模型列表（插件模块）
========================================
- /api/reranker/config:  GET 返回 reranker 状态；POST 保存 key/base_url/model
- /api/reranker/models:  用当前 key+base_url 拉取可用模型列表
- /api/reranker/test:    测试 rerank 端点连通性

设计原则（插件化）：
- 本模块是「新增文件」，不修改 upstream 的任何路由。
- 通过 web/_shared.py 访问 config / reranker_engine，避免循环 import。
- reranker_engine 实例由 server.py 启动时注入到 sh.reranker_engine。
- 若 reranker_engine 为 None（未启用），所有接口返回 503。

对外暴露：register(mcp)
========================================
"""

from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from . import _shared as sh

logger = sh.logger

try:
    from errors import OBStartupError  # type: ignore
except ImportError:  # pragma: no cover
    from ..errors import OBStartupError  # type: ignore


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def register(mcp) -> None:

    @mcp.custom_route("/api/reranker/config", methods=["GET"])
    async def api_reranker_config_get(request: Request) -> Response:
        err = sh._require_auth(request)
        if err:
            return err
        rr_engine = getattr(sh, "reranker_engine", None)
        rr_cfg = sh.config.get("reranker", {}) or {}
        emb_cfg = sh.config.get("embedding", {}) or {}

        # 生效值（reranker 优先，回退 embedding）
        effective_api_key = str(rr_cfg.get("api_key") or emb_cfg.get("api_key") or "")
        effective_base_url = str(rr_cfg.get("base_url") or emb_cfg.get("base_url") or "").rstrip("/")

        has_own = bool(rr_cfg.get("api_key"))
        api_ready = bool(effective_api_key and effective_base_url)

        return JSONResponse({
            "ok": True,
            "enabled": rr_engine.enabled if rr_engine else False,
            "model": rr_cfg.get("model") or "Qwen/Qwen3-Reranker-4B",
            "base_url": rr_cfg.get("base_url") or "",
            "api_key_masked": _mask_key(effective_api_key),
            "has_own_api_key": has_own,
            "api_ready": api_ready,
            "effective_base_url": effective_base_url,
            "score_weight": rr_cfg.get("score_weight", 0.65),
            "candidate_limit": rr_cfg.get("candidate_limit", 40),
        })

    @mcp.custom_route("/api/reranker/config", methods=["POST"])
    async def api_reranker_config_post(request: Request) -> Response:
        err = sh._require_auth(request)
        if err:
            return err
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON body"}, status_code=400)

        api_key = str(body.get("api_key", "")).strip()
        base_url = str(body.get("base_url", "")).strip().rstrip("/")
        model = str(body.get("model", "")).strip()
        enabled = body.get("enabled")

        # Sentinel "__use_current_reranker__": 不修改 key
        if api_key == "__use_current_reranker__":
            api_key = ""

        updates_env = {}
        if api_key:
            updates_env["OMBRE_RERANKER_API_KEY"] = api_key
        if base_url:
            updates_env["OMBRE_RERANKER_BASE_URL"] = base_url
        if model:
            updates_env["OMBRE_RERANKER_MODEL"] = model
        if enabled is not None:
            updates_env["OMBRE_RERANKER_ENABLED"] = "1" if enabled else "0"

        if not updates_env:
            return JSONResponse({"error": "no fields to update"}, status_code=400)

        # 复用 /api/env-config 的逻辑：写 .env + 更新 config + 热重建（config_api 已内置 reranker 热重建）
        import httpx as _httpx
        from starlette.requests import Request as _Req

        # 直接调用内部逻辑（不走 HTTP，避免自调用）
        # 构造一个伪请求让 api_env_config_set 处理 —— 但更简单的方式是直接写
        _env_path = sh._project_env_path()
        import os as _os
        for var, val in updates_env.items():
            _os.environ[var] = val
            # 更新进程内 config
            meta_map = {
                "OMBRE_RERANKER_API_KEY":  ("reranker", "api_key"),
                "OMBRE_RERANKER_BASE_URL": ("reranker", "base_url"),
                "OMBRE_RERANKER_MODEL":    ("reranker", "model"),
                "OMBRE_RERANKER_ENABLED":  ("reranker", "enabled"),
            }
            if var in meta_map:
                section, key = meta_map[var]
                sh.config.setdefault(section, {})[key] = val

        # 写 .env 文件
        try:
            _write_env_vars(_env_path, updates_env)
        except Exception as e:
            logger.error(f"[reranker] write .env failed: {e}")

        # 写 config.yaml
        try:
            import yaml as _yaml
            _cfg_path = _os.path.join(sh.repo_root, "config.yaml")
            _save = {}
            if _os.path.exists(_cfg_path):
                with open(_cfg_path, "r", encoding="utf-8") as _f:
                    _save = _yaml.safe_load(_f) or {}
            _sec = _save.setdefault("reranker", {})
            rr_cfg = sh.config.get("reranker", {}) or {}
            for k, v in rr_cfg.items():
                _sec[k] = v
            with open(_cfg_path, "w", encoding="utf-8") as _f:
                _yaml.dump(_save, _f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            logger.error(f"[reranker] write config.yaml failed: {e}")

        # 热重建 reranker_engine
        try:
            from reranker_engine import RerankerEngine
            new_engine = RerankerEngine(sh.config)
            sh.reranker_engine = new_engine  # type: ignore[attr-defined]
            try:
                import tools._runtime as _rt
                _rt.reranker_engine = new_engine
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"[reranker] rebuild engine failed: {e}")

        return JSONResponse({"ok": True, "rebuilt": True})

    @mcp.custom_route("/api/reranker/models", methods=["POST"])
    async def api_reranker_models(request: Request) -> Response:
        err = sh._require_auth(request)
        if err:
            return err
        try:
            body = await request.json()
        except Exception:
            body = {}

        api_key = str(body.get("api_key", "")).strip()
        base_url = str(body.get("base_url", "")).strip().rstrip("/")

        # Sentinel: 用当前 reranker 生效值
        if api_key == "__use_current_reranker__":
            rr_engine = getattr(sh, "reranker_engine", None)
            api_key = getattr(rr_engine, "api_key", "") if rr_engine else ""
            if not api_key:
                emb_cfg = sh.config.get("embedding", {}) or {}
                api_key = str(emb_cfg.get("api_key") or "")
        if not api_key:
            rr_engine = getattr(sh, "reranker_engine", None)
            api_key = getattr(rr_engine, "api_key", "") if rr_engine else ""

        if not base_url:
            rr_engine = getattr(sh, "reranker_engine", None)
            base_url = getattr(rr_engine, "base_url", "") if rr_engine else ""
        if not base_url:
            emb_cfg = sh.config.get("embedding", {}) or {}
            base_url = str(emb_cfg.get("base_url") or "").rstrip("/")

        if not api_key or not base_url:
            return JSONResponse(
                {"error": "缺少 API Key 或 Base URL（reranker 和 embedding 均未配置）"},
                status_code=400,
            )

        # 用 OpenAI 兼容的 /models 端点拉列表（与 embedding 一致）
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            hint = ""
            if status == 401:
                hint = " — API Key 无效或已过期"
            elif status == 403:
                hint = " — 无权限访问此端点"
            return JSONResponse(
                {"error": f"上游返回 {status}{hint}", "body": exc.response.text[:500]},
                status_code=502,
            )
        except Exception as exc:
            return JSONResponse({"error": f"请求失败: {exc}"}, status_code=502)

        models = []
        for item in data.get("data", []) if isinstance(data, dict) else []:
            mid = item.get("id", "") if isinstance(item, dict) else ""
            if mid:
                models.append(mid)
        models.sort()
        return JSONResponse({"ok": True, "models": models, "count": len(models)})

    @mcp.custom_route("/api/reranker/test", methods=["POST"])
    async def api_reranker_test(request: Request) -> Response:
        err = sh._require_auth(request)
        if err:
            return err
        rr_engine = getattr(sh, "reranker_engine", None)
        if not rr_engine or not rr_engine.enabled:
            return JSONResponse({"error": "reranker 未启用（缺少 key/base_url）"}, status_code=400)

        try:
            results = await rr_engine.rerank(
                "test query",
                ["hello world", "goodbye world"],
                top_n=2,
            )
            return JSONResponse({
                "ok": True,
                "results": [{"index": r.index, "score": round(r.score, 4)} for r in results],
                "model": rr_engine.model,
                "base_url": rr_engine.base_url,
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)


def _write_env_vars(env_path: str, updates: dict) -> None:
    """把 updates 里的变量写入 .env 文件（保留已有行，只更新/追加）。"""
    import os
    lines = []
    existing = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k = stripped.split("=", 1)[0]
                    existing[k] = True
                    if k in updates:
                        lines.append(f"{k}={updates[k]}\n")
                    else:
                        lines.append(line)
                    continue
                lines.append(line)
    # 追加新变量
    for k, v in updates.items():
        if k not in existing:
            lines.append(f"{k}={v}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
