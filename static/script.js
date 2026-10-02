function token() {
  return localStorage.getItem("studyai_token");
}

function setToken(value) {
  localStorage.setItem("studyai_token", value);
}

function requireAuth() {
  if (!token()) {
    window.location.href = "/login";
    return false;
  }
  return true;
}

function authHeaders() {
  return { Authorization: "Bearer " + token() };
}

function setWorkspaceUsername(username) {
  document.querySelectorAll("[data-workspace-username]").forEach((element) => {
    element.textContent = username;
  });
}

async function loadWorkspaceUser() {
  if (!document.querySelector("[data-workspace-username]") || document.getElementById("materialList")) return;
  if (!requireAuth()) return;
  try {
    const response = await fetch("/api/me", { headers: authHeaders() });
    if (response.status === 401) {
      localStorage.removeItem("studyai_token");
      window.location.href = "/login";
      return;
    }
    if (!response.ok) throw new Error(await readError(response));
    const user = await response.json();
    setWorkspaceUsername(user.username);
  } catch (err) {
    showToast(err.message);
  }
}

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function showAlert(message, type) {
  const box = document.getElementById("alertBox");
  if (!box) {
    showToast(message, type);
    return;
  }
  const alert = document.createElement("div");
  alert.className = `alert alert-${type || "danger"}`;
  alert.setAttribute("role", "alert");
  alert.textContent = message;
  box.replaceChildren(alert);
}

