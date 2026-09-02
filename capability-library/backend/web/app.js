// Skills Library 后台前端逻辑，原生 JS，无构建步骤。
const state = { skills: [], taxonomy: null, current: null };

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

function buildQuery(params) {
  const usp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) usp.set(k, v);
  const s = usp.toString();
  return s ? `?${s}` : "";
}

async function loadTaxonomy() {
  state.taxonomy = await api("/api/taxonomy");
  const industrySel = document.getElementById("f-industry");
  for (const ind of state.taxonomy.industries) {
    const opt = document.createElement("option");
    opt.value = ind.slug;
    opt.textContent = ind.name;
    industrySel.appendChild(opt);
  }
}

async function loadSkills() {
  const category = document.getElementById("f-category").value;
  const industry = document.getElementById("f-industry").value;
  const status = document.getElementById("f-status").value;
  state.skills = await api(`/api/skills${buildQuery({ category, industry, status })}`);
  renderRows();
  renderCategoryOptions();
}

function renderCategoryOptions() {
  const sel = document.getElementById("f-category");
  const cur = sel.value;
  const cats = [...new Set(state.skills.map((s) => s.category).filter(Boolean))];
  sel.innerHTML = '<option value="">全部分类</option>' +
    cats.map((c) => `<option value="${c}">${c}</option>`).join("");
  sel.value = cur;
}

function renderRows() {
  const tbody = document.getElementById("skill-rows");
  tbody.innerHTML = state.skills
    .map(
      (s) => `
    <tr data-name="${s.name}">
      <td>${s.name}</td>
      <td>${s.category || "-"}</td>
      <td>${(s.industries || []).join(", ") || "-"}</td>
      <td class="score">${s.score ?? "-"}</td>
      <td><span class="badge status-${s.status || ""}">${s.status || "-"}</span></td>
    </tr>`
    )
    .join("");
  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => selectSkill(tr.dataset.name));
  });
}

async function selectSkill(name) {
  const data = await api(`/api/skills/${encodeURIComponent(name)}`);
  state.current = data;
  renderDetail(data);
}

function industryOptionsHtml(selected) {
  const sel = new Set(selected || []);
  return state.taxonomy.industries
    .map((ind) => `<option value="${ind.slug}" ${sel.has(ind.slug) ? "selected" : ""}>${ind.name}</option>`)
    .join("");
}

function renderDetail(data) {
  const meta = data.meta || {};
  const cap = meta.capability || {};
  const rubric = cap.rubric || {};
  const source = meta.source || {};
  const pane = document.getElementById("detail");
  pane.innerHTML = `
    <h2>${data.name}</h2>
    <section>
      <h3>说明 (来自 SKILL.md frontmatter)</h3>
      <p>${data.frontmatter?.description || "-"}</p>
    </section>
    <section>
      <h3>治理字段</h3>
      <div class="row">
        <div>
          <label>分类 (category)</label>
          <input type="text" id="f-cat" value="${meta.category || ""}">
        </div>
        <div>
          <label>状态 (status)</label>
          <select id="f-status-edit">
            ${["active", "experimental", "deprecated"]
              .map((s) => `<option value="${s}" ${meta.status === s ? "selected" : ""}>${s}</option>`)
              .join("")}
          </select>
        </div>
      </div>
      <label>行业标签 (可多选)</label>
      <select id="f-industries" multiple size="4">${industryOptionsHtml(meta.industries)}</select>
    </section>
    <section>
      <h3>能力评分（人工评审为准）</h3>
      <div class="row">
        <div><label>综合分 score</label><input type="number" id="f-score" min="1" max="10" value="${cap.score ?? ""}"></div>
        <div><label>AI 建议分（只读参考）</label><input type="text" value="${cap.ai_suggested_score ?? "-"}" disabled></div>
      </div>
      <div class="row">
        <div><label>completeness</label><input type="number" id="f-completeness" min="1" max="10" value="${rubric.completeness ?? ""}"></div>
        <div><label>doc_quality</label><input type="number" id="f-doc_quality" min="1" max="10" value="${rubric.doc_quality ?? ""}"></div>
      </div>
      <div class="row">
        <div><label>maintenance</label><input type="number" id="f-maintenance" min="1" max="10" value="${rubric.maintenance ?? ""}"></div>
        <div><label>real_world_effect</label><input type="number" id="f-real_world_effect" min="1" max="10" value="${rubric.real_world_effect ?? ""}"></div>
      </div>
      <label>评审备注 notes</label>
      <textarea id="f-notes" rows="2">${cap.notes || ""}</textarea>
      <button id="btn-save-meta">保存评分/分类</button>
    </section>
    <section>
      <h3>相似 skill (similar_to)</h3>
      <input type="text" id="f-similar" value="${(meta.similar_to || []).join(", ")}" placeholder="逗号分隔的 skill 名">
      <button id="btn-save-similar">保存</button>
    </section>
    <section>
      <h3>来源记录</h3>
      <pre>${data.source_md || "(无 SOURCE.md)"}</pre>
      <p>source.url: ${source.url || "(未配置)"}</p>
      <button id="btn-check-update" ${source.url ? "" : "disabled"}>检查更新（只读，不写文件）</button>
      <div id="check-update-result"></div>
    </section>
    <section>
      <h3>更新记录 (CHANGELOG.md)</h3>
      <pre>${data.changelog || "(无记录)"}</pre>
      <div class="row">
        <div><input type="text" id="f-log-author" placeholder="操作人"></div>
        <div><input type="text" id="f-log-summary" placeholder="本次更新摘要"></div>
      </div>
      <button id="btn-add-log">追加记录</button>
    </section>
  `;
  bindDetailEvents(data.name);
}

