const appRoot = document.querySelector("#app");
const toast = document.querySelector("#toast");
let pollTimer = null;
const API_TIMEOUT_MS = 20000;

const statusLabels = {
  idle: "대기",
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

function safeExternalUrl(value) {
  try {
    const url = new URL(String(value));
    return ["http:", "https:"].includes(url.protocol) ? escapeHtml(url.href) : "#";
  } catch {
    return "#";
  }
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

function watchChangeSummary(run) {
  if (!run) return '<p class="muted">아직 실행 기록이 없습니다.</p>';
  const changes = run.changes || {};
  if (changes.outcome === "initial") {
    return `<p class="research-notice">첫 검색 스냅샷 · 최근 상위 10개 중 ${run.findings.length}개 결과</p>`;
  }
  if (changes.outcome === "no_change") {
    return '<p class="research-notice">최근 상위 10개 검색 결과 변경 없음 · 정확한 URL 비교</p>';
  }
  const links = (items, label) => items.length
    ? `<section><h3>${label} ${items.length}건</h3><ul>${items.map((item) => {
        const finding = item.after || item;
        return `<li><a href="${safeExternalUrl(finding.url)}" target="_blank" rel="noreferrer">${escapeHtml(finding.title)}</a><p>${escapeHtml(finding.snippet)}</p></li>`;
      }).join("")}</ul></section>`
    : "";
  return `<div class="watch-changes">
    ${links(changes.added || [], "검색 결과에 추가")}
    ${links(changes.changed || [], "제목/검색 요약 변경")}
    ${links(changes.removed || [], "검색 결과에서 제외")}
  </div>`;
}

async function renderWatches() {
  setLoading("관심 주제를 불러오는 중…");
  const watches = await api("/api/watches");
  appRoot.innerHTML = `
    <section class="page-heading">
      <div><a class="back-link" href="#/">← 내 주제</a><p class="eyebrow">지속 리서치</p><h1>관심 주제</h1>
      <p>최근 상위 10개 검색 결과를 정확한 URL로 비교해 검색 결과의 변화를 확인합니다.</p></div>
      <div class="hero-actions"><a class="button button-ghost" href="#/watches/guide">사용 가이드</a><a class="button button-primary" href="#/watches/new">관심 주제 등록</a></div>
    </section>
    <div class="topic-grid">${watches.length ? watches.map((watch) => `
      <article class="panel topic-card"><div class="card-topline"><span class="status-badge ${escapeHtml(watch.status)}">${escapeHtml(statusLabels[watch.status] || watch.status)}</span><span>${watch.interval_minutes ? `${watch.interval_minutes}분마다` : "수동"}</span></div>
      <h3>${escapeHtml(watch.topic)}</h3><p class="muted">${watch.last_error ? escapeHtml(watch.last_error) : "최근 오류 없음"}</p>
      <div class="card-actions"><a class="button button-small" href="#/watches/${encodeSlug(watch.slug)}">열기</a></div></article>`).join("") : '<article class="panel empty-state"><h3>등록된 관심 주제가 없습니다</h3></article>'}</div>`;
}

function renderNewWatch() {
  appRoot.innerHTML = `<section class="narrow"><a class="back-link" href="#/watches">← 관심 주제</a>
    <article class="panel form-panel"><p class="eyebrow">지속 리서치</p><h1>관심 주제 등록</h1>
    <form id="new-watch-form"><label>검색 주제<input name="topic" required maxlength="500"></label>
    <label>자동 새로고침 간격 <span class="optional">(비우면 수동)</span><input name="interval" type="number" min="5" max="10080" placeholder="분"></label>
    <button class="button button-primary" type="submit">등록</button></form></article></section>`;
  const form = document.querySelector("#new-watch-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const payload = { topic: data.get("topic").trim(), interval_minutes: data.get("interval") ? Number(data.get("interval")) : null };
    const watch = await api("/api/watches", { method: "POST", body: JSON.stringify(payload) });
    window.location.hash = `#/watches/${encodeSlug(watch.slug)}`;
  });
}

async function renderWatch(slug, isPoll = false) {
  if (!isPoll) setLoading("변화 기록을 불러오는 중…");
  const detail = await api(`/api/watches/${encodeSlug(slug)}`);
  const { watch, current_run: run } = detail;
  const busy = ["pending", "running"].includes(watch.status);
  appRoot.innerHTML = `<section class="page-heading"><div><a class="back-link" href="#/watches">← 관심 주제</a><p class="eyebrow">${escapeHtml(watch.status)}</p><h1>${escapeHtml(watch.topic)}</h1>
    <p>${watch.interval_minutes ? `${watch.interval_minutes}분 간격 · 다음 실행 ${escapeHtml(watch.next_run_at || "계산 중")}` : "수동 새로고침"}</p></div>
    <button id="refresh-watch" class="button button-primary" ${busy ? "disabled" : ""}>${busy ? "새로고침 중…" : "지금 새로고침"}</button></section>
    ${watch.last_error ? `<p class="panel research-notice error">${escapeHtml(watch.last_error)} · 다시 시도할 수 있습니다.</p>` : ""}
    <article class="panel form-panel"><h2>최근 검색 결과 변화</h2><p class="muted">제목·검색 요약 변화이며, 사실이나 세계 상태의 변화를 검증한 결과는 아닙니다.</p>${watchChangeSummary(run)}</article>
    <article class="panel watch-settings"><h2>자동 새로고침</h2><form id="watch-interval-form" class="inline-form">
      <label>간격(분, 5~10080; 비우면 수동)<input name="interval" type="number" min="5" max="10080" value="${watch.interval_minutes || ""}" ${busy ? "disabled" : ""}></label>
      <button class="button button-ghost" type="submit" ${busy ? "disabled" : ""}>설정 저장</button></form></article>
    <section class="footer-actions"><a class="button button-ghost" href="#/watches/guide">사용 가이드</a><button id="delete-watch" class="button button-danger" ${busy ? "disabled" : ""}>관심 주제 삭제</button></section>`;
  document.querySelector("#refresh-watch").addEventListener("click", async () => {
    await api(`/api/watches/${encodeSlug(slug)}/refresh`, { method: "POST" });
    await renderWatch(slug, true);
  });
  document.querySelector("#delete-watch").addEventListener("click", async () => {
    if (!window.confirm("이 관심 주제와 실행 기록을 삭제할까요?")) return;
    await api(`/api/watches/${encodeSlug(slug)}`, { method: "DELETE" });
    window.location.hash = "#/watches";
  });
  document.querySelector("#watch-interval-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("interval");
    await api(`/api/watches/${encodeSlug(slug)}`, { method: "PATCH", body: JSON.stringify({ interval_minutes: value ? Number(value) : null }) });
    notify("새로고침 간격을 저장했습니다.");
    await renderWatch(slug, true);
  });
  if (busy && window.location.hash.includes("#/watches/")) {
    pollTimer = window.setTimeout(() => renderWatch(slug, true), 3000);
  }
}

