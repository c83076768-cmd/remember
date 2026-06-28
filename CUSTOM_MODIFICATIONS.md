# Ombre-Brain Custom 改造日志

> **用途**：记录 custom 分支相对 upstream（`origin/main`）的所有改动，供上游更新时快速审查兼容性。
> **最后更新**：2026-06-29（基于 v2.3.22）
> **维护方式**：每次新增 custom 改动或合并上游后，更新对应章节。

---

## 快速摘要

| 改造模块 | 新建文件 | 修改文件 | 状态 |
|----------|---------|---------|------|
| Reranker 重排序引擎 | `src/reranker_engine.py`, `src/web/reranker.py` | `server.py`, `tools/_runtime.py`, `tools/breath/search.py`, `web/__init__.py`, `web/_shared.py`, `frontend/dashboard.html` | 已完成 |
| 多 AI 记忆隔离 (owner) | `src/owner_filter.py` | `server.py`, `bucket_manager.py`, `tools/breath/search.py`, `tools/breath/feel.py`, `tools/breath/importance.py`, `tools/breath/surface.py` | 已完成 |
| 域 / Domain 时间线视图 | `seed_mock_data.py`（mock 数据脚本，可选） | `web/buckets.py`, `frontend/dashboard.html` | 已完成 |
| Plan/Letter owner 隔离 | 无新建 | `server.py`, `tools/plan/core.py`, `tools/_common.py`, `tools/dream/__init__.py`, `web/hooks.py`, `web/plans.py`, `web/letters.py`, `frontend/dashboard.html` | 已完成 |
| 前端代码抽离（减少冲突） | `frontend/custom.css`, `frontend/custom.js` | `src/web/dashboard.py`, `frontend/dashboard.html` | 已完成 |

**总计**：6 个新建文件 + 22 个修改文件。

---

## 改造三：域 / Domain 时间线视图

### 目的

在 dashboard 的「记忆网络」旁新增「域」标签页，按时间线展示记忆桶，支持按 owner（A.L. / Pearl / Shared）筛选、关键词搜索、类型过滤（钉选/重要/feel），并显示记忆池统计。

### 修改文件

#### 1. `src/web/buckets.py`

- 在 `/api/buckets` 响应中新增 3 个字段：
  - `owner`：记忆池归属（`alove` / `pearl` / `shared`）
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

#### 8. `src/web/config_api.py`（**已迁出，见 `web/reranker.py`**）

> **v2.3.22 同步说明**：reranker 的环境变量映射、配置热重建逻辑已在更早的改造中整体迁到独立模块 `src/web/reranker.py`，`config_api.py` 现已**零 custom 改动**，可与上游自由同步。历史记录保留如下仅供追溯：
>
> - ~~L473-476：新增 4 个 reranker 环境变量映射（`OMBRE_RERANKER_*`）~~
> - ~~L483：新增 reranker 配置变更说明~~
> - ~~L663-676：reranker 配置变更时热重建 `reranker_engine` 实例~~

#### 9. `frontend/dashboard.html`

- 新增 Reranker 配置面板（+244 行）：key/base_url/model/enabled 输入、模型列表拉取、连通性测试、状态显示

### 上游更新时需检查

| 上游改动点 | 检查内容 |
|-----------|---------|
| `tools/breath/search.py` 的搜索流程 | reranker 插入点（L87-114）是否仍在正确的位置（向量搜索之后、结果截断之前） |
| `server.py` 的工具初始化流程 | `reranker_engine` 注入是否被上游重构打断 |
| `tools/_runtime.py` 的全局槽位 | 上游是否新增/重命名槽位导致 `reranker_engine` 被覆盖 |
| `web/__init__.py` 的模块注册 | `register_all()` 是否被上游重构导致 reranker 注册丢失 |
| `web/config_api.py` 的环境变量表 | ~~上游是否重构 env 映射结构导致 reranker 变量丢失~~（v2.3.22：reranker 已迁至 `web/reranker.py`，config_api.py 零 custom 改动，可自由同步） |
| `frontend/dashboard.html` | 合并冲突时优先保留 custom 的 reranker 面板代码 |

### 降级安全性

- reranker 未配置 → `enabled=False` → `rerank()` 返回 `[]` → search.py 跳过重排序
- reranker 调用超时/异常 → warning 日志 → 保持原排序
- reranker_engine 初始化失败 → `server.py` L346 warning → `reranker_engine=None` → search.py L89 `getattr` 返回 None → 跳过

---

## 改造二：多 AI 记忆隔离（owner 字段）

### 目的

支持多个 AI（Alove / Pearl）共享同一 Ombre-Brain 实例，通过 `owner` 字段实现记忆读写隔离：
- `alove` — Alove 私有记忆
- `pearl` — Pearl 私有记忆
- `shared` — 群聊共享记忆（所有 AI 可读）