function showToast(message, type) {
  let area = document.getElementById("toastArea");
  if (!area) {
    area = document.createElement("div");
    area.id = "toastArea";
    area.className = "toast-container position-fixed bottom-0 end-0 p-3";
    document.body.appendChild(area);
  }
  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${type === "success" ? "success" : "danger"} border-0 show`;
  el.setAttribute("role", "status");
  const row = document.createElement("div");
  row.className = "d-flex";
  const body = document.createElement("div");
  body.className = "toast-body";
  body.textContent = message;
  const close = document.createElement("button");
  close.className = "btn-close btn-close-white me-2 m-auto";
  close.type = "button";
  close.setAttribute("aria-label", "Close notification");
  close.addEventListener("click", () => el.remove());
  row.append(body, close);
  el.append(row);
  area.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function setLoading(form, loading) {
  const button = form.querySelector("button[type='submit']") || form;
  const text = button.querySelector(".btn-text");
  const spinner = button.querySelector(".spinner-border");
  button.disabled = loading;
  if (text) text.classList.toggle("d-none", loading);
  if (spinner) spinner.classList.toggle("d-none", !loading);
}

async function readError(response) {
  try {
    const data = await response.json();
    if (Array.isArray(data.detail)) {
      return data.detail.map((item) => item.msg).join(" ");
    }
    return data.detail || "Request failed.";
  } catch (err) {
    return "Request failed.";
  }
}

document.querySelectorAll("[data-toggle-password]").forEach((button) => {
  button.addEventListener("click", () => {
    const input = document.getElementById(button.getAttribute("data-toggle-password"));
    if (!input) return;
    input.type = input.type === "password" ? "text" : "password";
    const icon = button.querySelector("i");
    if (icon) {
      icon.classList.toggle("bi-eye");
      icon.classList.toggle("bi-eye-slash");
    }
  });
});

const loginForm = document.getElementById("loginForm");
if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setLoading(loginForm, true);
    const body = new URLSearchParams();
    body.set("username", loginForm.username.value);
    body.set("password", loginForm.password.value);
    try {
      const response = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      if (!response.ok) throw new Error(await readError(response));
      const data = await response.json();
      setToken(data.access_token);
      window.location.href = "/dashboard";
    } catch (err) {
      showAlert(err.message);
    } finally {
      setLoading(loginForm, false);
    }
  });
}

const registerForm = document.getElementById("registerForm");
if (registerForm) {
  registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (registerForm.password.value !== registerForm.confirm.value) {
      showAlert("Passwords do not match.");
      return;
    }
    if (registerForm.password.value.length < 6) {
      showAlert("Password must be at least 6 characters.");
      return;
    }
    setLoading(registerForm, true);
    try {
      const response = await fetch("/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: registerForm.username.value,
          email: registerForm.email.value,
          password: registerForm.password.value,
        }),
      });
      if (!response.ok) throw new Error(await readError(response));
      showAlert("Account created. You can login now.", "success");
      setTimeout(() => (window.location.href = "/login"), 800);
    } catch (err) {
      showAlert(err.message);
    } finally {
      setLoading(registerForm, false);
    }
  });
}

document.querySelectorAll("[data-logout], #logoutBtn").forEach((logoutBtn) => {
  logoutBtn.addEventListener("click", () => {
    localStorage.removeItem("studyai_token");
    window.location.href = "/login";
  });
});

let dashboardMaterials = [];
let activeMaterialFilter = "all";

function renderDashboardMaterials() {
  const list = document.getElementById("materialList");
  if (!list) return;
  const search = (document.getElementById("materialSearch")?.value || "").trim().toLowerCase();
  const sort = document.getElementById("materialSort")?.value || "newest";
  const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
  let materials = dashboardMaterials.filter((item) => {
    const matchesSearch = `${item.title} ${item.filename}`.toLowerCase().includes(search);
    const createdAt = item.created_at ? new Date(item.created_at).getTime() : 0;
    const matchesFilter = activeMaterialFilter === "all"
      || (activeMaterialFilter === "recent" && createdAt >= cutoff)
      || (activeMaterialFilter === "summarized" && item.has_summary)
      || (activeMaterialFilter === "quiz" && item.has_quiz);
    return matchesSearch && matchesFilter;
  });

  materials.sort((first, second) => {
    if (sort === "name") return first.title.localeCompare(second.title);
    const difference = new Date(first.created_at || 0) - new Date(second.created_at || 0);
    return sort === "oldest" ? difference : -difference;
  });

  const count = document.getElementById("materialCount");
  if (count) count.textContent = `${materials.length} of ${dashboardMaterials.length} materials`;
  if (!materials.length && !dashboardMaterials.length) {
    list.innerHTML = `
      <div class="col-12"><div class="card empty-state">
        <div class="empty-state-icon"><i class="bi bi-journal-plus" aria-hidden="true"></i></div>
        <h3 class="h5">No study materials yet</h3>
        <p class="text-secondary mb-3">Upload your first PDF and turn it into study material.</p>
        <a class="btn btn-primary rounded-pill" href="/upload"><i class="bi bi-plus-lg me-1" aria-hidden="true"></i>Upload PDF</a>
      </div></div>`;
    return;
  }
  if (!materials.length) {
    list.innerHTML = `<div class="col-12"><div class="card empty-state py-4"><h3 class="h6">No matching materials</h3><p class="text-secondary mb-0">Try another search or filter.</p></div></div>`;
    return;
  }

  list.innerHTML = materials.map((item) => `
    <div class="col-sm-6 col-xl-4 fade-in">
      <article class="card material-card">
        <div class="material-card-top">
          <span class="pdf-mark"><i class="bi bi-file-earmark-pdf" aria-hidden="true"></i></span>
          <div class="min-w-0"><h3>${escapeHTML(item.title)}</h3><div class="material-filename">${escapeHTML(item.filename)}</div></div>
        </div>
        <p class="material-date"><i class="bi bi-clock me-1" aria-hidden="true"></i>${item.created_at ? escapeHTML(new Date(item.created_at).toLocaleDateString()) : "Date unavailable"}</p>
        <div class="material-status">
          <span class="status-chip ${item.has_summary ? "ready" : ""}"><i class="bi ${item.has_summary ? "bi-check-circle" : "bi-circle"}" aria-hidden="true"></i>Summary ${item.has_summary ? "ready" : "not created"}</span>
          <span class="status-chip ${item.has_quiz ? "ready" : ""}"><i class="bi ${item.has_quiz ? "bi-check-circle" : "bi-circle"}" aria-hidden="true"></i>Quiz ${item.has_quiz ? "ready" : "not created"}</span>
        </div>
        <div class="material-actions">
          <a class="btn btn-sm btn-outline-primary" href="/materials/${item.id}">View</a>
          <a class="btn btn-sm btn-outline-secondary" href="/materials/${item.id}/summary">Summary</a>
          <a class="btn btn-sm btn-primary" href="/materials/${item.id}/quiz">Quiz</a>
          <button class="btn btn-sm btn-outline-danger ms-auto" type="button" data-delete-material="${item.id}" aria-label="Delete ${escapeHTML(item.title)}" title="Delete PDF"><i class="bi bi-trash me-1" aria-hidden="true"></i>Delete</button>
        </div>
      </article>
    </div>`).join("");
}

async function loadDashboard() {
  if (!document.getElementById("materialList") || !requireAuth()) return;
  try {
    const response = await fetch("/api/materials", { headers: authHeaders() });
    if (response.status === 401) {
      localStorage.removeItem("studyai_token");
      window.location.href = "/login";
      return;
    }
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    const welcome = document.getElementById("welcome");
    if (welcome) welcome.textContent = `Welcome, ${data.username}`;
    setWorkspaceUsername(data.username);
    document.getElementById("statPdfs").textContent = data.total_pdfs;
    document.getElementById("statSummaries").textContent = data.total_summaries;
    document.getElementById("statQuizzes").textContent = data.total_quizzes;
    dashboardMaterials = data.materials;
    renderDashboardMaterials();
  } catch (err) {
    showToast(err.message);
  }
}

const materialList = document.getElementById("materialList");
if (materialList) {
  document.getElementById("materialSearch")?.addEventListener("input", renderDashboardMaterials);
  document.getElementById("materialSort")?.addEventListener("change", renderDashboardMaterials);
  document.querySelectorAll("[data-material-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      activeMaterialFilter = button.dataset.materialFilter;
      document.querySelectorAll("[data-material-filter]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", String(active));
      });
      renderDashboardMaterials();
    });
  });
  materialList.addEventListener("click", async (event) => {
    const button = event.target.closest?.("[data-delete-material]");
    if (!button) return;
    if (!window.confirm("Delete this PDF and its saved quizzes? This cannot be undone.")) return;

    button.disabled = true;
    try {
      const response = await fetch(`/materials/${button.dataset.deleteMaterial}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!response.ok) throw new Error(await readError(response));
      await loadDashboard();
      showToast("PDF deleted.", "success");
    } catch (err) {
      showToast(err.message);
      button.disabled = false;
    }
  });
}

