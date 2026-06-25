# Ombre-Brain Custom 改造日志

> **用途**：记录 custom 分支相对 upstream（`origin/main`）的所有改动，供上游更新时快速审查兼容性。
> **最后更新**：2026-06-25（基于 v2.3.11）
> **维护方式**：每次新增 custom 改动或合并上游后，更新对应章节。

---

## 快速摘要

| 改造模块 | 新建文件 | 修改文件 | 状态 |
|----------|---------|---------|------|
| Reranker 重排序引擎 | `src/reranker_engine.py`, `src/web/reranker.py` | `server.py`, `tools/_runtime.py`, `tools/breath/search.py`, `web/__init__.py`, `web/_shared.py`, `web/config_api.py`, `frontend/dashboard.html` | 已完成 |
| 多 AI 记忆隔离 (owner) | `src/owner_filter.py` | `server.py`, `bucket_manager.py`, `tools/breath/search.py`, `tools/breath/feel.py`, `tools/breath/importance.py`, `tools/breath/surface.py` | 已完成 |
| 域 / Domain 时间线视图 | `seed_mock_data.py`（mock 数据脚本，可选） | `web/buckets.py`, `frontend/dashboard.html` | 已完成 |

**总计**：4 个新建文件 + 12 个修改文件。

---

## 改造三：域 / Domain 时间线视图

### 目的

在 dashboard 的「记忆网络」旁新增「域」标签页，按时间线展示记忆桶，支持按 owner（A.L. / Pearl / Shared）筛选、关键词搜索、类型过滤（钉选/重要/feel），并显示记忆池统计。

### 修改文件

#### 1. `src/web/buckets.py`

- 在 `/api/buckets` 响应中新增 3 个字段：
  - `owner`：记忆池归属（`a.l.` / `pearl` / `shared`）
  - `protected`：保护标记
  - `event_time`：事件时间（用于时间线排序）

#### 2. `frontend/dashboard.html`

- **CSS**：`.domain-view`、`.domain-toolbar`、`.domain-owner-btn`、`.tl-row`、`.tl-group` 等样式
- **HTML**：新增 `domain-view` 内容区，含 owner 筛选按钮、搜索框、类型过滤、统计标签
- **Tab 切换**：新增 `domain` 标签页，切换时调用 `renderDomainTimeline()`
- **JavaScript**：
  - `renderDomainTimeline()`：按 owner 筛选 → 统计 → 过滤 → 按时间倒序 → 按 YYYY-MM 分组渲染
  - `domainToggleRow()`：点击行展开/折叠详情
  - `domainLoadDetail()`：异步加载桶详情（含 type/importance/owner/created/tags/valence/arousal）
  - `loadBuckets()` 完成后自动刷新域视图（如可见）

### 新建文件

#### `seed_mock_data.py`（可选，mock 数据脚本）

- 向 Ombre Brain 插入 45 条模拟记忆桶（15 A.L. + 10 Pearl + 12 Shared + 8 Feel）
- 时间戳为过去 1-30 天内（避免被衰减引擎归档）
- 20% 概率 pinned，10% 概率 protected
- 用 `__mock__` tag 标记，支持 `--clean` 物理清理
- **用法**：`python seed_mock_data.py`（插入）/ `python seed_mock_data.py --clean`（清理）

### 上游更新检查清单

- [ ] `web/buckets.py` 的 `/api/buckets` 响应结构是否变化 → 确认 `owner`/`protected`/`event_time` 字段仍在
- [ ] `frontend/dashboard.html` 的 tab 切换逻辑是否变化 → 确认 `domain` tab 和 `renderDomainTimeline()` 调用仍在
- [ ] `loadBuckets()` 函数是否变化 → 确认域视图刷新钩子仍在

---

## 改造一：Reranker 重排序引擎

### 目的

在 `breath` 检索召回候选桶后，用 reranker 模型（如 `BAAI/bge-reranker-v2-m3`）做二次精排，提升记忆召回质量。未配置或调用失败时自动降级到原排序，不影响主流程。

### 新建文件

#### 1. `src/reranker_engine.py`（142 行）

- **类**：`RerankerEngine`
- **配置优先级**：`reranker.*` > `embedding.*` > `dehydration.*`（留空时自动复用 embedding 的 key/base_url）
- **核心方法**：`async rerank(query, documents, top_n) -> list[RerankResult]`
- **降级策略**：`enabled=False` 或调用异常时返回空列表，调用方保持原排序
- **配置项**（`config.yaml` → `reranker` 节）：
  - `model`：reranker 模型名（默认 `Qwen/Qwen3-Reranker-4B`）
  - `base_url` / `api_key`：端点地址和密钥
  - `enabled`：是否启用（默认 `True`，前提是有 key+url）
  - `candidate_limit`：参与重排的最大候选数（默认 40）
  - `score_weight`：rerank 分数与原始分数的混合权重（默认 0.65）
  - `timeout_seconds`：超时（默认 12s）