### 隔离规则

| 场景 | 写入 owner | 读取 owner |
|------|-----------|-----------|
| Alove 私聊 | `alove` | `alove,shared` |
| Pearl 私聊 | `pearl` | `pearl,shared` |
| 群聊 | `shared` | `shared` |

### 新建文件

#### 1. `src/owner_filter.py`（115 行）

- **上下文管理**：`set_current_owner` / `reset_current_owner` / `get_current_owner`（基于 `contextvars.ContextVar`，asyncio 安全）
- **参数解析**：`parse_owner_param("alove,shared")` → `{"alove", "shared"}`
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

## 改造四：Plan / Letter owner 隔离

### 目的

把 plan（计划）和 letter（信件）功能也接入 owner 隔离体系，让 A爱 和 Pearl 各自的计划/信件互不可见。改造前 plan/letter 工具入口完全没接 owner 上下文，存在三个问题：
1. **写入永远落 shared** — A爱 写的计划/信件全落 `owner=shared`，和 Pearl 的混在一起
2. **读取跨 owner 泄露** — A爱 调 `letter_read` 能读到 Pearl 的全部私信
3. **去重跨 owner 误判** — A爱 建计划时，若 Pearl 有相同内容的 active plan，会被误去重到 Pearl 的桶上

### 设计原则

- **owner 和 author 正交**：`author=user/claude` 表示信件方向（原作者设计），`owner=alove/pearl/shared` 表示归属哪个 AI（我们加的）。例：人类写给 Alove 的信 = `author=user, owner=alove`；Alove 写给人类的回信 = `author=claude, owner=alove`
- **工具数量不变**：只在现有 plan/letter_write/letter_read/dream 四个工具的函数签名加 `owner` 可选参数，不新增工具
- **Dashboard 默认看全部**：`/api/plans` 和 `/api/letters` 默认返回所有 owner 的数据（人类视角），传 `?owner=` 才筛选
- **MCP 工具默认按 owner 隔离**：AI 调用时传 owner 才隔离，不传走 shared（向后兼容）

### 修改文件

#### 1. `src/server.py`

- **`plan` 工具**：新增 `owner: Optional[str] = ""` 参数 + `set_current_owner`/`reset_current_owner` 包裹
- **`letter_write` 工具**：同上
- **`letter_read` 工具**：同上
- **`dream` 工具**：同上（因为 dream 末尾展示 active plans + feel 历史，需一并隔离）

#### 2. `src/tools/plan/core.py`

- **import**：`from owner_filter import filter_buckets_by_context_owner`
- **`plan_create` 去重扫描**：`list_all()` 后调用 `filter_buckets_by_context_owner()` 过滤，避免跨 owner 误去重
- **`letter_read` 读取**：`list_all()` 后调用 `filter_buckets_by_context_owner()` 过滤，A爱 只能读到自己 owner 的信件

#### 3. `src/tools/_common.py`

- **import**：`from owner_filter import filter_buckets_by_context_owner`
- **`check_plan_resolution`**（auto-resolve 后台扫描）：`list_all()` 后调用 `filter_buckets_by_context_owner()` 过滤，新事件只匹配同 owner 的 active plan

#### 4. `src/tools/dream/__init__.py`

- **import**：`from owner_filter import filter_buckets_by_context_owner`
- **`dispatch`**：`list_all()` 后调用 `filter_buckets_by_context_owner()` 过滤，dream 只看自己 owner 的记忆/计划/feel

#### 5. `src/web/hooks.py`

- **import**：`parse_owner_param`, `bucket_matches_owner`
- **`/breath-hook`**：新增 `?owner=` 查询参数，信件部分按 owner 过滤（不传 = 不过滤，向后兼容）

#### 6. `src/web/plans.py`

- **import**：`parse_owner_param`, `bucket_matches_owner`, `get_bucket_owner`
- **`/api/plans`**：新增 `?owner=` 查询参数（默认返回全部），响应里新增 `owner` 字段

#### 7. `src/web/letters.py`

- **import**：`parse_owner_param`, `bucket_matches_owner`, `get_bucket_owner`, `apply_owner_to_meta`
- **`/api/letters`**：新增 `?owner=` 查询参数（默认返回全部），响应里新增 `owner` 字段
- **`/api/letter` POST**：支持 body 里传 `owner` 字段写入信件归属

#### 8. `frontend/dashboard.html`

- **计划面板**：加 全部/A爱/Pearl/共享 筛选按钮 + 卡片显示 owner 彩色标签
- **信件面板**：加 owner 筛选按钮 + 写信表单加「归属」下拉框 + 信件卡片显示 owner 标签
- **新增辅助函数**：`_ownerTagHtml(owner)` 生成 owner 彩色小标签（复用 domain timeline 的 `domainOwnerLabel`/`domainOwnerColor`）
- **新增筛选函数**：`setPlanOwnerFilter()` / `setLetterOwnerFilter()`

