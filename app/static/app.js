const appRoot = document.querySelector("#app");
const toast = document.querySelector("#toast");
let pollTimer = null;
const API_TIMEOUT_MS = 20000;

const statusLabels = {
  pending: "대기",
  in_progress: "진행 중",
  done: "완료",
  error: "오류",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function encodeSlug(value) {
  return encodeURIComponent(value);
}

function notify(message, isError = false) {
  toast.textContent = message;
  toast.className = `toast visible${isError ? " error" : ""}`;
  window.setTimeout(() => {
    toast.className = "toast";
  }, 3200);
}

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
      signal: controller.signal,
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const payload = await response.json();
        detail = payload.detail || detail;
      } catch {
        // Preserve the HTTP status when the response has no JSON body.
      }
      throw new Error(detail);
    }
    if (response.status === 204) return null;
    return response.json();
  } catch (error) {
    if (error.name === "AbortError") {
      const message = "서버 응답이 지연되고 있습니다. 잠시 후 다시 시도하세요.";
      notify(message, true);
      throw new Error(message);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function stopPolling() {
  if (pollTimer) {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function enableInPageAnchors(container) {
  container.addEventListener("click", (event) => {
    const link = event.target.closest('a[href^="#"]');
    if (!link) return;
    const targetId = link.getAttribute("href").slice(1);
    const target = document.getElementById(targetId);
    if (target) {
      event.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
}

function setLoading(label = "불러오는 중…") {
  appRoot.innerHTML = `
    <section class="panel loading-panel">
      <div class="spinner" aria-hidden="true"></div>
      <p>${escapeHtml(label)}</p>
    </section>`;
}

function renderError(error) {
  appRoot.innerHTML = `
    <section class="panel empty-state">
      <p class="eyebrow">문제가 발생했습니다</p>
      <h1>${escapeHtml(error.message)}</h1>
      <p class="muted">잠시 뒤 다시 시도하거나 홈으로 돌아가세요.</p>
      <a class="button" href="#/">홈으로</a>
    </section>`;
}

function progressText(completed, total) {
  return total ? `${completed}/${total}` : "0/0";
}

async function renderHome() {
  setLoading("저장된 주제를 불러오는 중…");
  const topics = await api("/api/topics");
  appRoot.innerHTML = `
    <section class="hero">
      <div>
        <p class="eyebrow">개인 학습 리서치</p>
        <h1>무엇을 깊이 공부할까요?</h1>
        <p>먼저 목차를 확인하고, 필요한 섹션만 골라 리서치할 수 있습니다.</p>
      </div>
      <a class="button button-primary" href="#/new">새 주제 만들기</a>
    </section>
    <section>
      <div class="section-heading">
        <div>
          <p class="eyebrow">라이브러리</p>
          <h2>내 주제</h2>
        </div>
        <span class="count">${topics.length}개</span>
      </div>
      <div class="topic-grid">
        ${
          topics.length
            ? topics.map(topicCard).join("")
            : `<article class="panel empty-state">
                <h3>아직 저장된 주제가 없습니다</h3>
                <p class="muted">첫 목차를 만들어 학습 계획을 시작하세요.</p>
                <a class="text-link" href="#/new">새 주제 만들기 →</a>
              </article>`
        }
      </div>
    </section>`;

  appRoot.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const slug = button.dataset.delete;
      if (!window.confirm("이 주제와 모든 리서치 파일을 삭제할까요?")) return;
      button.disabled = true;
      try {
        await api(`/api/topics/${encodeSlug(slug)}`, { method: "DELETE" });
        notify("주제를 삭제했습니다.");
        await renderHome();
      } catch (error) {
        button.disabled = false;
        notify(error.message, true);
      }
    });
  });
}

function topicCard(topic) {
  const created = topic.created_at
    ? new Date(topic.created_at).toLocaleDateString("ko-KR")
    : "날짜 없음";
  const percent = topic.total_sections
    ? Math.round((topic.completed_sections / topic.total_sections) * 100)
    : 0;
  const slug = encodeSlug(topic.slug);
  return `
    <article class="panel topic-card">
      <div class="card-topline">
        <span class="depth">${escapeHtml(topic.depth || "standard")}</span>
        <time>${escapeHtml(created)}</time>
      </div>
      <h3>${escapeHtml(topic.topic)}</h3>
      <div class="progress-row">
        <div class="progress-track" aria-label="진행률 ${percent}%">
          <span style="width: ${percent}%"></span>
        </div>
        <strong>${progressText(topic.completed_sections, topic.total_sections)}</strong>
      </div>
      <div class="card-actions">
        <a class="button button-small" href="#/topic/${slug}/progress">열기</a>
        ${
          topic.has_study_document
            ? `<a class="button button-small button-ghost" href="/api/topics/${slug}/download">다운로드</a>`
            : ""
        }
        <button class="button button-small button-danger" data-delete="${escapeHtml(topic.slug)}">삭제</button>
      </div>
    </article>`;
}

function renderNewTopic() {
  appRoot.innerHTML = `
    <section class="narrow">
      <a class="back-link" href="#/">← 내 주제</a>
      <article class="panel form-panel">
        <p class="eyebrow">새 학습 계획</p>
        <h1>먼저 목차부터 만듭니다</h1>
        <p class="muted">본문 리서치는 목차를 확인한 뒤 직접 시작합니다.</p>
        <form id="new-topic-form">
          <label>
            공부할 주제
            <textarea name="topic" rows="3" required maxlength="500" placeholder="예: 양자 컴퓨팅의 원리와 현재 응용"></textarea>
          </label>
          <div class="form-grid">
            <label>
              깊이
              <select name="depth">
                <option value="standard">Standard · 핵심 6개 섹션</option>
                <option value="deep">Deep · 심화 10개 섹션</option>
              </select>
            </label>
            <label>
              섹션 수 <span class="optional">(선택)</span>
              <input name="num_sections" type="number" min="2" max="20" placeholder="자동">
            </label>
          </div>
          <button class="button button-primary button-wide" type="submit">목차 생성</button>
        </form>
      </article>
    </section>`;

  const form = document.querySelector("#new-topic-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    const data = new FormData(form);
    const payload = {
      topic: data.get("topic").trim(),
      depth: data.get("depth"),
    };
    if (data.get("num_sections")) {
      payload.num_sections = Number(data.get("num_sections"));
    }
    button.disabled = true;
    button.textContent = "목차를 설계하는 중…";
    try {
      const result = await api("/api/topics", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const slug = result.manifest.topic_slug;
      window.location.hash = `#/topic/${encodeSlug(slug)}/toc`;
    } catch (error) {
      button.disabled = false;
      button.textContent = "목차 생성";
      notify(error.message, true);
    }
  });
}

async function renderToc(slug, isPoll = false) {
  if (!isPoll) setLoading("목차를 불러오는 중…");
  const detail = await api(`/api/topics/${encodeSlug(slug)}`);
  const { toc, manifest } = detail;
  const isRunning = manifest.sections.some((section) => section.status === "in_progress");
  appRoot.innerHTML = `
    ${
      isRunning
        ? `<p class="panel research-notice">리서치가 진행 중입니다. 자동으로 갱신됩니다.</p>`
        : ""
    }
    <section class="page-heading">
      <div>
        <a class="back-link" href="#/">← 내 주제</a>
        <p class="eyebrow">${escapeHtml(manifest.depth)} 목차</p>
        <h1>${escapeHtml(manifest.topic)}</h1>
        <p>목차만 저장해도 좋습니다. 준비되면 전체 또는 원하는 섹션만 시작하세요.</p>
      </div>
      <button id="build-all" class="button button-primary" ${isRunning ? "disabled" : ""}>전체 리서치 시작</button>
    </section>
    <div class="toc-list">
      ${toc.map((section) => tocSection(section, manifest, isRunning)).join("")}
    </div>`;

  document.querySelector("#build-all").addEventListener("click", async (event) => {
    event.currentTarget.disabled = true;
    try {
      await api(`/api/topics/${encodeSlug(slug)}/build`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      window.location.hash = `#/topic/${encodeSlug(slug)}/progress`;
    } catch (error) {
      event.currentTarget.disabled = false;
      notify(error.message, true);
    }
  });
  appRoot.querySelectorAll("[data-research-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await api(
          `/api/topics/${encodeSlug(slug)}/sections/${encodeURIComponent(button.dataset.researchSection)}/research`,
          { method: "POST" },
        );
        window.location.hash = `#/topic/${encodeSlug(slug)}/progress`;
      } catch (error) {
        button.disabled = false;
        notify(error.message, true);
      }
    });
  });

  if (isRunning && window.location.hash.endsWith("/toc")) {
    pollTimer = window.setTimeout(() => {
      renderToc(slug, true).catch((error) => {
        notify(error.message, true);
        pollTimer = window.setTimeout(() => renderToc(slug, true), 5000);
      });
    }, 3000);
  }
}