function renderWatchGuide() {
  appRoot.innerHTML = `<section class="narrow"><a class="back-link" href="#/watches">← 관심 주제</a>
    <article class="panel prose watch-guide"><p class="eyebrow">관심 주제 사용 가이드</p><h1>변화를 놓치지 않는 방법</h1>
    <h2>1. 주제 등록</h2><p>관심 주제 화면에서 검색할 주제를 등록합니다. 같은 이름은 중복 등록되지 않습니다.</p>
    <h2>2. 수동 새로고침</h2><p>상세 화면의 <strong>지금 새로고침</strong>을 누르면 기존 Researcher 검색 파이프라인으로 최신 출처를 수집합니다.</p>
    <h2>3. 예약 새로고침</h2><p>5~10080분 사이의 간격을 저장하면 서버가 실행 중일 때 예약 시각에 새로고침합니다. 값을 비우면 수동 모드입니다.</p>
    <h2>4. 변화 읽기</h2><p>각 실행의 <strong>최근 상위 10개 검색 결과</strong>를 <strong>정확한 URL</strong>로 비교합니다. <strong>검색 결과에 추가</strong>는 새 URL, <strong>제목/검색 요약 변경</strong>은 같은 URL의 제목·검색 요약 변화, <strong>검색 결과에서 제외</strong>는 이번 상위 결과에서 사라진 URL입니다. 차이가 없으면 <strong>검색 결과 변경 없음</strong>으로 표시합니다. 이는 검색 결과의 변동이며 사실이나 세계 상태의 변화를 검증한 결과가 아닙니다.</p>
    <h2>5. 실패와 재시도</h2><p>검색 오류나 빈 결과는 오류 상태로 남고 기존 스냅샷을 보존합니다. 예약 실행 실패 후 자동 재시도는 설정한 다음 간격까지 기다리지만, 지금 새로고침을 누른 수동 재시도는 즉시 시작됩니다.</p>
    <h2>6. 저장과 재시작</h2><p>등록 정보와 최근·이전 스냅샷은 출력 디렉터리에 원자적으로 저장됩니다. 서버 재시작 시 지난 예약 실행을 재생하지 않고 시작 시각부터 다음 간격으로 예약을 다시 잡으며, 중단된 실행은 오류로 표시합니다.</p>
    <h2>알려진 한계</h2><p>스케줄러는 단일 프로세스에서 동작하는 best-effort 방식입니다. 서버가 꺼진 동안 실행하지 않으며, 라이브 결과는 실행 중인 SearXNG와 선택한 API 제공자 접근 상태에 따라 달라집니다.</p>
    </article></section>`;
}