### 上游更新时需检查

| 上游改动点 | 检查内容 |
|-----------|---------|
| `server.py` 的 `plan`/`letter_write`/`letter_read`/`dream` 函数签名 | 上游是否新增参数导致 owner 参数位置变化；try/finally 结构是否被重构 |
| `tools/plan/core.py` 的 `plan_create`/`letter_read` | 上游是否重构去重/读取逻辑，导致 `filter_buckets_by_context_owner` 无处插入 |
| `tools/_common.py` 的 `check_plan_resolution` | 上游是否改 auto-resolve 流程导致过滤丢失 |
| `tools/dream/__init__.py` 的 `dispatch` | 上游是否改 dream 流程导致过滤丢失 |
| `web/hooks.py` 的 `/breath-hook` | 上游是否重构信件段导致 owner 过滤丢失 |
| `web/plans.py` / `web/letters.py` | 上游是否改 API 响应结构导致 `owner` 字段丢失 |
| `frontend/dashboard.html` | 合并冲突时优先保留 custom 的 owner 筛选按钮和写信表单 owner 下拉框 |

### 降级安全性

- `owner` 参数为空 → `set_current_owner(None)` → `filter_buckets_by_context_owner` 返回原列表 → **行为与 upstream 完全一致**
- Dashboard API 不传 `?owner=` → `owner_set=None` → `bucket_matches_owner` 返回 True → 返回全部
- 老数据无 owner 字段 → `get_bucket_owner()` 返回 `shared` → Dashboard「共享」tab 能看到

---

## 改造五：前端代码抽离（减少 dashboard.html 合并冲突）

### 目的

dashboard.html 是 custom 改造和上游改动冲突最频繁的文件（改造一/三/四都在里面加了 CSS + JS）。把 custom 的 CSS/JS 抽到独立文件后，dashboard.html 里只留两行引用（`<link>` + `<script src>`）和少量侵入点注释，上游改 dashboard.html 主体时几乎不会碰到 custom 代码。

### 新建文件

#### 1. `frontend/custom.css`（约 165 行）

- 域 / Domain Timeline 样式（`.domain-view`、`.tl-*`、`.domain-owner-btn` 等）
- owner 筛选按钮样式（`.domain-owner-btn[data-owner="alove"].active` 等）
- 记忆桶卡片样式

#### 2. `frontend/custom.js`（约 470 行）

集中了 4 块 custom JavaScript：
- **域 / Domain Timeline**：`renderDomainTimeline()`、`domainAttachListeners()`、`domainCleanTitle()`、`escapeHtml()` + `domainState`/`domainOwnerLabel`/`domainOwnerColor`/`_ownerTagHtml` 等辅助函数
- **Plan owner 筛选**：`setPlanOwnerFilter()` + `_planOwnerFilter` 状态
- **Letter owner 筛选**：`setLetterOwnerFilter()` + `_letterOwnerFilter` 状态
- **Reranker UI**：`refreshRrInfo()`、`saveRerankerKey()`、`fetchRerankerModels()`、`testReranker()` + DOMContentLoaded 自动加载

### 修改文件

#### 3. `src/web/dashboard.py`

- **静态文件白名单** `allowed` 字典：新增 `custom.css`（`text/css; charset=utf-8`）和 `custom.js`（`application/javascript; charset=utf-8`）
- 其余静态文件服务逻辑不变（仍走 `/static/{name}` 路由，文件名精确匹配，无路径穿越风险）

#### 4. `frontend/dashboard.html`

- **删除**：原内嵌的 165 行 custom CSS（`/* ── custom: 域 / Domain Timeline 视图 ── */` 到 `.tl-empty`）
- **删除**：原内嵌的 domain JS（`renderDomainTimeline` 等约 200 行）
- **删除**：原内嵌的 plan/letter owner 筛选 JS（`setPlanOwnerFilter`/`setLetterOwnerFilter` 共约 20 行）
- **删除**：原独立 `<script>` 块的 Reranker UI JS（约 190 行）
- **新增**：`</style>` 前加 `<link rel="stylesheet" href="/static/custom.css?v=6">`
- **新增**：`</body>` 前加 `<script src="/static/custom.js?v=5"></script>`
- **侵入点注释**：`loadPlans` / `loadLetters` 里的 owner 过滤行前加 `// custom: owner filter` 注释

### 加载顺序与依赖

```
<head>
  ...上游 <style>...</style>
  <link rel="stylesheet" href="/static/custom.css?v=6">   ← custom CSS（覆盖上游样式）
</head>
<body>
  ...上游 HTML...
  <script>...上游 JS（定义 allBuckets/esc/authFetch/readJsonSafe/_SV/showDetail/loadPlans/loadLetters...）</script>
  <script src="/static/custom.js?v=5"></script>           ← custom JS（依赖上游全局变量/函数）
</body>
```