const uploadForm = document.getElementById("uploadForm");
if (uploadForm) {
  if (!requireAuth()) {
    /* redirect */
  } else {
    const fileInput = document.getElementById("pdfFile");
    const dropBox = document.querySelector(".drop-box");
    const fileInfo = document.getElementById("fileInfo");
    const progress = document.getElementById("uploadProgress");
    const uploadLimit = 10 * 1024 * 1024;

    function showFile(file) {
      if (!file) return;
      const validationMessage = validateUploadFile(file);
      fileInfo.textContent = validationMessage || `${file.name} · ${(file.size / 1024).toFixed(1)} KB`;
      fileInfo.classList.toggle("text-danger", Boolean(validationMessage));
    }

    function validateUploadFile(file) {
      if (!file.name.toLowerCase().endsWith(".pdf")) return "Only PDF files are supported.";
      if (file.type && !["application/pdf", "application/octet-stream"].includes(file.type)) {
        return "This file does not appear to be a PDF.";
      }
      if (file.size > uploadLimit) return "File size is too large. The maximum is 10 MB.";
      return "";
    }

    fileInput.addEventListener("change", () => showFile(fileInput.files[0]));
    ["dragenter", "dragover"].forEach((name) => {
      dropBox.addEventListener(name, (event) => {
        event.preventDefault();
        dropBox.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      dropBox.addEventListener(name, (event) => {
        event.preventDefault();
        dropBox.classList.remove("dragover");
      });
    });
    dropBox.addEventListener("drop", (event) => {
      const file = event.dataTransfer.files[0];
      if (file) {
        fileInput.files = event.dataTransfer.files;
        showFile(file);
      }
    });

    uploadForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const file = fileInput.files[0];
      if (!file) {
        showAlert("Please choose a PDF file.");
        return;
      }
      const validationMessage = validateUploadFile(file);
      if (validationMessage) {
        showAlert(validationMessage);
        return;
      }
      const formData = new FormData();
      formData.append("file", file);
      setLoading(uploadForm, true);
      progress.classList.remove("d-none");
      showAlert("Uploading and extracting text. Scanned PDFs may take a little longer.", "info");
      try {
        const response = await fetch("/materials/upload", {
          method: "POST",
          headers: authHeaders(),
          body: formData,
        });
        if (!response.ok) throw new Error(await readError(response));
        const data = await response.json();
        document.getElementById("uploadedFilename").textContent = data.filename || file.name;
        document.getElementById("uploadedSummaryLink").href = `/materials/${data.id}/summary`;
        document.getElementById("uploadedQuizLink").href = `/materials/${data.id}/quiz`;
        document.getElementById("uploadSuccess").classList.remove("d-none");
        uploadForm.classList.add("d-none");
        showAlert("PDF uploaded and text extracted.", "success");
        showToast("PDF uploaded successfully.", "success");
      } catch (err) {
        showAlert(err.message);
      } finally {
        setLoading(uploadForm, false);
        progress.classList.add("d-none");
      }
    });
  }
}

