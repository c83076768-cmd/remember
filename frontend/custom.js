/* ============================================================
 * custom.js — Ombre-Brain custom 改造前端逻辑
 * 从 dashboard.html 抽离，减少上游合并冲突。
 * 包含：域/Domain 时间线 + owner 筛选 + Reranker UI。
 *
 * 依赖（主脚本 <script> 里定义的全局变量/函数）：
 *   - allBuckets, esc, escapeHtml(已抽离到此), authFetch, readJsonSafe, _SV, BASE
 *   - showDetail(id) — 主脚本里的桶详情函数
 *   - loadPlans(), loadLetters() — 主脚本里的列表加载函数
 *
 * 加载顺序：必须在主 <script> 之后加载（放 </script> 之后）。
 * ============================================================ */

// ════════════════════════════════════════════════════════════
// 1. 域 / Domain Timeline
// ════════════════════════════════════════════════════════════

var domainState = {
  owner: 'all',       // all | alove | pearl | shared
  filter: 'all',      // all | pinned | important | feel
  search: '',
  expandedId: null,
  detailCache: {},
};
var _domainListenersAttached = false;

function domainSortKey(b) {
  return b.event_time || b.created || (b.last_active || '');
}
function domainMatchesOwner(b) {
  if (domainState.owner === 'all') return true;
  return (b.owner || 'shared') === domainState.owner;
}
function domainMatchesFilter(b) {
  if (domainState.filter === 'all') return true;
  if (domainState.filter === 'pinned') return !!(b.pinned || b.protected);
  if (domainState.filter === 'important') return (b.importance || 5) >= 8;
  if (domainState.filter === 'feel') return b.type === 'feel';
  return true;
}
function domainMatchesSearch(b) {
  if (!domainState.search) return true;
  var q = domainState.search.toLowerCase();
  var hay = ((b.name || '') + ' ' + (b.content_preview || '') + ' ' + (b.tags || []).join(' ')).toLowerCase();
  return hay.indexOf(q) !== -1;
}
function domainOwnerLabel(owner) {
  if (owner === 'alove') return 'Alove';
  if (owner === 'pearl') return 'Pearl';
  return 'Shared';
}
function domainOwnerColor(owner) {
  if (owner === 'alove') return '#8B4A6A';
  if (owner === 'pearl') return '#4A6C8B';
  return '#4A7C59';
}
// 生成 owner 彩色小标签（plan / letter 卡片共用）
function _ownerTagHtml(owner) {
  if (!owner) owner = 'shared';
  var label = domainOwnerLabel(owner);
  var color = domainOwnerColor(owner);
  return '<span style="display:inline-block;padding:1px 6px;margin-right:6px;border-radius:8px;font-size:10px;color:#fffdf5;background:' + color + ';vertical-align:middle;">' + esc(label) + '</span>';
}

// 去掉标题中的时间戳前缀（如 "2026-06-25 18-42-55 雨中散步" → "雨中散步"）
function domainCleanTitle(name) {
  if (!name) return '';
  // 匹配 YYYY-MM-DD HH-MM-SS 前缀（20 个字符）
  var m = name.match(/^\d{4}-\d{2}-\d{2}\s+\d{2}-\d{2}-\d{2}\s+/);
  if (m) return name.slice(m[0].length);
  return name;
}

// HTML 转义（domain timeline 专用，主脚本的 esc() 功能类似但签名不同）
function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function domainAttachListeners() {
  if (_domainListenersAttached) return;
  _domainListenersAttached = true;

  // owner 按钮
  document.querySelectorAll('.domain-owner-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.domain-owner-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      domainState.owner = btn.dataset.owner;
      domainState.expandedId = null;
      renderDomainTimeline();
    });
  });

  // filter 按钮
  document.querySelectorAll('#domain-view .domain-controls .filter-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('#domain-view .domain-controls .filter-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      domainState.filter = btn.dataset.dlFilter;
      renderDomainTimeline();
    });
  });

  // 搜索
  var search = document.getElementById('domain-search');
  if (search) {
    var t;
    search.addEventListener('input', function(e) {
      clearTimeout(t);
      t = setTimeout(function() {
        domainState.search = e.target.value.trim();
        renderDomainTimeline();
      }, 200);
    });
  }
}