**关键约束**：`custom.js` 必须在主 `<script>` 之后加载，因为它依赖主脚本定义的全局变量/函数（`allBuckets`、`esc`、`authFetch`、`readJsonSafe`、`_SV`、`showDetail`、`loadPlans`、`loadLetters`）。放在 `</body>` 前可保证这一点。

### 侵入点清单（dashboard.html 里仍需维护的 custom 代码）

抽离后 dashboard.html 里剩下的 custom 痕迹只有这些，上游合并时需确认它们仍在：

| 位置 | 内容 | 用途 |
|------|------|------|
| `<head>` 末尾 | `<link rel="stylesheet" href="/static/custom.css?v=6">` | 加载 custom CSS |
| `<body>` 末尾 | `<script src="/static/custom.js?v=5"></script>` | 加载 custom JS |
| 域视图 HTML | `id="domain-view"` 整块 + owner 筛选按钮 + `onclick="setPlanOwnerFilter(...)"` | 域视图 DOM 结构 |
| 计划面板 HTML | owner 筛选按钮 `onclick="setPlanOwnerFilter(...)"` | plan owner 筛选 UI |
| 信件面板 HTML | owner 筛选按钮 `onclick="setLetterOwnerFilter(...)"` + 写信表单 owner 下拉框 | letter owner 筛选 UI |
| `loadPlans()` | `// custom: owner filter` + `_planOwnerFilter` 过滤行 | plan API 请求带 owner 参数 |
| `loadLetters()` | `// custom: owner filter` + `_letterOwnerFilter` 过滤行 | letter API 请求带 owner 参数 |
| `_renderLetter()` | `${_ownerTagHtml(l.owner)}` 调用 | 信件卡片显示 owner 标签 |
| Tab 切换逻辑 | `if (target === 'domain') renderDomainTimeline();` | 切到域视图时渲染时间线 |
| `loadBuckets()` 末尾 | `renderDomainTimeline()` 调用（如域视图可见） | 桶加载后刷新域视图 |

### 上游更新时需检查

| 上游改动点 | 检查内容 |
|-----------|---------|
| `dashboard.html` 的 `<head>` | 确认 `<link rel="stylesheet" href="/static/custom.css?v=6">` 仍在 `</style>` 后 |
| `dashboard.html` 的 `<body>` 末尾 | 确认 `<script src="/static/custom.js?v=5"></script>` 仍在主 `</script>` 后 |
| `dashboard.py` 的静态文件白名单 | 确认 `custom.css` / `custom.js` 仍在 `allowed` 字典里 |
| `custom.js` 依赖的全局变量/函数 | 上游是否重命名 `allBuckets`/`esc`/`authFetch`/`readJsonSafe`/`_SV`/`showDetail`/`loadPlans`/`loadLetters`，导致 custom.js 调用失败 |
| `dashboard.html` 的侵入点 | 确认 owner 筛选按钮、域视图 DOM、`renderDomainTimeline()` 调用仍在 |

### 抽离经验

1. **CSS 变量依赖**：custom.css 依赖上游 `<style>` 里定义的 CSS 变量（`--accent`、`--border`、`--surface`、`--text-dim`、`--warning`、`--negative`、`--positive` 等）。只要 `<link>` 在 `</style>` 之后加载，变量就能正确解析。如果上游重命名变量，custom.css 里对应变量会失效（视觉降级，不报错）。

2. **JS 全局依赖**：custom.js 不能用 ES module（`import`/`export`），因为上游主脚本是普通 `<script>`，全局变量挂在 `window` 上。custom.js 也用普通 `<script>` 加载，直接访问全局变量即可。

3. **函数声明 hoisting**：custom.js 里 `renderDomainTimeline` 调用了 `escapeHtml`，但 `escapeHtml` 定义在后面。因为 JavaScript function 声明会被 hoisting，所以顺序不重要。但若改用 `var escapeHtml = function() {...}`，则必须保证定义在使用之前。

4. **DOMContentLoaded 时机**：custom.js 里有 `document.addEventListener('DOMContentLoaded', ...)` 回调。因为 custom.js 在主脚本之后、`</body>` 之前同步加载，DOMContentLoaded 尚未触发，回调能正确执行。

5. **缓存控制**：`<link>` 和 `<script>` 用 `?v=N` 查询参数做缓存控制。更新 custom.css/custom.js 后，需把 dashboard.html 里的 `?v=N` 改成 `?v=N+1` 强制浏览器刷新缓存。或者直接 Ctrl+F5 硬刷新。当前版本：custom.css?v=6 / custom.js?v=5（v2.3.22 同步时 bump）。