function renderSummary(title, summary) {
  document.getElementById("pdfTitle").textContent = title || "PDF Summary";
  const box = document.getElementById("summaryContent");
  if (!summary) {
    box.innerHTML = `<div class="summary-section"><h2 class="h5">No summary yet</h2><p class="text-secondary mb-0">Generate a summary from this PDF to see its key ideas here.</p></div>`;
    return;
  }
  const sections = [
    ["Overview", summary.overview, false],
    ["Key Points", summary.main_points, true],
    ["Important Concepts", summary.important_concepts, true],
    ["Important Terms", summary.important_terms, true],
    ["Conclusion", summary.conclusion, false],
  ];
  box.innerHTML = sections.map(([heading, content, isList]) => `
    <section class="summary-section"><h2>${heading}</h2>
      ${isList
        ? (content || []).length ? `<ul>${content.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul>` : `<p class="text-secondary mb-0">No items provided.</p>`
        : `<p>${escapeHTML(content || "")}</p>`}
    </section>`).join("");
}

function getSummaryText() {
  const summary = document.getElementById("summaryContent");
  return summary?.innerText.trim() || "";
}

async function loadSummaryPage() {
  const page = document.querySelector("[data-material-id]");
  if (!page || !document.getElementById("summaryContent") || !requireAuth()) return;
  const id = page.getAttribute("data-material-id");
  try {
    const response = await fetch("/api/materials/" + id, { headers: authHeaders() });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    renderSummary(data.title, data.summary);
    const generateButton = document.getElementById("generateSummary");
    if (data.summary) {
      generateButton.querySelector(".btn-text").innerHTML = '<i class="bi bi-arrow-clockwise me-1" aria-hidden="true"></i>Generate Again';
    } else {
      generateButton.querySelector(".btn-text").innerHTML = '<i class="bi bi-stars me-1" aria-hidden="true"></i>Generate Summary';
    }
    const uploadedDate = document.getElementById("uploadedDate");
    if (uploadedDate && data.created_at) uploadedDate.textContent = `Uploaded ${new Date(data.created_at).toLocaleDateString()}`;

    generateButton.addEventListener("click", async () => {
      if (data.summary && !window.confirm("Regenerate the summary? The current summary will be replaced.")) return;
      setLoading(generateButton, true);
      try {
        const result = await fetch("/materials/" + id + "/summary", {
          method: "POST",
          headers: authHeaders(),
        });
        if (!result.ok) throw new Error(await readError(result));
        const payload = await result.json();
        renderSummary(payload.title, payload.summary);
        data.summary = payload.summary;
        generateButton.querySelector(".btn-text").innerHTML = '<i class="bi bi-arrow-clockwise me-1" aria-hidden="true"></i>Generate Again';
        showToast("Summary ready.", "success");
      } catch (err) {
        showAlert(err.message);
      } finally {
        setLoading(generateButton, false);
      }
    });

    document.getElementById("copySummary").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(getSummaryText());
        showToast("Summary copied.", "success");
      } catch (err) {
        showToast("Clipboard access is unavailable in this browser.");
      }
    });
    document.getElementById("downloadSummary").addEventListener("click", () => {
      const file = new Blob([getSummaryText()], { type: "text/plain;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(file);
      link.download = `${(data.title || "study-summary").replace(/[\\/:*?"<>|]/g, "-")}-summary.txt`;
      link.click();
      URL.revokeObjectURL(link.href);
    });
    document.getElementById("printSummary").addEventListener("click", () => window.print());
  } catch (err) {
    showAlert(err.message);
  }
}