function renderDomainTimeline() {
  domainAttachListeners();
  var list = document.getElementById('domain-timeline-list');
  var all = allBuckets || [];

  // owner 筛选
  var ownerFiltered = all.filter(domainMatchesOwner);

  // 统计
  var pinnedCount = ownerFiltered.filter(function(b) { return !!(b.pinned || b.protected); }).length;
  var ownerLabel = domainState.owner === 'all' ? '全部' : domainOwnerLabel(domainState.owner);
  document.getElementById('domain-stats').textContent =
    ownerLabel + ' · ' + ownerFiltered.length + ' 桶 · ' + pinnedCount + ' 钉选';

  // filter + 搜索
  var filtered = ownerFiltered.filter(function(b) {
    return domainMatchesFilter(b) && domainMatchesSearch(b);
  });

  if (!filtered.length) {
    list.innerHTML = '<div class="tl-empty">' + ownerLabel + ' 记忆池中没有匹配的记忆。</div>';
    return;
  }

  // 按时间倒序
  filtered.sort(function(a, b) {
    return domainSortKey(b).localeCompare(domainSortKey(a));
  });

  // 按 YYYY-MM-DD 分组（同一天一个卡片）
  var groups = {};
  var groupOrder = [];
  filtered.forEach(function(b) {
    var key = String(domainSortKey(b));
    var ymd = key.length >= 10 ? key.slice(0, 10) : '未知日期';
    if (!groups[ymd]) { groups[ymd] = []; groupOrder.push(ymd); }
    groups[ymd].push(b);
  });

  var WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

  var html = '';
  groupOrder.forEach(function(ymd) {
    var rows = groups[ymd];
    // 日期块
    var dateMain = ymd, dateSub = '';
    if (ymd.length >= 10) {
      var y = ymd.slice(0, 4), m = ymd.slice(5, 7), d = ymd.slice(8, 10);
      dateMain = parseInt(m, 10) + '/' + parseInt(d, 10);
      var dt = new Date(parseInt(y, 10), parseInt(m, 10) - 1, parseInt(d, 10));
      dateSub = (WEEKDAYS[dt.getDay()] || '') + ' · ' + y;
    }

    // 卡片头：聚合 owner
    var ownersInCard = {};
    rows.forEach(function(b) {
      var o = b.owner || 'shared';
      ownersInCard[o] = (ownersInCard[o] || 0) + 1;
    });
    var hasPinned = rows.some(function(b) { return !!(b.pinned || b.protected); });
    var hasFeel = rows.some(function(b) { return b.type === 'feel'; });

    html += '<div class="tl-group"' +
      (hasPinned ? ' data-has-pinned="true"' : '') +
      (hasFeel ? ' data-has-feel="true"' : '') + '>';
    html += '<div class="tl-date-block"><div class="tl-date-main">' + dateMain + '</div><div class="tl-date-sub">' + dateSub + '</div></div>';
    html += '<div class="tl-node"></div>';
    html += '<div class="tl-card">';
    html += '<div class="tl-card-header"><span class="tl-card-count">' + rows.length + '</span> 条记忆';
    if (domainState.owner === 'all') {
      html += '<span class="tl-card-owners">';
      Object.keys(ownersInCard).forEach(function(o) {
        html += '<span class="tl-card-owner" style="color:' + domainOwnerColor(o) + '">' + domainOwnerLabel(o) + ' ' + ownersInCard[o] + '</span>';
      });
      html += '</span>';
    }
    html += '</div><div class="tl-rows">';

    rows.forEach(function(b) {
      var sortKey = String(domainSortKey(b));
      // 时间（HH:MM）
      var timeStr = '—';
      if (sortKey.length >= 16) timeStr = sortKey.slice(11, 16);

      var typeClass = b.type || 'dynamic';

      // badges：只显示状态徽章，标题为纯文字
      var badges = '';
      if (b.pinned) badges += '<span class="tl-badge pinned">📌</span>';
      if (b.protected) badges += '<span class="tl-badge protected">🔒</span>';
      if ((b.importance || 5) >= 8) badges += '<span class="tl-badge important">◆' + b.importance + '</span>';
      if (b.type === 'feel') badges += '<span class="tl-badge feel">🫧</span>';

      html += '<div class="tl-row" onclick="showDetail(\'' + b.id + '\')">';
      html += '<div class="tl-time">' + timeStr + '</div>';
      html += '<div class="tl-title">' + escapeHtml(domainCleanTitle(b.name) || b.id) + '<span class="tl-badges">' + badges + '</span></div>';
      html += '</div>';
    });

    html += '</div></div></div>';
  });

  list.innerHTML = html;
}