6. **静态文件安全**：dashboard.py 的 `/static/{name}` 路由用白名单字典精确匹配文件名，不暴露目录遍历风险。新增 custom 文件只需在 `allowed` 字典加一行即可。

7. **抽离验证方法**：抽离后用 `node --check custom.js` 验证 JS 语法；用 `curl http://localhost:8000/static/custom.css` 验证 200 返回；浏览器打开 dashboard 后看服务日志是否有 `GET /static/custom.css` 和 `GET /static/custom.js` 的 200 记录；看 `/api/reranker/config` 是否被请求（验证 `refreshRrInfo` 执行了）。

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

## 改造六：8 固定主题域 + UI 布局优化 + 数据恢复

### 目的

1. **8 固定主题域**：把 AI 写入记忆时的主题域收敛到 8 个固定域（`日常/人际/成长/身心/兴趣/数字/事务/内心`），避免 AI 持续新增子域导致筛选器爆炸。旧数据通过归一化映射表收敛到固定域。
2. **域界面单行布局**：owner 按钮（全部/Alove/Pearl/Shared）+ 统计（`全部 · N 桶 · N 钉选`）合并为单行，宽屏单行显示，窄屏自动换行。
3. **buckets 界面三行筛选器**：把原单行筛选器拆为三行：状态筛选（全部/钉选/Feel/未解决/已消化/归档）/ 8 固定主题域 / owner filter，并显示 owner 彩色标签。
4. **时间线左移**：缩小时间线左侧日期列宽度和间距，减少留白。
5. **数据恢复**：从 ECS 备份 zip 恢复 106 个记忆桶，全部 UTF-8 编码、`owner: alove`。

### 设计原则

- **UI 逻辑全部隔离在 custom.js/custom.css**：通过 monkey-patch 覆盖 `buildFilters`/`filterBuckets`/`renderBuckets`，dashboard.html 的 `<script>` 主体不改动（只改 HTML 结构 + 缓存版本号），最大化上游同步友好性。
- **归一化兜底**：前端 `filterBuckets` 对域筛选做归一化（子域 → 固定域），即使 AI 偶尔写子域也能正确筛选。
- **AI prompt 强制约束**：dehydrator.py / reclassify_api.py / import_memory.py 三处 prompt 都明确要求"只写顶层域名，不写括号内的子域"。

### 修改文件

#### 1. `frontend/custom.js`

- **`FIXED_DOMAINS` 数组**：8 个固定主题域常量
- **`DOMAIN_MAP` 映射表**：旧域 → 固定域（编程→数字、情绪→内心、家庭→人际 等 30+ 条）
- **`normalizeDomain(d)`**：归一化函数
- **Monkey-patch `buildFilters`**：原函数执行后调用 `restructureBucketFilters()` 重构为三行
- **`restructureBucketFilters()`**：
  - Row 1 状态：保留原 `.filter-btn`（非 `domain:` 前缀）
  - Row 2 主题域：用 `FIXED_DOMAINS` 生成 `data-filter="domain:XXX"` 按钮
  - Row 3 owner：`全部/Alove/Pearl/Shared` + 事件绑定
- **Monkey-patch `filterBuckets`**：
  - 域筛选归一化兜底：`currentFilter` 为 `domain:XXX` 时，把 `DOMAIN_MAP` 中所有映射到 XXX 的子域也加入匹配集
  - owner 过滤：`_bucketOwnerFilter !== 'all'` 时按 `b.owner` 过滤
- **（owner 徽章已删除）**：原 `renderBuckets` monkey-patch 插入 `.bucket-owner-dot` 的逻辑已按用户要求移除

#### 2. `frontend/custom.css`

- **`.domain-owner-row`**：owner 按钮 + 统计容器，`flex-wrap: wrap`（宽屏单行，窄屏换行）
- **`@media (max-width: 560px)`**：手机端 owner 行垂直堆叠、按钮缩小
- **`.tl-group`**：`--tl-date-w: 68px`（原 88px）、`--tl-gap: 8px`（原 12px）、`--tl-node-w: 18px`（原 20px）
- **`.tl-date-main`**：字号 15px（原 17px）
- **`.bucket-filters-row` / `.row-label`**：三行筛选器样式
- **`.bucket-owner-row`**：owner 筛选行按钮样式
- **`@media (max-width: 560px)`**：buckets 筛选按钮缩小

#### 3. `frontend/dashboard.html`

- **HTML 结构**：owner 按钮 + 统计包在 `.domain-owner-row` div 内（强制单行容器）
- **缓存版本号**：`custom.css?v=5`、`custom.js?v=4`（每次 custom 文件改动都 bump）

#### 4. `src/dehydrator.py`

- **`EXTRACT_PROMPT`**：主题域说明改为"必须从以下 8 个固定域中选择 1~2 个（只写顶层域名，不写括号内的子域）"
- **`ANALYZE_PROMPT`**：同上强化