function sectionNeighbors(toc, manifestSections, sectionId) {
  const index = toc.findIndex((section) => section.id === sectionId);
  const statusById = new Map(
    manifestSections.map((section) => [section.id, section.status]),
  );
  const neighbor = (offset) => {
    const section = toc[index + offset];
    if (index < 0 || !section) return null;
    return {
      id: section.id,
      title: section.title,
      available: statusById.get(section.id) === "done",
    };
  };
  return { previous: neighbor(-1), next: neighbor(1) };
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
      <div class="hero-actions">
        <a class="button button-ghost" href="#/logs">서버 로그</a>
        <a class="button button-primary" href="#/new">새 주제 만들기</a>
      </div>
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
  const tocStatus = topic.toc_status || "done";
  const progressOrStatus =
    tocStatus === "generating"
      ? '<span class="status-badge in_progress">목차 생성 중</span>'
      : tocStatus === "error"
        ? '<span class="status-badge error">목차 생성 실패</span>'
        : `<div class="progress-row">
            <div class="progress-track" aria-label="진행률 ${percent}%">
              <span style="width: ${percent}%"></span>
            </div>
            <strong>${progressText(topic.completed_sections, topic.total_sections)}</strong>
          </div>`;
  const openDestination = tocStatus === "done" ? "progress" : "toc";
  return `
    <article class="panel topic-card">
      <div class="card-topline">
        <span class="depth">${escapeHtml(topic.depth || "standard")}</span>
        <time>${escapeHtml(created)}</time>
      </div>
      <h3>${escapeHtml(topic.topic)}</h3>
      ${progressOrStatus}
      <div class="card-actions">
        <a class="button button-small" href="#/topic/${slug}/${openDestination}">열기</a>
        ${
          topic.has_study_document
            ? `<a class="button button-small button-ghost" href="/api/topics/${slug}/download">다운로드 (MD)</a>
               <a class="button button-small button-ghost" href="/api/topics/${slug}/download?format=excel">다운로드 (Excel)</a>
               <a class="button button-small button-ghost" href="/api/topics/${slug}/download?format=zip">다운로드 (섹션별 ZIP)</a>`
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
      const slug = result.slug;
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
  const tocStatus = manifest.toc_status || "done";
  if (tocStatus !== "done") {
    const isGenerating = tocStatus === "generating";
    appRoot.innerHTML = `
      <section class="narrow">
        <a class="back-link" href="#/">← 내 주제</a>
        <article class="panel">
          <p class="eyebrow">${escapeHtml(manifest.depth)} 목차</p>
          <h1>${escapeHtml(manifest.topic)}</h1>
          ${
            isGenerating
              ? '<p class="research-notice">목차를 생성하는 중입니다… 자동으로 갱신됩니다.</p>'
              : `<p class="status-badge error">목차 생성 실패</p>
                 <p>${escapeHtml(manifest.toc_error || "알 수 없는 오류")}</p>
                 <button id="delete-topic" class="button button-danger">주제 삭제</button>`
          }
        </article>
      </section>`;
    if (isGenerating) {
      if (window.location.hash.endsWith("/toc")) {
        pollTimer = window.setTimeout(() => {
          renderToc(slug, true).catch((error) => {
            notify(error.message, true);
            pollTimer = window.setTimeout(() => renderToc(slug, true), 5000);
          });
        }, 3000);
      }
    } else {
      document.querySelector("#delete-topic").addEventListener("click", async () => {
        if (!window.confirm("이 주제를 삭제할까요?")) return;
        try {
          await api(`/api/topics/${encodeSlug(slug)}`, { method: "DELETE" });
          notify("주제를 삭제했습니다.");
          window.location.hash = "#/";
        } catch (error) {
          notify(error.message, true);
        }
      });
    }
    return;
  }
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

  document.querySelector("#build-all").addEventListener("click", (event) => {
    event.currentTarget.disabled = true;
    api(`/api/topics/${encodeSlug(slug)}/build`, {
      method: "POST",
      body: JSON.stringify({}),
    }).catch((error) => {
      notify(error.message, true);
    });
    window.location.hash = `#/topic/${encodeSlug(slug)}/progress`;
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
             <a class="button button-ghost" href="/api/topics/${encodeSlug(slug)}/download">다운로드 (MD)</a>
             <a class="button button-ghost" href="/api/topics/${encodeSlug(slug)}/download?format=excel">다운로드 (Excel)</a>
             <a class="button button-ghost" href="/api/topics/${encodeSlug(slug)}/download?format=zip">다운로드 (섹션별 ZIP)</a>`
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
        <a class="button button-ghost" href="/api/topics/${encodeSlug(slug)}/download">다운로드 (MD)</a>
        <a class="button button-ghost" href="/api/topics/${encodeSlug(slug)}/download?format=excel">다운로드 (Excel)</a>
        <a class="button button-ghost" href="/api/topics/${encodeSlug(slug)}/download?format=zip">다운로드 (섹션별 ZIP)</a>
      </div>
      <article class="panel prose">${marked.parse(text)}</article>
    </section>`;
  enableInPageAnchors(appRoot.querySelector(".prose"));
}