// ════════════════════════════════════════════════════════════
// 2. Plan owner 筛选
// ════════════════════════════════════════════════════════════

var _planOwnerFilter = '';
function setPlanOwnerFilter(owner) {
  _planOwnerFilter = owner || '';
  document.querySelectorAll('[data-plan-owner]').forEach(function(b){
    b.classList.toggle('active', b.getAttribute('data-plan-owner') === _planOwnerFilter);
  });
  loadPlans();
}

// ════════════════════════════════════════════════════════════
// 3. Letter owner 筛选
// ════════════════════════════════════════════════════════════

var _letterOwnerFilter = '';
function setLetterOwnerFilter(owner) {
  _letterOwnerFilter = owner || '';
  document.querySelectorAll('[data-letter-owner]').forEach(function(b){
    b.classList.toggle('active', b.getAttribute('data-letter-owner') === _letterOwnerFilter);
  });
  loadLetters();
}

// ════════════════════════════════════════════════════════════
// 4. Reranker UI
// ════════════════════════════════════════════════════════════

// ===== Reranker info panel（对齐 embedding 的 refreshEmbInfo） =====
async function refreshRrInfo() {
  try {
    var r = await authFetch('/api/reranker/config');
    if (!r) return;
    var d = await readJsonSafe(r);
    if (!d || !d.ok) return;

    // info panel
    document.getElementById('rr-info-enabled').textContent = d.enabled ? '已启用' : '未启用';
    document.getElementById('rr-info-model').textContent = d.model || '—';
    document.getElementById('rr-info-key').textContent = d.api_ready ? (d.api_key_masked || '已配置') : '未配置';
    document.getElementById('rr-info-url').textContent = d.effective_base_url || '—';
    document.getElementById('rr-info-weight').textContent = d.score_weight != null ? d.score_weight : '—';
    document.getElementById('rr-info-limit').textContent = d.candidate_limit != null ? d.candidate_limit : '—';

    // meta 行
    var metaTxt = '';
    if (d.has_own_api_key) {
      metaTxt = '使用独立 Reranker API Key';
    } else if (d.api_ready) {
      metaTxt = '复用 Embedding API Key / Base URL';
    } else {
      metaTxt = _SV.warn + ' 未配置，将跳过重排序';
    }
    document.getElementById('rr-info-meta').innerHTML = metaTxt;

    // notice（未配置时显示警告）
    var rrNotice = document.getElementById('rr-key-notice');
    var rrNoticeText = document.getElementById('rr-notice-text');
    if (rrNotice && rrNoticeText) {
      if (!d.api_ready) {
        rrNotice.style.display = '';
        rrNoticeText.textContent = 'Reranker 未配置 API Key / Base URL，将自动跳过重排序。留空时复用 Embedding 配置。';
      } else {
        rrNotice.style.display = 'none';
      }
    }

    // 同步 key 输入框 placeholder（对齐 embedding 的 refreshEnvConfig）
    var rrKeyInline = document.getElementById('cfg-rr-api-key');
    if (rrKeyInline) {
      rrKeyInline.placeholder = d.api_ready ? '当前: ' + (d.api_key_masked || '***') : '未设置';
      rrKeyInline.value = '';
    }
    var rrBaseInline = document.getElementById('cfg-rr-base-url');
    if (rrBaseInline) rrBaseInline.value = d.base_url || '';
    var rrModelInline = document.getElementById('cfg-rr-model');
    if (rrModelInline) rrModelInline.value = d.model || '';
    var rrEnabledInline = document.getElementById('cfg-rr-enabled');
    if (rrEnabledInline) rrEnabledInline.value = d.enabled ? '1' : '0';
    var rrWeightInline = document.getElementById('cfg-rr-score-weight');
    if (rrWeightInline) rrWeightInline.value = d.score_weight != null ? d.score_weight : '';
    var rrLimitInline = document.getElementById('cfg-rr-candidate-limit');
    if (rrLimitInline) rrLimitInline.value = d.candidate_limit != null ? d.candidate_limit : '';
  } catch (e) {
    // ignore
  }
}