function tocSection(section, manifest, isRunning) {
  const state = manifest.sections.find((item) => item.id === section.id);
  const disabled =
    isRunning || state?.status === "in_progress" || state?.status === "done";
  const buttonText =
    state?.status === "in_progress"
      ? "진행 중…"
      : state?.status === "done"
        ? "리서치 완료"
        : "이 섹션만 리서치";
  return `
    <article class="panel toc-item">
      <div class="section-number">${escapeHtml(section.id)}</div>
      <div class="toc-content">
        <div class="toc-title-row">
          <div>
            <h2>${escapeHtml(section.title)}</h2>
            <p>${escapeHtml(section.description)}</p>
          </div>
          <button class="button button-small button-ghost"
            data-research-section="${escapeHtml(section.id)}"
            ${disabled ? "disabled" : ""}>
            ${buttonText}
          </button>
        </div>
        <ul>
          ${(section.subsections || [])
            .map(
              (subsection) =>
                `<li><strong>${escapeHtml(subsection.title)}</strong><span>${escapeHtml(subsection.description)}</span></li>`,
            )
            .join("")}
        </ul>
      </div>
    </article>`;
}

async function renderProgress(slug, isPoll = false) {
  if (!isPoll) setLoading("리서치 상태를 확인하는 중…");
  const detail = await api(`/api/topics/${encodeSlug(slug)}`);
  const { manifest } = detail;
  const completed = manifest.sections.filter((section) => section.status === "done").length;
  const running = manifest.sections.some((section) => section.status === "in_progress");
  const hasDocument = Boolean(manifest.study_document);
  const percent = manifest.sections.length
    ? Math.round((completed / manifest.sections.length) * 100)
    : 0;

  appRoot.innerHTML = `
    <section class="page-heading progress-heading">
      <div>
        <a class="back-link" href="#/">← 내 주제</a>
        <p class="eyebrow">${running ? "리서치 진행 중" : "리서치 상세"}</p>
        <h1>${escapeHtml(manifest.topic)}</h1>
      </div>
      <a class="button button-ghost" href="#/topic/${encodeSlug(slug)}/toc">목차와 작업 선택</a>
    </section>
    <section class="panel progress-overview">
      <div>
        <strong>${progressText(completed, manifest.sections.length)}</strong>
        <span>섹션 완료</span>
      </div>
      <div class="progress-track large" aria-label="진행률 ${percent}%">
        <span style="width: ${percent}%"></span>
      </div>
      <span>${percent}%</span>
    </section>
    <section class="status-list">
      ${manifest.sections.map((section) => statusRow(section, slug)).join("")}
    </section>
    <section class="footer-actions">
      ${
        hasDocument
          ? `<a class="button button-primary" href="#/topic/${encodeSlug(slug)}/document">전체 문서 보기</a>
             <a class="button button-ghost" href="/api/topics/${encodeSlug(slug)}/download">다운로드</a>`
          : `<span class="muted">${running ? "완료될 때까지 자동으로 갱신합니다." : "전체 리서치를 시작하면 최종 문서가 조립됩니다."}</span>`
      }
      <button id="delete-topic" class="button button-danger" ${running ? "disabled" : ""}>주제 삭제</button>
    </section>`;

  document.querySelector("#delete-topic").addEventListener("click", async () => {
    if (!window.confirm("이 주제와 모든 리서치 파일을 삭제할까요?")) return;
    try {
      await api(`/api/topics/${encodeSlug(slug)}`, { method: "DELETE" });
      notify("주제를 삭제했습니다.");
      window.location.hash = "#/";
    } catch (error) {
      notify(error.message, true);
    }
  });

  if (window.location.hash.endsWith("/progress")) {
    pollTimer = window.setTimeout(() => {
      renderProgress(slug, true).catch((error) => {
        notify(error.message, true);
        pollTimer = window.setTimeout(() => renderProgress(slug, true), 5000);
      });
    }, 3000);
  }
}

