/* Dependency-free browser client for the FastAPI application. */
(() => {
  "use strict";

  const API = "/api/v1";
  const SESSION_KEY = "eki.session";
  const app = document.getElementById("app");
  const state = {
    session: readSession(),
    profile: null,
    profileToken: null,
    messages: [],
    documents: [],
    documentsOffset: 0,
    documentsLimit: 50,
    documentSearch: "",
    activeDocument: null,
    versions: [],
    selectedVersion: null,
    chunks: [],
    chunksOffset: 0,
    chunksLimit: 50,
    selectedFiles: [],
    uploadResults: [],
    loading: false,
    error: "",
    success: "",
    deleteOpen: false,
    auditEvents: [],
    auditOffset: 0,
    auditLimit: 50,
    report: null,
  };

  function readSession() {
    try { return JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null"); }
    catch { return null; }
  }

  function saveSession(session) {
    state.session = session;
    state.profile = null;
    state.profileToken = null;
    if (session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else sessionStorage.removeItem(SESSION_KEY);
  }

  function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
  }

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  function safeError(error) {
    if (!(error instanceof ApiError)) return "The service could not be reached. Check that the API is running and try again.";
    if (error.status === 401) return "Your session has expired. Sign in again to continue.";
    if (error.status === 403) return "You do not have permission to do that.";
    if (error.status === 404) return "This item is unavailable or you do not have access to it.";
    if (error.status === 413 || error.status === 415 || error.status === 400 || error.status === 422) return error.message;
    if (error.status === 429) return "Too many requests. Wait a moment, then try again.";
    if (error.status === 502) return "The answer service could not respond. Check that the configured generation provider is running, then try again.";
    if (error.status === 503) return "A required service or request-protection component is unavailable. Try again shortly.";
    if (error.status >= 500) return "The backend encountered an internal error. Check the FastAPI logs for details, then try again.";
    return "The request could not be completed. Please try again.";
  }

  async function api(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (state.session?.token && options.auth !== false) {
      headers.set("Authorization", `Bearer ${state.session.token}`);
    }
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
    });
    if (response.status === 401 && options.auth !== false) {
      saveSession(null);
      state.messages = [];
      if (!location.hash.startsWith("#/login")) navigate("/login");
    }
    if (!response.ok) {
      let detail = "";
      try {
        const body = await response.json();
        detail = typeof body.detail === "string" ? body.detail : "";
      } catch { /* Use a safe status-specific message below. */ }
      throw new ApiError(response.status, detail || `Request failed (${response.status}).`);
    }
    if (response.status === 204) return null;
    const contentType = response.headers.get("content-type") || "";
    return contentType.includes("application/json") ? response.json() : response.blob();
  }

  function navigate(path) {
    location.hash = `#${path}`;
  }

  function currentRoute() {
    const route = location.hash.replace(/^#/, "") || "/";
    if (route === "/" && state.session) return "/ask";
    if (route === "/") return "/login";
    return route;
  }

  function alertHTML(message, success = false) {
    if (!message) return "";
    return `<div class="alert ${success ? "success" : ""}" role="status">${escapeHTML(message)}</div>`;
  }

  function initials(email) {
    return (email || "User").split("@")[0].split(/[._-]/).filter(Boolean).slice(0, 2)
      .map((part) => part[0].toUpperCase()).join("") || "U";
  }

  function shell(active, content, narrow = false) {
    const email = state.session?.email || "Signed-in user";
    const role = state.profile?.role;
    return `<div class="app-shell">
      <a class="skip-link" href="#main-content">Skip to main content</a>
      <aside class="sidebar">
        <a class="brand" href="#/ask" aria-label="Knowledge Intelligence home"><span class="brand-mark">K</span><span>Knowledge Intelligence</span></a>
        <nav class="nav" aria-label="Main navigation">
          <a class="nav-link ${active === "ask" ? "active" : ""}" href="#/ask"><span class="nav-icon" aria-hidden="true">✳</span>Ask</a>
          <a class="nav-link ${active === "documents" ? "active" : ""}" href="#/documents"><span class="nav-icon" aria-hidden="true">▤</span>Knowledge base</a>
          ${role === "admin" ? `<a class="nav-link ${active === "audit" ? "active" : ""}" href="#/audit"><span class="nav-icon" aria-hidden="true">◷</span>Audit log</a>` : ""}
          <a class="nav-link ${active === "reports" ? "active" : ""}" href="#/reports"><span class="nav-icon" aria-hidden="true">▤</span>Reports</a>
        </nav>
        <div class="sidebar-bottom"><div class="user-card"><div class="avatar" aria-hidden="true">${escapeHTML(initials(email))}</div><div class="user-meta"><strong>${escapeHTML(email.split("@")[0])}${role ? ` · ${escapeHTML(role)}` : ""}</strong><span>${escapeHTML(email)}</span></div><button type="button" class="signout" data-action="signout" aria-label="Sign out" title="Sign out">↗</button></div></div>
      </aside>
      <div class="main-wrap"><header class="topbar"><span class="crumb">Workspace / ${active === "documents" ? "Knowledge base" : active === "detail" ? "Document details" : "Ask"}</span><span class="topbar-label">Grounded in your accessible documents</span></header>
      <main class="page ${narrow ? "narrow" : ""}" id="main-content" tabindex="-1">${content}</main></div>
    </div>`;
  }

  function authPage(register = false) {
    const title = register ? "Create your account" : "Welcome back";
    const subtitle = register
      ? "Create an account to explore your organization’s knowledge."
      : "Sign in to ask questions across your accessible company documents.";
    const passwordField = (id, label, autocomplete, minLength, placeholder = "") => `
      <div class="field">
        <label for="${id}">${label}</label>
        <div class="password-input-wrap">
          <input class="input" id="${id}" name="${id === "confirm-password" ? "confirmPassword" : "password"}" type="password" autocomplete="${autocomplete}" required minlength="${minLength}" maxlength="128" placeholder="${placeholder}" />
          <button class="password-toggle" type="button" data-action="toggle-password" data-target="${id}" data-show-label="Show ${label.toLowerCase()}" data-hide-label="Hide ${label.toLowerCase()}" aria-controls="${id}" aria-label="Show ${label.toLowerCase()}" title="Show ${label.toLowerCase()}">
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>
          </button>
        </div>
      </div>`;
    app.innerHTML = `<main class="auth-page"><section class="card auth-card" aria-labelledby="auth-title">
      <a class="brand auth-brand" href="#/login"><span class="brand-mark">K</span><span>Knowledge Intelligence</span></a>
      <h1 id="auth-title">${title}</h1><p class="subheading">${subtitle}</p>
      ${alertHTML(state.error)}${alertHTML(state.success, true)}
      <form class="auth-form" id="auth-form" data-mode="${register ? "register" : "login"}" novalidate>
        <div class="field"><label for="email">Work email</label><input class="input" id="email" name="email" type="email" autocomplete="email" required maxlength="320" placeholder="name@company.com" /></div>
        ${passwordField("password", "Password", register ? "new-password" : "current-password", register ? 12 : 1, register ? "At least 12 characters" : "Your password")}
        ${register ? passwordField("confirm-password", "Confirm password", "new-password", 12) : ""}
        <button class="button" type="submit" ${state.loading ? "disabled" : ""}>${state.loading ? "Please wait…" : register ? "Create account" : "Sign in"}</button>
      </form>
      <p class="auth-footer">${register ? "Already have an account?" : "New to the platform?"} <a class="link-button" href="#/${register ? "login" : "register"}">${register ? "Sign in" : "Create an account"}</a></p>
    </section></main>`;
  }

  function answerNodes(text) {
    const fragment = document.createDocumentFragment();
    const parts = String(text || "").split(/(\[Source\s+\d+\]|\*\*[^*]+\*\*)/gi);
    for (const part of parts) {
      const match = part.match(/^\[Source\s+(\d+)\]$/i);
      if (match) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "citation";
        button.dataset.citation = match[1];
        button.textContent = `[Source ${match[1]}]`;
        button.setAttribute("aria-label", `Jump to source ${match[1]}`);
        fragment.append(button);
      } else if (/^\*\*[^*]+\*\*$/.test(part)) {
        const strong = document.createElement("strong");
        strong.textContent = part.slice(2, -2);
        fragment.append(strong);
      } else {
        fragment.append(document.createTextNode(part));
      }
    }
    return fragment;
  }

  function renderAnswer(message, index) {
    const declined = /\b(?:couldn.t|cannot|can.t|unable to|does not contain|doesn.t contain|not available|insufficient evidence|not in the (?:document|provided))\b/i.test(message.answer || "");
    const article = document.createElement("article");
    article.className = `answer-block card ${declined ? "abstain" : ""}`;
    const verification = message.verification;
    const verificationNote = verification?.status === "verified"
      ? `<p class="verification-note" role="status">Local model estimate: cited evidence supports the answer. This is not a guarantee of correctness.</p>`
      : verification?.status === "withheld"
        ? `<p class="verification-note warning" role="status">The answer was withheld because its claims could not be supported by the cited evidence.</p>`
        : verification?.status === "not_run"
          ? `<p class="verification-note warning" role="status">Citation labels were checked; claim support estimation was not run.</p>`
          : "";
    article.innerHTML = `<div class="answer-label ${declined ? "abstain" : ""}"><span class="dot" aria-hidden="true"></span>${declined ? "Insufficient evidence" : "Answer"}</div><div class="answer-text"></div>${verificationNote}${message.sources?.length ? `<details class="evidence-disclosure"><summary>View supporting evidence (${message.sources.length})</summary><div class="source-list"></div></details>` : ""}`;
    article.querySelector(".answer-text").append(answerNodes(message.answer));
    const sourceList = article.querySelector(".source-list");
    (message.sources || []).forEach((source) => {
      const card = document.createElement("section");
      card.className = "source-card card";
      card.id = `answer-${index}-source-${source.source_number}`;
      card.dataset.sourceNumber = String(source.source_number);
      const top = document.createElement("div");
      top.className = "source-top";
      const name = document.createElement("span");
      name.className = "source-name";
      name.textContent = source.document_title || "Source document";
      const filename = document.createElement("span");
      filename.className = "source-filename";
      filename.textContent = source.filename || "";
      const sourceInfo = document.createElement("div");
      sourceInfo.className = "source-info";
      sourceInfo.append(name, filename);
      const number = document.createElement("span");
      number.className = "source-index";
      number.textContent = `Source ${source.source_number}`;
      top.append(sourceInfo, number);
      const excerpt = document.createElement("p");
      excerpt.className = "source-content";
      excerpt.textContent = source.content || "No excerpt available.";
      const excerptLabel = document.createElement("span");
      excerptLabel.className = "excerpt-label";
      excerptLabel.textContent = "Relevant excerpt";
      card.append(top, excerptLabel, excerpt);
      if (source.document_id) {
        const viewDocument = document.createElement("a");
        viewDocument.className = "source-document-link";
        viewDocument.href = `#/documents/${encodeURIComponent(source.document_id)}`;
        viewDocument.textContent = "View full document →";
        card.append(viewDocument);
      }
      sourceList.append(card);
    });
    const feedback = document.createElement("div");
    feedback.className = "answer-feedback";
    if (message.feedbackSubmitted) {
      feedback.innerHTML = `<span class="small-text success-text" role="status">Thank you. Your feedback was saved.</span>`;
    } else {
      feedback.innerHTML = `<div class="feedback-row"><span class="small-text muted">Was this response useful?</span><button class="feedback-button" type="button" data-action="feedback-select" data-index="${index}" data-rating="1" aria-label="Rate this answer as helpful" ${message.feedbackLoading ? "disabled" : ""}>Helpful</button><button class="feedback-button" type="button" data-action="feedback-select" data-index="${index}" data-rating="-1" aria-label="Rate this answer as not helpful" ${message.feedbackLoading ? "disabled" : ""}>Not helpful</button></div><p class="feedback-privacy">Submitting feedback sends this question and answer for quality review.</p>${message.feedbackRating ? `<form class="feedback-form" data-index="${index}"><label class="sr-only" for="feedback-comment-${index}">Optional feedback comment</label><textarea class="input feedback-comment" id="feedback-comment-${index}" name="comment" maxlength="2000" placeholder="Optional comment"></textarea><button class="button secondary small" type="submit" ${message.feedbackLoading ? "disabled" : ""}>${message.feedbackLoading ? "Sending…" : "Submit feedback"}</button></form>` : ""}${message.feedbackError ? `<p class="small-text error-text" role="alert">${escapeHTML(message.feedbackError)}</p>` : ""}`;
    }
    article.append(feedback);
    return article;
  }

  function renderAsk() {
    const heading = state.messages.length
      ? `<section class="conversation-heading"><div><h1>Ask your company knowledge</h1><p class="subheading">Answers are grounded in documents you can access.</p></div><button class="button secondary small" type="button" data-action="new-question">New inquiry</button></section>`
      : `<section class="welcome"><div class="empty-mark" aria-hidden="true">✳</div><h1>Ask your company knowledge.</h1><p class="subheading">Get answers grounded in documents you can access, with citations you can inspect.</p></section>`;
    const body = `${heading}
      <div class="answer-list" id="answer-list"></div>
      ${alertHTML(state.error)}
      <section class="ask-dock"><form class="question-box card" id="ask-form"><label class="sr-only" for="question">Ask a question</label><textarea class="textarea" id="question" name="question" maxlength="4000" required placeholder="Ask a question about your company documents…"></textarea><div class="question-actions"><span class="small-text muted">Answers are based on retrieved documents.</span><button class="button small" type="submit" ${state.loading ? "disabled" : ""}>${state.loading ? "Searching…" : "Ask"} <span aria-hidden="true">→</span></button></div></form></section>
      ${state.messages.length ? "" : `<div class="suggestions" aria-label="Example questions">${[
        "How many annual paid leave days do employees receive?",
        "What should I do during a critical IT incident?",
        "What approvals are needed for equipment purchases?",
      ].map((question) => `<button class="suggestion" type="button" data-question="${escapeHTML(question)}">${escapeHTML(question)}</button>`).join("")}</div>`}`;
    app.innerHTML = shell("ask", body, true);
    const list = document.getElementById("answer-list");
    state.messages.forEach((message, index) => {
      const turn = document.createElement("section");
      turn.className = "conversation-turn";
      turn.setAttribute("aria-label", `Question and answer ${index + 1}`);
      const question = document.createElement("div");
      question.className = "message-question";
      question.textContent = message.question;
      turn.append(question, renderAnswer(message, index));
      list.append(turn);
    });
  }

  function renderReports() {
    const body = `<div class="page-head"><div><h1>Grounded reports</h1><p class="subheading">Create a structured report from documents you are authorized to access. Reports are not stored.</p></div></div>
      ${alertHTML(state.error)}
      <section class="card report-form-card"><form id="report-form"><div class="field"><label for="report-title">Report title <span class="muted">(optional)</span></label><input class="input" id="report-title" name="title" maxlength="180" /></div><div class="field"><label for="report-question">Purpose or question</label><textarea class="textarea" id="report-question" name="question" maxlength="4000" required placeholder="Describe the decision or subject this report should cover."></textarea></div><button class="button" type="submit" ${state.loading ? "disabled" : ""}>${state.loading ? "Building report…" : "Generate grounded report"}</button></form></section>
      ${state.report ? `<section class="card report-result"><div class="report-actions"><button class="button secondary small" type="button" data-action="download-report">Download Markdown</button><button class="button secondary small" type="button" data-action="print-report">Print / Save as PDF</button></div><pre class="report-markdown"></pre><h2>Evidence sources</h2><div class="report-source-list">${(state.report.sources || []).map((source) => `<section class="card report-source" id="report-source-${escapeHTML(source.source_number)}"><strong>[Source ${escapeHTML(source.source_number)}] ${escapeHTML(source.filename || source.document_title || "Source document")}</strong><p class="small-text muted">Chunk ${escapeHTML(Number(source.chunk_index) + 1)}${source.page_numbers?.length ? ` · Page ${escapeHTML(source.page_numbers.join(", "))}` : ""}</p><p>${escapeHTML(source.content || "")}</p>${source.document_id ? `<a class="source-document-link" href="#/documents/${encodeURIComponent(source.document_id)}">View source document →</a>` : ""}</section>`).join("")}</div><p class="small-text muted">Citation checks confirm that labels map to retrieved sources. Model support checks are estimates, not proof of correctness.</p></section>` : ""}`;
    app.innerHTML = shell("reports", body, true);
    if (state.report) app.querySelector(".report-markdown")?.append(answerNodes(state.report.markdown));
  }

  function documentRows() {
    const term = state.documentSearch.trim().toLocaleLowerCase();
    const docs = state.documents.filter((doc) => !term || `${doc.title} ${doc.filename}`.toLocaleLowerCase().includes(term));
    if (!docs.length) return `<tr><td colspan="4" class="muted">${state.documents.length ? "No documents match this filter." : "No documents have been uploaded yet."}</td></tr>`;
    return docs.map((doc) => `<tr>
      <td><a class="doc-title" href="#/documents/${encodeURIComponent(doc.id)}">${escapeHTML(doc.title || doc.filename)}</a><span class="file-meta">${escapeHTML(doc.filename)}</span></td>
      <td>${escapeHTML(fileType(doc.filename, doc.content_type))}</td>
      <td><span class="badge">Ready</span></td>
      <td>v${escapeHTML(doc.current_version)}<span class="file-meta">${escapeHTML(formatDate(doc.updated_at))}</span></td>
    </tr>`).join("");
  }

  function fileType(filename, contentType) {
    const extension = String(filename || "").match(/\.([^.]+)$/)?.[1];
    if (extension) return extension.toUpperCase();
    return String(contentType || "Document").split("/").pop().toUpperCase();
  }

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
  }

  function renderDocuments() {
    const hasNext = state.documents.length === state.documentsLimit;
    const body = `<div class="page-head"><div><h1>Knowledge base</h1><p class="subheading">Manage the documents you can use to answer questions.</p></div></div>
      ${alertHTML(state.error)}${alertHTML(state.success, true)}
      <section class="card upload-panel"><form id="upload-form"><div class="upload-drop" id="upload-drop"><strong>Upload company documents</strong><span class="small-text muted">PDF, DOCX, TXT, or Markdown · up to 20 MB per file</span><input id="upload-files" name="files" type="file" accept=".pdf,.docx,.txt,.md" multiple aria-label="Choose documents to upload" /><span class="small-text muted">Original files are stored by this application for download and version history.</span></div><div class="question-actions"><span class="small-text muted">Each file is uploaded and indexed individually.</span><button class="button small" type="submit" ${state.loading || !state.selectedFiles.length ? "disabled" : ""}>${state.loading ? "Uploading…" : `Upload ${state.selectedFiles.length || "files"}`}</button></div></form>${state.uploadResults.length ? `<div class="upload-progress" aria-live="polite">${state.uploadResults.map((item) => `<div class="upload-row"><span>${escapeHTML(item.filename)}</span><span>${escapeHTML(item.result)}</span></div>`).join("")}</div>` : ""}</section>
      <section class="card"><div class="toolbar"><div><h2>Documents</h2><span class="small-text muted">Your accessible knowledge sources</span></div><input class="input search" id="document-search" type="search" value="${escapeHTML(state.documentSearch)}" placeholder="Filter by title or filename" aria-label="Filter documents" /></div>
        <div class="table-wrap"><table><thead><tr><th>Document</th><th>Type</th><th>Status</th><th>Version / updated</th></tr></thead><tbody id="document-rows">${state.loading && !state.documents.length ? `<tr><td colspan="4" class="busy">Loading documents…</td></tr>` : documentRows()}</tbody></table></div>
        <div class="pagination"><span class="small-text muted">${state.documents.length ? `Showing ${state.documentsOffset + 1}–${state.documentsOffset + state.documents.length}` : ""}</span><div><button class="button secondary small" data-action="docs-prev" type="button" ${state.documentsOffset === 0 ? "disabled" : ""}>Previous</button> <button class="button secondary small" data-action="docs-next" type="button" ${!hasNext ? "disabled" : ""}>Next</button></div></div>
      </section>`;
    app.innerHTML = shell("documents", body);
  }

  function renderDetail() {
    const doc = state.activeDocument;
    if (!doc) {
      app.innerHTML = shell("detail", `<p class="busy">Loading document…</p>`);
      return;
    }
    const selected = state.selectedVersion || doc.current_version;
    const selectedVersionInfo = state.versions.find(
      (version) => Number(version.version_number) === Number(selected),
    );
    const body = `<div class="page-head"><div><a class="link-button" href="#/documents">← Knowledge base</a><h1>${escapeHTML(doc.title || doc.filename)}</h1><p class="subheading">${escapeHTML(doc.filename)} · Version ${escapeHTML(selected)}</p></div></div>
      ${alertHTML(state.error)}${alertHTML(state.success, true)}
      ${(doc.extraction_warnings || []).length ? `<section class="alert warning" role="status"><strong>Extraction notes</strong><ul>${doc.extraction_warnings.map((warning) => `<li>${escapeHTML(warning)}</li>`).join("")}</ul></section>` : ""}
      <div class="detail-grid"><section class="card detail-main"><div class="page-head"><div><h2>Extracted content</h2><p class="small-text muted">Text segments indexed for search. This view does not display the original file layout.</p></div></div>
        ${state.loading && !state.chunks.length ? `<p class="busy">Loading document content…</p>` : state.chunks.length ? state.chunks.map((chunk) => `<article class="chunk"><div class="chunk-meta">Chunk ${escapeHTML(chunk.chunk_index + 1)} · ${escapeHTML(chunk.token_count ?? "")} tokens</div><p class="chunk-text">${escapeHTML(chunk.content)}</p></article>`).join("") : `<p class="muted small-text">No extracted text is available for this version.</p>`}
        ${state.chunks.length === state.chunksLimit ? `<div style="padding-top:12px"><button class="button secondary small" data-action="more-chunks" type="button">Load more content</button></div>` : ""}
      </section><aside class="card detail-side"><h2>Document details</h2><p class="small-text muted">${escapeHTML(doc.filename)}</p><p class="small-text">Current version: <strong>${escapeHTML(doc.current_version)}</strong></p><p class="small-text">Content chunks: <strong>${escapeHTML(doc.chunk_count)}</strong></p><p class="small-text">Updated: ${escapeHTML(formatDate(doc.updated_at))}</p>
        <h3 style="margin-top:20px">Version history</h3><div class="version-list">${state.versions.map((version) => `<button type="button" class="version-option ${Number(version.version_number) === Number(selected) ? "active" : ""}" data-action="select-version" data-version="${escapeHTML(version.version_number)}"><span>Version ${escapeHTML(version.version_number)}<br><span class="muted">${escapeHTML(formatDate(version.created_at))}</span></span><span>${version.original_available ? "Original available" : "Text only"}</span></button>`).join("")}</div>
        <div class="side-actions"><button class="button secondary" type="button" data-action="download" data-version="${escapeHTML(selected)}" ${selectedVersionInfo && !selectedVersionInfo.original_available ? "disabled" : ""}>${selectedVersionInfo && !selectedVersionInfo.original_available ? "Original unavailable" : "Download original"}</button><button class="button danger" type="button" data-action="delete-open">Delete document</button></div>
      </aside></div>${state.deleteOpen ? deleteModal(doc) : ""}`;
    app.innerHTML = shell("detail", body);
  }

  function renderAudit() {
    const rows = state.auditEvents.length ? state.auditEvents.map((event) => `<tr>
      <td>${escapeHTML(formatDateTime(event.created_at))}</td>
      <td><strong>${escapeHTML(event.action)}</strong><span class="file-meta">${escapeHTML(event.resource_type)}</span></td>
      <td>${escapeHTML(event.actor_id || "System")}</td>
      <td><code>${escapeHTML(event.resource_id || "—")}</code></td>
      <td><code>${escapeHTML(JSON.stringify(event.details || {}))}</code></td>
    </tr>`).join("") : `<tr><td colspan="5" class="muted">No audit events are available.</td></tr>`;
    app.innerHTML = shell("audit", `<div class="page-head"><div><h1>Audit log</h1><p class="subheading">Administrative activity metadata. Question text, answers, and document contents are not included.</p></div></div>${alertHTML(state.error)}<section class="card"><div class="table-wrap"><table class="audit-table"><thead><tr><th>Time</th><th>Action</th><th>Actor ID</th><th>Resource ID</th><th>Metadata</th></tr></thead><tbody>${rows}</tbody></table></div><div class="pagination"><span class="small-text muted">${state.auditEvents.length ? `Showing ${state.auditOffset + 1}–${state.auditOffset + state.auditEvents.length}` : ""}</span><div><button class="button secondary small" data-action="audit-prev" type="button" ${state.auditOffset === 0 ? "disabled" : ""}>Previous</button> <button class="button secondary small" data-action="audit-next" type="button" ${state.auditEvents.length < state.auditLimit ? "disabled" : ""}>Next</button></div></div></section>`);
  }

  function formatDateTime(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
  }

  function deleteModal(doc) {
    return `<div class="modal-backdrop" role="presentation"><section class="modal card" role="dialog" aria-modal="true" aria-labelledby="delete-title"><h2 id="delete-title">Delete this document?</h2><p class="small-text">This will permanently delete <strong>${escapeHTML(doc.title || doc.filename)}</strong>, its indexed content, and stored versions. This action cannot be undone.</p><div class="modal-actions"><button class="button secondary" type="button" data-action="delete-cancel">Cancel</button><button class="button danger" type="button" data-action="delete-confirm" ${state.loading ? "disabled" : ""}>${state.loading ? "Deleting…" : "Delete document"}</button></div></section></div>`;
  }

  async function loadDocuments() {
    state.loading = true;
    renderDocuments();
    try {
      const data = await api(`/documents?limit=${state.documentsLimit}&offset=${state.documentsOffset}`);
      state.documents = data.items || [];
      state.error = "";
    } catch (error) { state.error = safeError(error); }
    finally { state.loading = false; renderDocuments(); }
  }

  async function loadDocument(id) {
    state.loading = true;
    state.error = "";
    renderDetail();
    try {
      const [doc, versions] = await Promise.all([
        api(`/documents/${encodeURIComponent(id)}`),
        api(`/documents/${encodeURIComponent(id)}/versions`),
      ]);
      state.activeDocument = doc;
      state.versions = versions.items || [];
      state.selectedVersion = Number(doc.current_version);
      await loadChunks(id, false);
    } catch (error) { state.error = safeError(error); }
    finally { state.loading = false; renderDetail(); }
  }

  async function ensureProfile() {
    const token = state.session?.token;
    if (!token || state.profileToken === token) return;
    try {
      state.profile = await api("/auth/me");
      state.profileToken = token;
    } catch (error) {
      if (error instanceof ApiError && error.status !== 401) {
        state.profile = null;
        state.profileToken = token;
      }
    }
  }

  async function loadAudit() {
    try {
      const result = await api(`/audit?limit=${state.auditLimit}&offset=${state.auditOffset}`);
      state.auditEvents = result.items || [];
      state.error = "";
    } catch (error) {
      state.error = error instanceof ApiError && error.status === 403
        ? "Administrator access is required to view audit events." : safeError(error);
    }
    renderAudit();
  }

  async function loadChunks(id, append) {
    if (!append) { state.chunks = []; state.chunksOffset = 0; }
    const version = state.selectedVersion || state.activeDocument?.current_version;
    const data = await api(`/documents/${encodeURIComponent(id)}/content?version_number=${encodeURIComponent(version)}&limit=${state.chunksLimit}&offset=${state.chunksOffset}`);
    state.chunks = append ? state.chunks.concat(data.items || []) : (data.items || []);
  }

  async function renderRoute() {
    state.error = "";
    const route = currentRoute();
    if (!state.session && !["/login", "/register"].includes(route)) {
      navigate("/login");
      return;
    }
    if (state.session && ["/", "/login", "/register"].includes(route)) {
      navigate("/ask");
      return;
    }
    if (state.session) {
      await ensureProfile();
      if (!state.session) return;
    }
    if (route === "/login") return authPage(false);
    if (route === "/register") return authPage(true);
    if (route === "/ask") return renderAsk();
    if (route === "/reports") return renderReports();
    if (route === "/documents") {
      state.documentsOffset = Math.max(0, state.documentsOffset);
      return loadDocuments();
    }
    if (route === "/audit") {
      if (state.profile?.role !== "admin") {
        navigate("/ask");
        return;
      }
      return loadAudit();
    }
    const detail = route.match(/^\/documents\/([0-9a-f-]{36})$/i);
    if (detail) {
      state.activeDocument = null;
      state.versions = [];
      state.chunks = [];
      state.selectedVersion = null;
      return loadDocument(detail[1]);
    }
    navigate(state.session ? "/ask" : "/login");
  }

  async function submitLogin(form) {
    const values = new FormData(form);
    const body = new URLSearchParams({ username: values.get("email"), password: values.get("password") });
    state.loading = true;
    state.error = "";
    authPage(false);
    try {
      const result = await api("/auth/token", {
        method: "POST", auth: false,
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      saveSession({ token: result.access_token, email: String(values.get("email")).trim() });
      state.messages = [];
      navigate("/ask");
    } catch (error) {
      state.error = error instanceof ApiError && error.status === 401
        ? "Invalid email or password." : safeError(error);
      authPage(false);
    } finally {
      state.loading = false;
      if (currentRoute() === "/login") authPage(false);
      else if (currentRoute() === "/register") authPage(true);
    }
  }

  async function submitRegister(form) {
    const values = new FormData(form);
    const email = String(values.get("email") || "").trim();
    const password = String(values.get("password") || "");
    if (password !== values.get("confirmPassword")) {
      state.error = "The passwords do not match.";
      return authPage(true);
    }
    if (password.length < 12) {
      state.error = "Use a password with at least 12 characters.";
      return authPage(true);
    }
    state.loading = true;
    state.error = "";
    authPage(true);
    try {
      await api("/auth/register", {
        method: "POST", auth: false,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      state.success = "Account created. Sign in with your email and password.";
      navigate("/login");
    } catch (error) {
      state.error = error instanceof ApiError && error.status === 409
        ? "An account with this email already exists." : safeError(error);
      authPage(true);
    } finally {
      state.loading = false;
      if (currentRoute() === "/login") authPage(false);
      else if (currentRoute() === "/register") authPage(true);
    }
  }

  async function ask(question) {
    const cleaned = String(question || "").trim();
    if (!cleaned || state.loading) return;
    state.messages.push({ question: cleaned, answer: "", sources: [] });
    const messageIndex = state.messages.length - 1;
    state.loading = true;
    state.error = "";
    renderAsk();
    try {
      const body = new URLSearchParams({ question: cleaned });
      const result = await api("/query/", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      state.messages[messageIndex] = {
        question: result.question || cleaned,
        answer: result.answer || "The platform returned an empty answer.",
        sources: Array.isArray(result.sources) ? result.sources : [],
        verification: result.verification || null,
      };
    } catch (error) {
      state.messages.pop();
      state.error = safeError(error);
    } finally {
      state.loading = false;
      renderAsk();
      document.getElementById("question")?.focus();
      window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    }
  }

  async function generateReport(form) {
    const values = new FormData(form);
    const question = String(values.get("question") || "").trim();
    if (!question || state.loading) return;
    state.loading = true;
    state.error = "";
    state.report = null;
    renderReports();
    try {
      state.report = await api("/reports/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, title: String(values.get("title") || "").trim() || null }),
      });
    } catch (error) {
      state.error = safeError(error);
    } finally {
      state.loading = false;
      renderReports();
    }
  }

  async function submitFeedback(index, form) {
    const message = state.messages[index];
    if (!message || !message.feedbackRating || message.feedbackLoading) return;
    message.feedbackLoading = true;
    message.feedbackError = "";
    renderAsk();
    try {
      await api("/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: message.question,
          answer: message.answer,
          rating: message.feedbackRating,
          comment: new FormData(form).get("comment") || null,
        }),
      });
      message.feedbackSubmitted = true;
    } catch (error) {
      message.feedbackError = safeError(error);
    } finally {
      message.feedbackLoading = false;
      renderAsk();
    }
  }

  async function uploadFiles() {
    if (!state.selectedFiles.length || state.loading) return;
    state.loading = true;
    state.error = "";
    state.success = "";
    state.uploadResults = [];
    renderDocuments();
    const allowed = new Set([".pdf", ".docx", ".txt", ".md"]);
    for (const file of state.selectedFiles) {
      const extension = `.${file.name.split(".").pop().toLowerCase()}`;
      if (!allowed.has(extension)) {
        state.uploadResults.push({ filename: file.name, result: "Unsupported file type" });
        continue;
      }
      if (file.size === 0) {
        state.uploadResults.push({ filename: file.name, result: "Empty files cannot be uploaded" });
        continue;
      }
      if (file.size > 20 * 1024 * 1024) {
        state.uploadResults.push({ filename: file.name, result: "File exceeds 20 MB" });
        continue;
      }
      const form = new FormData();
      form.append("file", file, file.name);
      try {
        const result = await api("/documents/upload", { method: "POST", body: form });
        state.uploadResults.push({
          filename: file.name,
          result: result.duplicate ? `Already indexed · version ${result.version_number}` : `Indexed · version ${result.version_number}`,
        });
      } catch (error) {
        state.uploadResults.push({ filename: file.name, result: safeError(error) });
      }
      renderDocuments();
    }
    state.selectedFiles = [];
    state.loading = false;
    state.success = state.uploadResults.some((item) => item.result.startsWith("Indexed") || item.result.startsWith("Already indexed"))
      ? "Upload processing finished. The document list has been refreshed." : "No files were uploaded.";
    await loadDocuments();
    state.loading = false;
    renderDocuments();
  }

  async function downloadOriginal(version) {
    if (!state.activeDocument) return;
    const id = encodeURIComponent(state.activeDocument.id);
    const path = Number(version) === Number(state.activeDocument.current_version)
      ? `/documents/${id}/file`
      : `/documents/${id}/versions/${encodeURIComponent(version)}/file`;
    try {
      const blob = await api(path);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = state.activeDocument.filename || "document";
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      state.error = safeError(error);
      renderDetail();
    }
  }

  async function deleteDocument() {
    if (!state.activeDocument) return;
    state.loading = true;
    renderDetail();
    try {
      await api(`/documents/${encodeURIComponent(state.activeDocument.id)}`, { method: "DELETE" });
      state.activeDocument = null;
      state.deleteOpen = false;
      state.success = "Document deleted.";
      state.documentsOffset = 0;
      navigate("/documents");
    } catch (error) {
      state.error = safeError(error);
      state.deleteOpen = false;
      renderDetail();
    } finally { state.loading = false; }
  }

  app.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.target;
    if (form.id === "auth-form") {
      if (form.dataset.mode === "register") submitRegister(form);
      else submitLogin(form);
    } else if (form.id === "ask-form") {
      ask(new FormData(form).get("question"));
    } else if (form.id === "upload-form") {
      uploadFiles();
    } else if (form.id === "report-form") {
      generateReport(form);
    } else if (form.classList.contains("feedback-form")) {
      submitFeedback(Number(form.dataset.index), form);
    }
  });

  app.addEventListener("change", (event) => {
    if (event.target.id === "upload-files") {
      state.selectedFiles = Array.from(event.target.files || []);
      renderDocuments();
    }
  });

  app.addEventListener("input", (event) => {
    if (event.target.id === "document-search") {
      state.documentSearch = event.target.value;
      const rows = document.getElementById("document-rows");
      if (rows) rows.innerHTML = documentRows();
    }
  });

  app.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-action], [data-question], [data-citation]");
    if (!button) return;
    if (button.dataset.question) return ask(button.dataset.question);
    if (button.dataset.citation) {
      const target = button.closest(".answer-block")?.querySelector(
        `[data-source-number="${CSS.escape(button.dataset.citation)}"]`,
      ) || document.getElementById(`report-source-${button.dataset.citation}`);
      if (target) {
        const disclosure = target.closest(".evidence-disclosure");
        if (disclosure) disclosure.open = true;
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.add("highlight");
        window.setTimeout(() => target.classList.remove("highlight"), 1800);
      }
      return;
    }
    switch (button.dataset.action) {
      case "toggle-password": {
        const input = document.getElementById(button.dataset.target);
        if (!input) break;
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        const label = show ? button.dataset.hideLabel : button.dataset.showLabel;
        button.setAttribute("aria-label", label);
        button.setAttribute("title", label);
        button.innerHTML = show
          ? '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8"/><path d="M9.9 5.2A10.8 10.8 0 0 1 12 5c6.4 0 10 7 10 7a16 16 0 0 1-3.1 3.8M6.2 6.2C3.5 8.1 2 12 2 12s3.6 7 10 7a10 10 0 0 0 3-.5"/></svg>'
          : '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
        input.focus({ preventScroll: true });
        break;
      }
      case "signout": saveSession(null); state.messages = []; state.error = ""; navigate("/login"); break;
      case "docs-prev": state.documentsOffset = Math.max(0, state.documentsOffset - state.documentsLimit); await loadDocuments(); break;
      case "docs-next": state.documentsOffset += state.documentsLimit; await loadDocuments(); break;
      case "new-question": state.messages = []; state.error = ""; renderAsk(); break;
      case "download-report": {
        if (!state.report) break;
        const url = URL.createObjectURL(new Blob([state.report.markdown], { type: "text/markdown;charset=utf-8" }));
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `${(state.report.title || "grounded-report").replace(/[^a-z0-9-_]+/gi, "-").replace(/^-|-$/g, "") || "grounded-report"}.md`;
        anchor.click();
        URL.revokeObjectURL(url);
        break;
      }
      case "print-report": window.print(); break;
      case "feedback-select": {
        const message = state.messages[Number(button.dataset.index)];
        if (message && !message.feedbackSubmitted) {
          message.feedbackRating = Number(button.dataset.rating);
          renderAsk();
          document.getElementById(`feedback-comment-${button.dataset.index}`)?.focus();
        }
        break;
      }
      case "audit-prev": state.auditOffset = Math.max(0, state.auditOffset - state.auditLimit); await loadAudit(); break;
      case "audit-next": state.auditOffset += state.auditLimit; await loadAudit(); break;
      case "delete-open":
        state.deleteOpen = true;
        renderDetail();
        requestAnimationFrame(() => app.querySelector('[role="dialog"] button')?.focus());
        break;
      case "delete-cancel": state.deleteOpen = false; renderDetail(); break;
      case "delete-confirm": await deleteDocument(); break;
      case "download": await downloadOriginal(button.dataset.version); break;
      case "more-chunks":
        if (state.activeDocument) {
          state.chunksOffset += state.chunksLimit;
          state.loading = true;
          renderDetail();
          try { await loadChunks(state.activeDocument.id, true); }
          catch (error) { state.error = safeError(error); }
          finally { state.loading = false; renderDetail(); }
        }
        break;
      case "select-version":
        if (state.activeDocument) {
          state.selectedVersion = Number(button.dataset.version);
          state.chunksOffset = 0;
          state.loading = true;
          renderDetail();
          try { await loadChunks(state.activeDocument.id, false); }
          catch (error) { state.error = safeError(error); }
          finally { state.loading = false; renderDetail(); }
        }
        break;
    }
  });

  app.addEventListener("keydown", (event) => {
    if (!state.deleteOpen) return;
    const dialog = app.querySelector('[role="dialog"]');
    if (!dialog) return;
    if (event.key === "Escape") {
      state.deleteOpen = false;
      renderDetail();
      return;
    }
    if (event.key !== "Tab") return;
    const controls = [...dialog.querySelectorAll("button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled)")];
    if (!controls.length) return;
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  window.addEventListener("hashchange", renderRoute);
  renderRoute();
})();