// ===== 保存 Reranker Key（对齐 saveEmbedKey） =====
async function saveRerankerKey() {
  var msgEl = document.getElementById('rr-key-msg');
  if (!msgEl) return;
  var apiKey = (document.getElementById('cfg-rr-api-key').value || '').trim();
  var baseUrl = (document.getElementById('cfg-rr-base-url').value || '').trim();
  var model = (document.getElementById('cfg-rr-model').value || '').trim();
  var enabled = document.getElementById('cfg-rr-enabled').value;
  var scoreWeight = parseFloat(document.getElementById('cfg-rr-score-weight').value);
  var candidateLimit = parseInt(document.getElementById('cfg-rr-candidate-limit').value);

  // 检查是否已有 key（通过 placeholder 判断，对齐 fetchModels 的逻辑）
  var phEl = document.getElementById('cfg-rr-api-key');
  var keyIsAlreadySaved = phEl && phEl.placeholder.indexOf('当前:') !== -1;

  if (!apiKey && !keyIsAlreadySaved) {
    msgEl.style.color = 'var(--warning)'; msgEl.innerHTML = _SV.warn + ' 请先输入并保存 API Key';
    return;
  }

  // 如果 key 为空但已有 key，用 sentinel
  var keyToSend = apiKey || (keyIsAlreadySaved ? '__use_current_reranker__' : '');

  var body = {
    api_key: keyToSend,
    base_url: baseUrl,
    model: model,
    enabled: enabled === '1',
  };
  if (!isNaN(scoreWeight)) body.score_weight = scoreWeight;
  if (!isNaN(candidateLimit)) body.candidate_limit = candidateLimit;

  msgEl.style.color = 'var(--text-dim)'; msgEl.textContent = '保存中…';
  try {
    var resp = await authFetch('/api/reranker/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp) return;
    var d = await readJsonSafe(resp);
    if (d && d.ok) {
      msgEl.style.color = 'var(--positive, #9DC880)'; msgEl.innerHTML = _SV.ok + ' 保存成功，reranker 已热重建';
      setTimeout(refreshRrInfo, 500);
    } else {
      msgEl.style.color = 'var(--negative)'; msgEl.innerHTML = _SV.err + ' ' + esc(d.error || '保存失败');
    }
  } catch (e) {
    msgEl.style.color = 'var(--negative)'; msgEl.innerHTML = _SV.err + ' ' + esc(e.message || e);
  }
}

// ===== 获取可用模型列表（对齐 fetchModels，用 model-list-dropdown） =====
async function fetchRerankerModels() {
  var listEl = document.getElementById('cfg-rr-model-list');
  if (!listEl) return;

  // 检查是否已有 key
  var phEl = document.getElementById('cfg-rr-api-key');
  var keyIsAlreadySaved = phEl && phEl.placeholder.indexOf('当前:') !== -1;
  var apiKey = (phEl.value || '').trim();
  var baseUrl = (document.getElementById('cfg-rr-base-url').value || '').trim();

  if (!apiKey && !keyIsAlreadySaved) {
    listEl.style.display = 'block';
    listEl.innerHTML = '<div style="padding:8px 12px;color:var(--warning);">' + _SV.warn + ' 请先输入并保存 API Key，再获取模型列表</div>';
    return;
  }

  var effectiveKey = apiKey || '__use_current_reranker__';

  listEl.style.display = 'block';
  listEl.innerHTML = '<div style="padding:6px 10px;color:var(--text-dim);">获取中…</div>';
  try {
    var payload = { api_key: effectiveKey, base_url: baseUrl };
    var r = await authFetch('/api/reranker/models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r) { listEl.style.display = 'none'; return; }
    var d = await readJsonSafe(r);
    if (!d || !d.ok || !d.models || !d.models.length) {
      listEl.innerHTML = '<div style="padding:8px 12px;color:var(--negative);">' + _SV.err + ' ' + esc(d.error || '无可用模型') + '</div>';
      return;
    }
    // 过滤可能支持 rerank 的模型
    var rerankModels = d.models.filter(function(m) {
      return /rerank|reranker|bge-reranker|qwen.*rerank/i.test(m);
    });
    var allModels = rerankModels.length > 0 ? rerankModels : d.models;
    listEl.innerHTML = allModels.map(function(m) {
      var safe = m.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
      return '<div class="model-item" onclick="document.getElementById(\'cfg-rr-model\').value=\'' + safe + '\';document.getElementById(\'cfg-rr-model-list\').style.display=\'none\';">' + m + '</div>';
    }).join('');
  } catch (e) {
    listEl.innerHTML = '<div style="padding:8px 12px;color:var(--negative);">' + _SV.err + ' ' + esc(e.message) + '</div>';
  }
}

// ===== 测试 rerank 端点（对齐 testEmbeddingKey，结果显示在 rr-key-msg） =====
async function testReranker() {
  var msgEl = document.getElementById('rr-key-msg');
  if (!msgEl) return;
  msgEl.style.color = 'var(--text-dim)'; msgEl.textContent = '测试中…';
  try {
    var resp = await authFetch('/api/reranker/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    if (!resp) return;
    var d = await readJsonSafe(resp);
    if (d && d.ok) {
      var resultsTxt = (d.results || []).map(function(r) { return '[index=' + r.index + ' score=' + r.score + ']'; }).join(' ');
      msgEl.style.color = 'var(--positive, #9DC880)';
      msgEl.innerHTML = _SV.ok + ' 测试成功（模型 ' + esc(d.model || '?') + '，结果 ' + resultsTxt + '）';
    } else {
      msgEl.style.color = 'var(--negative)'; msgEl.innerHTML = _SV.err + ' ' + esc(d.error || '测试失败');
    }
  } catch (e) {
    msgEl.style.color = 'var(--negative)'; msgEl.innerHTML = _SV.err + ' ' + esc(e.message || e);
  }
}

// ════════════════════════════════════════════════════════════
// 5. Buckets 界面三行筛选器 + owner 过滤 + owner 标签
// 通过 monkey-patch 实现，不修改 dashboard.html 主脚本
// ════════════════════════════════════════════════════════════

var _bucketOwnerFilter = 'all';

// 8 固定主题域（与 dehydrator.py / reclassify_api.py 保持一致）
var FIXED_DOMAINS = ['日常', '人际', '成长', '身心', '兴趣', '数字', '事务', '内心'];

// 旧域 → 8 固定域归一化映射
var DOMAIN_MAP = {
  '编程': '数字', 'AI': '数字', '硬件': '数字', '网络': '数字', '云服务': '数字', '安全': '数字',
  '饮食': '日常', '穿搭': '日常', '出行': '日常', '居家': '日常', '购物': '日常',
  '家庭': '人际', '恋爱': '人际', '友谊': '人际', '社交': '人际', '关系': '人际', '沟通': '人际',
  '工作': '成长', '学习': '成长', '考试': '成长', '求职': '成长',
  '健康': '身心', '心理': '身心', '睡眠': '身心', '运动': '身心',
  '游戏': '兴趣', '影视': '兴趣', '音乐': '兴趣', '阅读': '兴趣', '创作': '兴趣', '手工': '兴趣', '兴趣创作': '兴趣', '兴趣:创作': '兴趣',
  '财务': '事务', '计划': '事务', '待办': '事务',
  '情绪': '内心', '回忆': '内心', '梦境': '内心', '自省': '内心', '自我认知': '内心',
};
function normalizeDomain(d) {
  if (!d) return d;
  return DOMAIN_MAP[d] || d;
}

// --- Monkey-patch buildFilters: 单行 → 三行 ---
(function() {
  var _orig = window.buildFilters;
  if (typeof _orig !== 'function') return;
  window.buildFilters = function() {
    _orig.apply(this, arguments);
    restructureBucketFilters();
  };
})();

function restructureBucketFilters() {
  var filters = document.getElementById('filters');
  if (!filters) return;
  var btns = Array.prototype.slice.call(filters.querySelectorAll('.filter-btn'));
  if (!btns.length) return;

  // 分离状态按钮和域按钮
  var statusBtns = btns.filter(function(b) {
    return (b.dataset.filter || '').indexOf('domain:') !== 0;
  });

  var html = '';
  // Row 1: 状态筛选
  html += '<div class="bucket-filters-row">';
  html += '<span class="row-label">状态</span>';
  statusBtns.forEach(function(b) { html += b.outerHTML; });
  html += '</div>';
  // Row 2: 8 固定主题域
  html += '<div class="bucket-filters-row">';
  html += '<span class="row-label">主题域</span>';
  FIXED_DOMAINS.forEach(function(d) {
    html += '<button class="filter-btn" data-filter="domain:' + d + '">' + d + '</button>';
  });
  html += '</div>';
  // Row 3: owner 筛选
  html += '<div class="bucket-filters-row bucket-owner-row">';
  html += '<span class="row-label">Owner</span>';
  html += '<button class="domain-owner-btn active" data-bucket-owner="all">全部</button>';
  html += '<button class="domain-owner-btn" data-bucket-owner="alove">Alove</button>';
  html += '<button class="domain-owner-btn" data-bucket-owner="pearl">Pearl</button>';
  html += '<button class="domain-owner-btn" data-bucket-owner="shared">Shared</button>';
  html += '</div>';

  filters.innerHTML = html;

  // owner 按钮事件
  filters.querySelectorAll('[data-bucket-owner]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      filters.querySelectorAll('[data-bucket-owner]').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      _bucketOwnerFilter = btn.dataset.bucketOwner;
      if (typeof renderBuckets === 'function' && typeof filterBuckets === 'function') {
        renderBuckets(filterBuckets(allBuckets));
      }
    });
  });
}