let quizState = { questions: [], index: 0, answers: [] };

function renderQuestion() {
  const box = document.getElementById("quizBox");
  const q = quizState.questions[quizState.index];
  const total = quizState.questions.length;
  const progress = Math.round(((quizState.index + 1) / total) * 100);
  box.innerHTML = `
    <div class="quiz-progress-wrap">
      <div class="quiz-progress-label"><span>Question ${quizState.index + 1} of ${total}</span><span>${progress}%</span></div>
      <div class="progress quiz-progress" role="progressbar" aria-label="Quiz progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}"><div class="progress-bar" style="width:${progress}%"></div></div>
    </div>
    <h2 class="quiz-question">${escapeHTML(q.question)}</h2>
    ${q.options.map((opt, i) => `
      <label class="option-label ${quizState.answers[quizState.index] === opt ? "selected" : ""}" for="choice-${quizState.index}-${i}">
        <input id="choice-${quizState.index}-${i}" type="radio" name="choice" value="${escapeHTML(opt)}" ${quizState.answers[quizState.index] === opt ? "checked" : ""}>
        <span><strong>${String.fromCharCode(65 + i)}.</strong> ${escapeHTML(opt)}</span>
      </label>`).join("")}
    <div class="d-flex justify-content-between mt-3">
      <button class="btn btn-outline-secondary rounded-pill" id="prevQ" ${quizState.index === 0 ? "disabled" : ""}><i class="bi bi-arrow-left me-1" aria-hidden="true"></i>Previous</button>
      ${quizState.index === total - 1
        ? `<button class="btn btn-primary rounded-pill" id="submitQ">Submit Quiz</button>`
        : `<button class="btn btn-primary rounded-pill" id="nextQ">Next<i class="bi bi-arrow-right ms-1" aria-hidden="true"></i></button>`}
    </div>`;
  box.querySelectorAll("input[name='choice']").forEach((input) => {
    input.addEventListener("change", () => {
      quizState.answers[quizState.index] = input.value;
      renderQuestion();
    });
  });
  const prev = document.getElementById("prevQ");
  const next = document.getElementById("nextQ");
  const submit = document.getElementById("submitQ");
  if (prev) prev.onclick = () => { quizState.index -= 1; renderQuestion(); };
  if (next) next.onclick = () => { quizState.index += 1; renderQuestion(); };
  if (submit) submit.onclick = showQuizResults;
}