function statusRow(section, slug) {
  return `
    <article class="panel status-row">
      <span class="status-dot ${escapeHtml(section.status)}" aria-hidden="true"></span>
      <div>
        <h3>${escapeHtml(section.id)}. ${escapeHtml(section.title)}</h3>
        <p>${section.source_count || 0}개 출처</p>
      </div>
      <div class="status-actions">
        ${
          section.status === "done"
            ? `<a class="button button-small button-ghost"
                href="#/topic/${encodeSlug(slug)}/section/${encodeURIComponent(section.id)}">보기</a>`
            : ""
        }
        <span class="status-badge ${escapeHtml(section.status)}">
          ${escapeHtml(statusLabels[section.status] || section.status)}
        </span>
      </div>
    </article>`;
}

async function renderDocument(slug) {
  setLoading("문서를 불러오는 중…");
  const resp = await fetch(`/api/topics/${encodeSlug(slug)}/document`, {
    credentials: "same-origin",
  });
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  const text = await resp.text();
  appRoot.innerHTML = `
    <section class="narrow">
      <a class="back-link" href="#/topic/${encodeSlug(slug)}/progress">← 돌아가기</a>
      <div class="footer-actions" style="margin-bottom:1rem">
        <a class="button button-ghost" href="/api/topics/${encodeSlug(slug)}/download">다운로드</a>
      </div>
      <article class="panel prose">${marked.parse(text)}</article>
    </section>`;
  enableInPageAnchors(appRoot.querySelector(".prose"));
}