function num(id) {
  const v = document.getElementById(id).value;
  return v === "" ? null : Number(v);
}

function bindDetailEvents(name) {
  document.getElementById("btn-save-meta").addEventListener("click", async () => {
    const industries = Array.from(document.getElementById("f-industries").selectedOptions).map((o) => o.value);
    const body = {
      category: document.getElementById("f-cat").value || null,
      status: document.getElementById("f-status-edit").value,
      industries,
      capability: {
        score: num("f-score"),
        notes: document.getElementById("f-notes").value,
        rubric: {
          completeness: num("f-completeness"),
          doc_quality: num("f-doc_quality"),
          maintenance: num("f-maintenance"),
          real_world_effect: num("f-real_world_effect"),
        },
      },
    };
    await api(`/api/skills/${encodeURIComponent(name)}/meta`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    await loadSkills();
    await selectSkill(name);
  });

  document.getElementById("btn-save-similar").addEventListener("click", async () => {
    const similar_to = document
      .getElementById("f-similar")
      .value.split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    await api(`/api/skills/${encodeURIComponent(name)}/meta`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ similar_to }),
    });
    await loadSkills();
  });

  const checkBtn = document.getElementById("btn-check-update");
  if (checkBtn && !checkBtn.disabled) {
    checkBtn.addEventListener("click", async () => {
      const resultEl = document.getElementById("check-update-result");
      resultEl.textContent = "检查中...";
      try {
        const r = await api(`/api/skills/${encodeURIComponent(name)}/check-update`, { method: "POST" });
        resultEl.textContent = r.changed
          ? `源地址内容已变化：旧哈希 ${r.old_hash || "(无)"} -> 新哈希 ${r.new_hash}，请手动比对并决定是否更新。`
          : "内容哈希一致，未检测到变化。";
      } catch (e) {
        resultEl.textContent = `检查失败：${e.message}`;
      }
    });
  }

  document.getElementById("btn-add-log").addEventListener("click", async () => {
    const author = document.getElementById("f-log-author").value.trim();
    const summary = document.getElementById("f-log-summary").value.trim();
    if (!author || !summary) return;
    await api(`/api/skills/${encodeURIComponent(name)}/changelog`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author, summary }),
    });
    await selectSkill(name);
  });
}

document.getElementById("f-category").addEventListener("change", loadSkills);
document.getElementById("f-industry").addEventListener("change", loadSkills);
document.getElementById("f-status").addEventListener("change", loadSkills);
document.getElementById("btn-sync").addEventListener("click", async () => {
  const r = await api("/api/sync", { method: "POST" });
  alert(r.returncode === 0 ? "同步成功" : `同步失败:\n${r.stderr}`);
});

(async function init() {
  await loadTaxonomy();
  await loadSkills();
})();