#### 5. `src/reclassify_api.py`

- **`ANALYZE_PROMPT`**：同上强化

#### 6. `src/import_memory.py`

- **prompt**：同上强化

#### 7. `buckets/` 数据目录（gitignored）

- 从 `D:\Backup\...\ombre_export_1782406987.zip\buckets` 恢复 106 个 .md 文件
- 全部 UTF-8 编码（无 BOM）
- 全部添加 `owner: alove` 字段
- 83 个文件的 domain 字段归一化到 8 固定域（编程→数字、情绪→内心 等）

### 上游更新时需检查

| 上游改动点 | 检查内容 |
|-----------|---------|
| `frontend/dashboard.html` 的 `<head>` / `<body>` 末尾 | `<link custom.css?v=N>` 和 `<script custom.js?v=N>` 引用是否被上游删除 |
| `frontend/dashboard.html` 的域视图 HTML | `.domain-owner-row` 包裹结构是否被上游重构打乱 |
| `dehydrator.py` / `reclassify_api.py` / `import_memory.py` 的 prompt | 上游是否改 prompt 文本导致 8 固定域约束丢失 |
| `custom.js` 的 monkey-patch 目标函数 | 上游是否重命名 `buildFilters`/`filterBuckets`/`renderBuckets` 导致 patch 失效 |
| `custom.css` 的 `.tl-group` 变量 | 上游是否改时间线结构导致 `--tl-date-w` 等变量失效 |

### 降级安全性

- `custom.js` 加载失败 → `buildFilters`/`filterBuckets` 走原逻辑 → buckets 界面回退到单行筛选器（功能正常，无三行布局）
- `FIXED_DOMAINS` 与 AI 输出不匹配 → `DOMAIN_MAP` 兜底归一化 → 未映射的域原样保留（不报错）
- 8 固定域 prompt 失效 → AI 写子域 → 前端 `filterBuckets` 归一化兜底 → 筛选仍正确

### 数据恢复详情

- **备份源**：`D:\Backup\Users\12075\Documents\xwechat_files\wxid_ej8ioygw1yqz12_4694\msg\file\2026-06\ombre_export_1782406987.zip`
- **恢复内容**：106 个 .md 记忆桶文件
- **编码处理**：PowerShell 解压时显式 UTF-8，写入时用 `[System.Text.UTF8Encoding]::new($false)` 避免 BOM
- **owner 字段**：全部添加 `owner: alove`
- **域归一化**：Python 脚本 `normalize_domains.py`（已删除，一次性使用）批量处理 83 个文件

---

## 版本历史

| 日期 | 上游版本 | 操作 | 说明 |
|------|---------|------|------|
| 2026-06-29 | v2.3.22 | 合并 v2.3.18→v2.3.22 | **手动 file-by-file 同步**（本地仓库与 upstream 无共同祖先，无法 `git merge`）。7 个冲突文件采用「保留双方」策略：owner 轴 + 上游 author 轴并存。详见下方「v2.3.22 同步记录」章节 |
| 2026-06-26 | v2.3.18 | 新增改造六 | 8 固定主题域（dehydrator/reclassify_api/import_memory prompt 强化 + 83 桶数据归一化）+ buckets 三行筛选器（monkey-patch buildFilters/filterBuckets）+ 域界面单行布局 + 时间线左移 + 手机端适配 + 数据恢复（106 桶从 ECS 备份恢复）+ owner 徽章（先加后删）|
| 2026-06-26 | v2.3.18 | 上传 GitHub | 推送到 https://github.com/c83076768-cmd/remember.git (origin)，原 origin 重命名为 upstream（P0luz/Ombre-Brain.git）。清理 mock 数据 + 测试文件（2400 行删除），脱敏验证无 API key/个人路径 |
| 2026-06-25 | v2.3.17 | 新增改造五 | 前端代码抽离：dashboard.html 的 custom CSS（165行）→ custom.css，custom JS（domain/owner/reranker 约470行）→ custom.js，dashboard.py 白名单加 css/js serve，dashboard.html 留 `<link>`+`<script src>` 引用 + 侵入点注释 |
| 2026-06-25 | v2.3.17 | 新增改造四 | Plan/Letter owner 隔离：plan/letter_write/letter_read/dream 加 owner 参数 + plan/core.py 去重读取过滤 + _common auto-resolve 过滤 + dream 过滤 + hooks/plans/letters API 加 ?owner= + dashboard 加 owner 筛选 |
| 2026-06-25 | v2.3.17 | 合并 v2.3.17 | OAuth 副连接器修复：`/.well-known/oauth-protected-resource/{path}` 严格匹配。冲突文件：`src/server.py`（手动合并 401 中间件 resource_metadata 动态路径）。不影响 custom 改造 |
| 2026-06-25 | v2.3.16 | 合并 v2.3.12→v2.3.16 | pinned 计数修复 + Windows config.yaml 目录崩溃修复 + 只读根文件系统修复 + 改称呼同步旧记忆 + decay 自愈降级孤儿固化桶。冲突文件 6 个（手动合并 `_common.py`/`utils.py`/`decay_engine.py`/`dashboard.html`，`docs/CLAUDE_PROMPT.md`/`docker-publish.yml` 直接用上游）。不影响 custom 改造 |
| 2026-06-25 | v2.3.11 | 合并 v2.3.10 + v2.3.11 | 无冲突。改动：VERSION 同步、embedding 模型名归一化、热更新 VERSION 同步。不影响 custom 改造 |
| 2026-06-25 | v2.3.9 | 合并 v2.3.8 + v2.3.9 | 无冲突。改动：bucket_manager update() unpin demote、dehydrator perspective rule、web/meta 热更新重启。不影响 custom 改造 |
| 2026-06-25 | v2.3.8 | 新增 grow owner 参数 | 给 `grow` 工具添加 `owner` 参数，与 breath/hold 相同的 set/reset 模式 |
| 2026-06-25 | v2.3.8 | 清理临时文件 | 删除 `demo_owner_isolation.py`、`tests/test_reranker_debug.py`、`tests/test_reranker_compare.py`、`tests/test_output.txt` |
| 更早 | — | reranker 引擎集成 | `reranker_engine.py` + `web/reranker.py` + search.py 接入 + dashboard 面板 |
| 更早 | — | owner 隔离集成 | `owner_filter.py` + breath/hold owner 参数 + bucket_manager owner 读写 + breath 子模块过滤 |