#### 2. `src/web/reranker.py`（279 行）

- Dashboard 后端 API，提供 reranker 配置管理：
  - `GET /api/reranker/config` — 返回 reranker 状态和配置
  - `POST /api/reranker/config` — 保存 key/base_url/model/enabled
  - `GET /api/reranker/models` — 拉取可用模型列表
  - `POST /api/reranker/test` — 测试 rerank 端点连通性

### 修改文件

#### 3. `src/server.py`

- **L341-347**：启动时初始化 `RerankerEngine` 并注入到 `tools._runtime` 和 `web._shared`
- **L360**：`_t_breath` 构造时传入 `reranker_engine`
- **L556**：`_t_breath` 重建时传入 `reranker_engine`

#### 4. `src/tools/_runtime.py`

- **L37**：新增 `reranker_engine: Any = None` 全局槽位

#### 5. `src/tools/breath/search.py`

- **L87-114**：在向量搜索完成后、结果排序前插入 reranker 重排序逻辑
  - 取 `candidate_limit` 个候选，构造 `name + content[:500]` 作为 document
  - 调用 `rr_engine.rerank()`，按 `score_weight` 混合原始分数和 rerank 分数
  - 失败时 warning 日志，保持原排序

#### 6. `src/web/__init__.py`

- **L32**：`from . import reranker`
- **L53**：`reranker.register(mcp)` 注册路由

#### 7. `src/web/_shared.py`

- **L83**：新增 `reranker_engine = None` 共享槽位

#### 8. `src/web/config_api.py`

- **L473-476**：新增 4 个 reranker 环境变量映射（`OMBRE_RERANKER_*`）
- **L483**：新增 reranker 配置变更说明
- **L663-676**：reranker 配置变更时热重建 `reranker_engine` 实例

#### 9. `frontend/dashboard.html`

- 新增 Reranker 配置面板（+244 行）：key/base_url/model/enabled 输入、模型列表拉取、连通性测试、状态显示

### 上游更新时需检查

| 上游改动点 | 检查内容 |
|-----------|---------|
| `tools/breath/search.py` 的搜索流程 | reranker 插入点（L87-114）是否仍在正确的位置（向量搜索之后、结果截断之前） |
| `server.py` 的工具初始化流程 | `reranker_engine` 注入是否被上游重构打断 |
| `tools/_runtime.py` 的全局槽位 | 上游是否新增/重命名槽位导致 `reranker_engine` 被覆盖 |
| `web/__init__.py` 的模块注册 | `register_all()` 是否被上游重构导致 reranker 注册丢失 |
| `web/config_api.py` 的环境变量表 | 上游是否重构 env 映射结构导致 reranker 变量丢失 |
| `frontend/dashboard.html` | 合并冲突时优先保留 custom 的 reranker 面板代码 |

### 降级安全性

- reranker 未配置 → `enabled=False` → `rerank()` 返回 `[]` → search.py 跳过重排序
- reranker 调用超时/异常 → warning 日志 → 保持原排序
- reranker_engine 初始化失败 → `server.py` L346 warning → `reranker_engine=None` → search.py L89 `getattr` 返回 None → 跳过

---

## 改造二：多 AI 记忆隔离（owner 字段）

### 目的

支持多个 AI（A爱 / Null）共享同一 Ombre-Brain 实例，通过 `owner` 字段实现记忆读写隔离：
- `a.l.` — A爱 私有记忆
- `null` — Null 私有记忆
- `shared` — 群聊共享记忆（所有 AI 可读）

### 隔离规则

| 场景 | 写入 owner | 读取 owner |
|------|-----------|-----------|
| A爱私聊 | `a.l.` | `a.l.,shared` |
| Null私聊 | `null` | `null,shared` |
| 群聊 | `shared` | `shared` |

### 新建文件

#### 1. `src/owner_filter.py`（115 行）

- **上下文管理**：`set_current_owner` / `reset_current_owner` / `get_current_owner`（基于 `contextvars.ContextVar`，asyncio 安全）
- **参数解析**：`parse_owner_param("a.l.,shared")` → `{"a.l.", "shared"}`
- **元数据写入**：`apply_owner_to_meta(meta, owner)` — 写入 `meta["owner"]`
- **桶匹配**：`bucket_matches_owner(meta, owner_set)` — 检查桶是否属于指定 owner
- **列表过滤**：`filter_buckets_by_context_owner(buckets)` — 按当前上下文 owner 过滤桶列表
- **向后兼容**：老数据无 `owner` 字段 → 视为 `shared`