// --- Monkey-patch filterBuckets: 域归一化 + owner 过滤 ---
(function() {
  var _orig = window.filterBuckets;
  if (typeof _orig !== 'function') return;
  window.filterBuckets = function(buckets) {
    var filtered;
    // 域筛选：归一化兜底（子域 → 固定域）
    if (typeof currentFilter === 'string' && currentFilter.indexOf('domain:') === 0) {
      var target = currentFilter.slice(7);
      var matches = [target];
      Object.keys(DOMAIN_MAP).forEach(function(k) { if (DOMAIN_MAP[k] === target) matches.push(k); });
      filtered = buckets.filter(function(b) {
        return (b.domain || []).some(function(d) { return matches.indexOf(d) !== -1; });
      });
    } else {
      filtered = _orig.apply(this, arguments);
    }
    // owner 过滤
    if (_bucketOwnerFilter && _bucketOwnerFilter !== 'all') {
      filtered = filtered.filter(function(b) {
        return (b.owner || 'shared') === _bucketOwnerFilter;
      });
    }
    return filtered;
  };
})();

// --- Monkey-patch renderBuckets: 桶卡片追加 owner 小标签 ---
(function() {
  var _orig = window.renderBuckets;
  if (typeof _orig !== 'function') return;
  window.renderBuckets = function(buckets) {
    _orig.apply(this, arguments);
    var list = document.getElementById('bucket-list');
    if (!list) return;
    // 构建 id→owner 映射
    var ownerMap = {};
    (allBuckets || []).forEach(function(b) { ownerMap[b.id] = b.owner || 'shared'; });
    list.querySelectorAll('.bucket-row').forEach(function(row) {
      var id = row.getAttribute('data-id');
      var owner = ownerMap[id];
      if (!owner || row.querySelector('.bucket-owner-tag')) return;
      var top = row.querySelector('.bucket-row-top');
      if (!top) return;
      var tag = document.createElement('span');
      tag.className = 'bucket-owner-tag';
      tag.style.background = domainOwnerColor(owner);
      tag.textContent = domainOwnerLabel(owner);
      var tagsEl = top.querySelector('.bucket-row-tags');
      if (tagsEl) top.insertBefore(tag, tagsEl);
      else top.appendChild(tag);
    });
  };
})();

// 页面加载完成后自动加载 reranker 配置
document.addEventListener('DOMContentLoaded', function() {
  setTimeout(refreshRrInfo, 800);
});