---

## v2.3.22 同步记录（2026-06-29）

### 背景

- 上游 `https://github.com/P0luz/Ombre-Brain.git` 从 v2.3.18 升到 v2.3.22，跨 4 个版本（v2.3.19 / v2.3.20 / v2.3.21 / v2.3.22）。
- 本地仓库 root commit 是 `27a3685 custom: v2.3.11 base`，与 upstream **无共同祖先**，`git merge upstream/main` 会报 `refusing to merge unrelated histories`。
- 因此沿用 v2.3.16/17/18 的同步策略：**手动 file-by-file 同步**。

### 上游主要变更（v2.3.18 → v2.3.22）

| 版本 | 主要变更 |
|------|---------|
| v2.3.19 | 单连接器合并：`mcp_extra` 的 7 个工具回灌进主 `mcp`，对外只暴露一条 `/mcp` 路由（claude.ai 5 工具上限已解除）。前端移除 `/mcp-extra` 引用，新增 OAuth 鉴权开关 + 服务端口配置面板。小鸡彩蛋新增「天气 / 时间 / 心情」三件套（ObChickFlavor IIFE + tod- 色温 CSS） |
| v2.3.20 | 小修小补（文档 / 配置 / 测试） |
| v2.3.21 | letter author 重构：新增 `ai_name` 参数 + `get_ai_name()` util，`letter_write` 的 author 接受任意字符串（不再限定 user/claude），旧值 `claude` 归一化为 `ai_name` 的值。`_normalize_author` helper 抽出 |
| v2.3.22 | 版本号 bump + 小修 |

### 冲突文件与合并策略

7 个文件同时带有 custom 改动和上游改动，采用「**保留双方**」策略（owner 轴 + 上游改动并存）：

| 文件 | custom 改动 | 上游改动 | 合并方式 |
|------|------------|---------|---------|
| `src/server.py` | owner 参数 + reranker 注入 | mcp_extra 工具回灌到 mcp | 检出上游版，重新应用 owner 参数（7 个工具）+ reranker_engine 初始化 + 注入 |
| `src/bucket_manager.py` | owner 读写 + search owner 过滤 | 无实质冲突 | 检出上游版，重新应用 owner_filter 导入 + create()/search() owner 逻辑 |
| `src/tools/breath/search.py` | reranker 重排序 + owner 过滤 | 无实质冲突 | 检出上游版，重新应用 reranker 块 + filter_buckets_by_context_owner |
| `src/tools/plan/core.py` | plan_create/letter_read owner 过滤 | `get_ai_name` + `_matches_query` 重构 | 检出上游版，重新应用 filter_buckets_by_context_owner（保留上游 ai_name 逻辑） |
| `src/web/hooks.py` | breath-hook owner 过滤 | `_is_hook_request_authorized` 401 门 + `_latest(*authors)` 重写 | 检出上游版，重新应用 hook_owner_set 过滤 |
| `src/web/letters.py` | /api/letters ?owner= + owner 字段 + 写信 owner | `_normalize_author` + ai_name 逻辑 | 检出上游版，重新应用 owner_set 过滤 + apply_owner_to_meta（保留上游 _normalize_author） |
| `src/dehydrator.py` | 8 固定域 prompt 强化 | `_is_transient_error`/`_chat` 重试 | 上游已含 8 域但措辞为「可选」，改为「必须从以下 8 个固定域中选择」（保留上游重试逻辑） |