### 修改文件

#### 2. `src/server.py`

- **L58-59**：`from owner_filter import set_current_owner, reset_current_owner`
- **`breath` 工具（L575-594）**：新增 `owner: Optional[str] = ""` 参数，`set_current_owner` → 执行 → `reset_current_owner`
- **`hold` 工具（L608-628）**：同上模式
- **`grow` 工具（L634-645）**：同上模式

#### 3. `src/bucket_manager.py`

- **`create()` 方法**：调用 `apply_owner_to_meta()` 在创建桶时写入 owner 字段
- **`search()` 方法**：在候选集合并后、语义打分前，按 `get_current_owner()` 上下文预筛候选桶

#### 4. `src/tools/breath/search.py`

- **import**：`from owner_filter import filter_buckets_by_context_owner`（与 reranker 同文件，不同 import）
- **搜索结果过滤**：在 `list_all()` 之后调用 `filter_buckets_by_context_owner()` 过滤

#### 5. `src/tools/breath/feel.py`

- **import + L26**：`list_all()` 后调用 `filter_buckets_by_context_owner()` 过滤 feel 类记忆

#### 6. `src/tools/breath/importance.py`

- **import + L38**：`list_all()` 后调用 `filter_buckets_by_context_owner()` 过滤

#### 7. `src/tools/breath/surface.py`

- **import + L51**：`list_all()` 后调用 `filter_buckets_by_context_owner()` 过滤

### 上游更新时需检查

| 上游改动点 | 检查内容 |
|-----------|---------|
| `server.py` 的 `breath`/`hold`/`grow` 函数签名 | 上游是否新增参数导致 owner 参数位置变化；try/finally 结构是否被重构 |
| `bucket_manager.py` 的 `create()` / `search()` | 上游是否重构这两个方法导致 owner 写入/预筛逻辑丢失 |
| `tools/breath/*.py` 的 `list_all()` 调用 | 上游是否改用其他方法获取桶列表，导致 `filter_buckets_by_context_owner` 无处插入 |
| `owner_filter.py` 的 import 路径 | 上游是否调整模块结构导致 `from owner_filter import ...` 失败 |

### 降级安全性

- `owner` 参数为空 → `set_current_owner(None)` → 上下文为 None → `filter_buckets_by_context_owner` 返回原列表（不过滤）→ **行为与 upstream 完全一致**
- `owner_filter.py` import 失败 → `server.py` 启动报错（需修复，不会静默降级）
- 老数据无 owner 字段 → `get_bucket_owner()` 返回 `shared` → 所有 AI 都可读

---

## 上游更新操作流程

```bash
# 1. 拉取上游
git fetch origin

# 2. 查看新提交
git log --oneline custom..origin/main

# 3. 查看改了哪些文件
git diff --stat custom..origin/main

# 4. 合并（优先 merge，保留 custom 历史）
git merge --no-edit origin/main

# 5. 如有冲突，优先保留 custom 侧的 owner/reranker 代码
#    冲突文件参考本日志的"修改文件"列表

# 6. 合并后验证 custom 改造是否完好
#    - 检查 owner_filter.py 是否存在
#    - 检查 server.py 的 breath/hold/grow 是否有 owner 参数
#    - 检查 reranker_engine.py 是否存在
#    - 检查 tools/breath/search.py 的 reranker 和 owner 过滤代码
#    - 启动服务确认无 import 错误
```

---

## 版本历史

| 日期 | 上游版本 | 操作 | 说明 |
|------|---------|------|------|
| 2026-06-25 | v2.3.11 | 合并 v2.3.10 + v2.3.11 | 无冲突。改动：VERSION 同步、embedding 模型名归一化、热更新 VERSION 同步。不影响 custom 改造 |
| 2026-06-25 | v2.3.9 | 合并 v2.3.8 + v2.3.9 | 无冲突。改动：bucket_manager update() unpin demote、dehydrator perspective rule、web/meta 热更新重启。不影响 custom 改造 |
| 2026-06-25 | v2.3.8 | 新增 grow owner 参数 | 给 `grow` 工具添加 `owner` 参数，与 breath/hold 相同的 set/reset 模式 |
| 2026-06-25 | v2.3.8 | 清理临时文件 | 删除 `demo_owner_isolation.py`、`tests/test_reranker_debug.py`、`tests/test_reranker_compare.py`、`tests/test_output.txt` |
| 更早 | — | reranker 引擎集成 | `reranker_engine.py` + `web/reranker.py` + search.py 接入 + dashboard 面板 |
| 更早 | — | owner 隔离集成 | `owner_filter.py` + breath/hold owner 参数 + bucket_manager owner 读写 + breath 子模块过滤 |