async function renderSectionDocument(slug, sectionId) {
  setLoading("섹션 문서를 불러오는 중…");
  const [resp, detail] = await Promise.all([
    fetch(
      `/api/topics/${encodeSlug(slug)}/sections/${encodeURIComponent(sectionId)}`,
      { credentials: "same-origin" },
    ),
    api(`/api/topics/${encodeSlug(slug)}`),
  ]);
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  const text = await resp.text();
  const neighbors = sectionNeighbors(detail.toc, detail.manifest.sections, sectionId);
  const neighborButton = (neighbor, label) => {
    if (!neighbor) return '<span class="section-nav-spacer"></span>';
    if (!neighbor.available) {
      return `<span class="button button-ghost button-disabled" aria-disabled="true"
        title="${escapeHtml(neighbor.title)}">${escapeHtml(label)}</span>`;
    }
    return `<a class="button button-ghost"
      href="#/topic/${encodeSlug(slug)}/section/${encodeURIComponent(neighbor.id)}"
      title="${escapeHtml(neighbor.title)}">${escapeHtml(label)}</a>`;
  };
  const previousButton = neighborButton(neighbors.previous, "← 이전 섹션");
  const nextButton = neighborButton(neighbors.next, "다음 섹션 →");
  const sectionNavigation = `
    <nav class="section-nav" aria-label="섹션 이동">
      ${previousButton}
      ${nextButton}
    </nav>`;
  appRoot.innerHTML = `
    <section class="narrow">
      <a class="back-link" href="#/topic/${encodeSlug(slug)}/progress">← 돌아가기</a>
      ${sectionNavigation}
      <article class="panel prose">${marked.parse(text)}</article>
      ${sectionNavigation}
    </section>`;
  enableInPageAnchors(appRoot.querySelector(".prose"));
}

async function renderLogs() {
  appRoot.innerHTML = `
    <section class="page-heading logs-heading">
      <div>
        <a class="back-link" href="#/">← 내 주제</a>
        <p class="eyebrow">운영 상태</p>
        <h1>서버 로그</h1>
        <p>최근 1,000개 로그를 보여주며 4초마다 새 항목을 가져옵니다.</p>
      </div>
      <span id="log-status" class="count">연결 중</span>
    </section>
    <section class="panel log-panel">
      <p id="log-empty" class="muted">표시할 로그가 없습니다.</p>
      <ol id="log-list" class="log-list"></ol>
    </section>`;

  const list = document.querySelector("#log-list");
  const empty = document.querySelector("#log-empty");
  const status = document.querySelector("#log-status");
  let lastId = 0;

  const poll = async () => {
    try {
      const records = await api(`/api/logs?after_id=${lastId}&limit=200`);
      for (const record of records) {
        list.insertAdjacentHTML(
          "beforeend",
          `<li class="log-entry level-${escapeHtml(record.level).toLowerCase()}">
            <time>${escapeHtml(new Date(record.timestamp).toLocaleString("ko-KR"))}</time>
            <strong>${escapeHtml(record.level)}</strong>
            <span class="log-name">${escapeHtml(record.logger)}</span>
            <span class="log-message">${escapeHtml(record.message)}</span>
          </li>`,
        );
        lastId = Math.max(lastId, Number(record.id));
      }
      empty.hidden = list.children.length > 0;
      status.textContent = `최근 ID ${lastId}`;
    } catch (error) {
      status.textContent = "연결 오류";
      notify(error.message, true);
    } finally {
      if (window.location.hash === "#/logs") {
        pollTimer = window.setTimeout(poll, 4000);
      }
    }
  };

  await poll();
}

async function route() {
  stopPolling();
  const parts = window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  try {
    if (parts.length === 0) {
      await renderHome();
    } else if (parts[0] === "new") {
      renderNewTopic();
    } else if (parts[0] === "logs" && parts.length === 1) {
      await renderLogs();
    } else if (parts[0] === "watches" && parts.length === 1) {
      await renderWatches();
    } else if (parts[0] === "watches" && parts[1] === "new") {
      renderNewWatch();
    } else if (parts[0] === "watches" && parts[1] === "guide") {
      renderWatchGuide();
    } else if (parts[0] === "watches" && parts.length === 2) {
      await renderWatch(decodeURIComponent(parts[1]));
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