### 用户决策（AskUserQuestion）

1. **author 轴处理**：完全采用上游 v2.3.21 的 `ai_name` 体系，与我们的 owner 轴正交共存。
2. **7 个冲突文件合并策略**：同意「保留双方」（owner 轴 + 上游改动并存）。
3. **小鸡彩蛋（v2.3.19）**：保留 ObChickFlavor（天气 / 时间 / 心情 + tod- 色温 CSS）。

### 文件操作汇总

**Phase 1 — 直接检出上游版（33 个非 custom 文件）**：docs / config / deploy / tests / tools / 非 custom 的 src 文件（含 `config_api.py`，因 reranker 已迁出，零 custom 改动）。

**Phase 2 — 小 diff 应用到 custom 文件（4 个）**：
- `src/web/dashboard.py`：新增 `Cache-Control: no-cache, no-store, must-revalidate` 到 HTMLResponse；保留 custom.css/js 白名单
- `src/web/buckets.py`：3 处注释 `Claude` → `AI`；保留 owner/protected/event_time 字段
- `src/web/plans.py`：1 处注释 `Claude` → `AI`；保留 ?owner= + owner 字段
- `frontend/dashboard.html`：Phase 4 单独处理

**Phase 3 — 检出上游版后重新应用 custom（10 个 Python 文件）**：见上表 7 个 + `src/tools/breath/importance.py` / `surface.py` / `src/tools/_common.py`（这 3 个仅有 owner_filter 调用，无上游实质冲突）。

**Phase 4 — dashboard.html 手动合并**：
- 信件表单：`<option value="claude">` → `<option value="ai">`；placeholder `user_name` → `署名 name`；`<input type="date">` → `<button class="date-pill">` + 隐藏 input + 日期 label
- 信件筛选：`<option value="claude">仅 AI</option>` → `<option value="ai">仅 AI</option>`
- `_renderLetter()`：`who = ... : 'claude'` → `(l.author || 'AI')`；`accentColor = l.author === 'claude'` → `l.author !== 'user'`
- 新增 `openDatePicker()` / `syncDateLabel()` helper + `.date-pill` CSS
- `loadLogs()`：只显示文件名（全路径放 `meta.title`）
- MCP 配置面板：移除 `/mcp-extra` 引用，改为单一 `/mcp`；新增 OAuth 鉴权开关 + 服务端口配置面板；`copyAllMcpUrls` / `_buildClaudeDesktopConfig` / `exportClaudeDesktopConfig` 改为单端点；新增 `saveMcpAuth` / `saveHostPort` JS；`loadConfig()` 加载 `mcp_require_auth` / `host_port` / `in_docker` + 端口提示 + readonly 显示
- 文本：5 处 `Claude` → `AI`（调用 breath / 无法触发 / 无法恢复 / 收到通知）
- 小鸡彩蛋：新增 ObChickFlavor IIFE（~100 行，时段 / 天气 / 心情）+ tod-dawn/day/dusk/night 色温 CSS

**Phase 5 — 验证 + 文档 + 缓存**：
- 全部 13 个修改过的 Python 文件通过 `python -m py_compile` 语法检查
- 验证 custom 侵入点仍在：`<link custom.css?v=6>` / `<script custom.js?v=5>` / `domain-view` HTML / owner 筛选按钮 / `_ownerTagHtml` 调用 / `renderDomainTimeline` 钩子 / reranker 面板
- bump 缓存版本：custom.css `?v=5` → `?v=6`，custom.js `?v=4` → `?v=5`
- 更新本日志：修正 `config_api.py` 的 stale 信息（reranker 已迁到 `web/reranker.py`，config_api.py 零 custom 改动）

### 不影响 custom 改造的验证

| 验证项 | 结果 |
|--------|------|
| `src/owner_filter.py` 存在 | ✓ |
| `src/reranker_engine.py` 存在 | ✓ |
| `src/web/reranker.py` 存在 | ✓ |
| `frontend/custom.css` / `custom.js` 存在 | ✓ |
| `server.py` 7 个工具的 owner 参数 + set/reset 包装 | ✓ |
| `server.py` reranker_engine 初始化 + 双重注入（_wsh.init_runtime + _tools_runtime.init） | ✓ |
| `tools/breath/search.py` reranker 块 + owner 过滤 | ✓ |
| `dashboard.html` custom.css/js 引用 + domain-view + owner 按钮 + _ownerTagHtml | ✓ |
| `dashboard.py` custom.css/js 白名单 | ✓ |
| 13 个 Python 文件 `py_compile` | ✓ 全部通过 |