async function renderSectionDocument(slug, sectionId) {
  setLoading("섹션 문서를 불러오는 중…");
  const resp = await fetch(
    `/api/topics/${encodeSlug(slug)}/sections/${encodeURIComponent(sectionId)}`,
    { credentials: "same-origin" },
  );
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  const text = await resp.text();
  appRoot.innerHTML = `
    <section class="narrow">
      <a class="back-link" href="#/topic/${encodeSlug(slug)}/progress">← 돌아가기</a>
      <article class="panel prose">${marked.parse(text)}</article>
    </section>`;
  enableInPageAnchors(appRoot.querySelector(".prose"));
}

async function route() {
  stopPolling();
  const parts = window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  try {
    if (parts.length === 0) {
      await renderHome();
    } else if (parts[0] === "new") {
      renderNewTopic();
    } else if (parts[0] === "topic" && (parts.length === 3 || parts.length === 4)) {
      const slug = decodeURIComponent(parts[1]);
      if (parts[2] === "toc" && parts.length === 3) await renderToc(slug);
      else if (parts[2] === "progress" && parts.length === 3) await renderProgress(slug);
      else if (parts[2] === "document" && parts.length === 3) await renderDocument(slug);
      else if (parts[2] === "section" && parts.length === 4) {
        await renderSectionDocument(slug, decodeURIComponent(parts[3]));
      }
      else window.location.hash = "#/";
    } else {
      window.location.hash = "#/";
    }
  } catch (error) {
    renderError(error);
  }
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", route);