function showQuizResults() {
  const questions = quizState.questions;
  const score = quizState.answers.filter((answer, index) => answer === questions[index].correct_answer).length;
  const percentage = Math.round((score / questions.length) * 100);
  const details = questions.map((q, i) => {
    const given = quizState.answers[i];
    const ok = given === q.correct_answer;
    return `<article class="card p-3 mb-3 ${ok ? "border-success" : "border-danger"}">
      <strong>${ok ? "✓ Correct" : "✕ Incorrect"}: ${escapeHTML(q.question)}</strong>
      <p class="mb-1 mt-2"><span class="text-secondary">Your answer:</span> ${escapeHTML(given || "Not answered")}</p>
      <p class="mb-1"><span class="text-secondary">Correct answer:</span> ${escapeHTML(q.correct_answer)}</p>
      <p class="mb-0"><span class="text-secondary">Explanation:</span> ${escapeHTML(q.explanation || "")}</p>
    </article>`;
  }).join("");
  document.getElementById("quizBox").innerHTML = `
    <div class="text-center py-2">
      <p class="section-kicker mb-1">Quiz complete</p>
      <h2 class="h3">Your results</h2>
      <div class="quiz-result-score mx-auto">${percentage}%</div>
      <p class="text-secondary">${score} / ${questions.length} correct</p>
    </div>
    <div class="d-flex flex-wrap justify-content-center gap-2 mb-3">
      <button class="btn btn-outline-primary rounded-pill" id="reviewAnswers" type="button">Review Answers</button>
      <button class="btn btn-primary rounded-pill" id="retryQuiz" type="button"><i class="bi bi-arrow-repeat me-1" aria-hidden="true"></i>Retry Quiz</button>
      <a class="btn btn-outline-secondary rounded-pill" href="/dashboard">Back to Dashboard</a>
    </div>
    <div id="answerReview" class="d-none">${details}</div>`;
  document.getElementById("reviewAnswers").onclick = (event) => {
    const review = document.getElementById("answerReview");
    review.classList.toggle("d-none");
    event.currentTarget.textContent = review.classList.contains("d-none") ? "Review Answers" : "Hide Review";
  };
  document.getElementById("retryQuiz").onclick = () => {
    quizState.index = 0;
    quizState.answers = [];
    renderQuestion();
  };
}

function startQuiz(questions) {
  quizState = { questions, index: 0, answers: [] };
  renderQuestion();
}

async function loadQuizPage() {
  const page = document.querySelector("[data-material-id]");
  if (!page || !document.getElementById("quizBox") || document.getElementById("summaryContent") || !requireAuth()) return;
  const id = page.getAttribute("data-material-id");
  try {
    const response = await fetch("/api/materials/" + id, { headers: authHeaders() });
    if (!response.ok) throw new Error(await readError(response));
    const data = await response.json();
    document.getElementById("pdfTitle").textContent = `${data.title} · Quiz`;
    if (data.quiz && data.quiz.length) {
      startQuiz(data.quiz);
    } else {
      document.getElementById("quizBox").innerHTML = `<div class="empty-state py-4"><p class="text-secondary mb-0">No quiz yet. Generate one from this PDF.</p></div>`;
    }

    document.getElementById("generateQuiz").addEventListener("click", async () => {
      const button = document.getElementById("generateQuiz");
      setLoading(button, true);
      try {
        const result = await fetch("/materials/" + id + "/quiz", {
          method: "POST",
          headers: authHeaders(),
        });
        if (!result.ok) throw new Error(await readError(result));
        const payload = await result.json();
        startQuiz(payload.questions);
        showToast("Quiz ready.", "success");
      } catch (err) {
        showAlert(err.message);
      } finally {
        setLoading(button, false);
      }
    });
  } catch (err) {
    showAlert(err.message);
  }
}

loadDashboard();
loadSummaryPage();
loadQuizPage();
loadWorkspaceUser();

function handleGoogleAuthResult() {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const accessToken = fragment.get("access_token");
  if (accessToken) {
    setToken(accessToken);
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    window.location.replace("/dashboard");
    return;
  }

  const url = new URL(window.location.href);
  const errorCode = url.searchParams.get("google_error");
  const messages = {
    cancelled: "Google sign-in was cancelled.",
    not_configured: "Google sign-in is not configured. Add the Google OAuth settings to your .env file.",
    unverified_email: "Google did not provide a verified email address for this account.",
    failed: "Google sign-in could not be completed. Please try again.",
  };
  if (errorCode && messages[errorCode]) {
    showAlert(messages[errorCode]);
    url.searchParams.delete("google_error");
    window.history.replaceState(null, "", url.pathname + url.search);
  }
}

handleGoogleAuthResult();
