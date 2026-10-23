const STORAGE_KEY = "resumeProfile";
const QA_STORAGE_KEY = "customAnswers";

const QUICK_ADD_QUESTIONS = [
  "Are you legally authorized to work in this country?",
  "Will you now or in the future require visa sponsorship?",
  "What are your salary expectations?",
  "What is your notice period / earliest start date?",
  "How did you hear about this position?",
  "Are you willing to relocate?",
  "Are you comfortable with on-site / hybrid / remote work?",
  "Do you have a disability?",
  "Veteran status",
];

const els = {
  tabs: document.querySelectorAll(".tab-btn"),
  panels: document.querySelectorAll(".tab-panel"),
  resumeFile: document.getElementById("resumeFile"),
  resumePaste: document.getElementById("resumePaste"),
  parseBtn: document.getElementById("parseBtn"),
  saveBtn: document.getElementById("saveBtn"),
  saveStatus: document.getElementById("saveStatus"),
  fillBtn: document.getElementById("fillBtn"),
  fillResult: document.getElementById("fillResult"),
  widgetToggle: document.getElementById("widgetToggle"),
  qaList: document.getElementById("qaList"),
  addQaBtn: document.getElementById("addQaBtn"),
  qaQuickAdd: document.getElementById("qaQuickAdd"),
  saveQaBtn: document.getElementById("saveQaBtn"),
  qaSaveStatus: document.getElementById("qaSaveStatus"),
  name: document.getElementById("fName"),
  firstName: document.getElementById("fFirstName"),
  lastName: document.getElementById("fLastName"),
  email: document.getElementById("fEmail"),
  phone: document.getElementById("fPhone"),
  location: document.getElementById("fLocation"),
  linkedin: document.getElementById("fLinkedin"),
  website: document.getElementById("fWebsite"),
  skills: document.getElementById("fSkills"),
  summary: document.getElementById("fSummary"),
};

let rawResumeText = "";

function switchTab(tabName) {
  els.tabs.forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === tabName));
  els.panels.forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${tabName}`));
}

els.tabs.forEach((btn) => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

function populateFieldsFromProfile(profile) {
  els.name.value = profile.name || "";
  els.firstName.value = profile.firstName || "";
  els.lastName.value = profile.lastName || "";
  els.email.value = profile.email || "";
  els.phone.value = profile.phone || "";
  els.location.value = profile.location || "";
  els.linkedin.value = profile.linkedin || "";
  els.website.value = profile.website || "";
  els.skills.value = (profile.skills || []).join(", ");
  els.summary.value = profile.summary || "";
  rawResumeText = profile.rawText || "";
}

function readProfileFromFields() {
  return {
    name: els.name.value.trim(),
    firstName: els.firstName.value.trim(),
    lastName: els.lastName.value.trim(),
    email: els.email.value.trim(),
    phone: els.phone.value.trim(),
    location: els.location.value.trim(),
    linkedin: els.linkedin.value.trim(),
    website: els.website.value.trim(),
    skills: els.skills.value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    summary: els.summary.value.trim(),
    rawText: rawResumeText,
  };
}

function loadSavedProfile() {
  chrome.storage.local.get([STORAGE_KEY], (result) => {
    if (result[STORAGE_KEY]) {
      populateFieldsFromProfile(result[STORAGE_KEY]);
    }
  });
}

els.resumeFile.addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    const text = String(reader.result || "");
    rawResumeText = text;
    els.resumePaste.value = text;
    const profile = ResumeParser.parseResume(text);
    populateFieldsFromProfile(profile);
  };
  reader.readAsText(file);
});

els.parseBtn.addEventListener("click", () => {
  const text = els.resumePaste.value;
  if (!text.trim()) return;
  rawResumeText = text;
  const profile = ResumeParser.parseResume(text);
  populateFieldsFromProfile(profile);
});

els.saveBtn.addEventListener("click", () => {
  const profile = readProfileFromFields();
  chrome.storage.local.set({ [STORAGE_KEY]: profile }, () => {
    els.saveStatus.textContent = "Saved. Go to \"Fill & Score\" on any job page.";
    setTimeout(() => (els.saveStatus.textContent = ""), 3000);
  });
});

chrome.runtime.onMessage.addListener((message) => {
  if (message && message.type === "RESUME_FIT_RESULT") {
    renderFillResult(message.payload);
  }
});

els.fillBtn.addEventListener("click", async () => {
  els.fillResult.innerHTML = "<p class=\"hint\">Analyzing page...</p>";
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) {
    els.fillResult.innerHTML = "<p class=\"hint\">No active tab found.</p>";
    return;
  }

  try {
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["lib/matcher.js", "lib/tailor.js", "lib/autofillEngine.js", "content.js"],
    });
    // Result arrives asynchronously via the RESUME_FIT_RESULT message above.
  } catch (err) {
    els.fillResult.innerHTML = `<p class="hint">Couldn't run on this page (${err.message || "restricted page"}).</p>`;
  }
});

function renderFillResult(outcome) {
  if (!outcome) {
    els.fillResult.innerHTML = "<p class=\"hint\">No result returned. Make sure you saved a resume profile first.</p>";
    return;
  }
  if (outcome.error) {
    els.fillResult.innerHTML = `<p class="hint">${outcome.error}</p>`;
    return;
  }

  const { filledCount, draftedCount, flaggedCount, match, tailor } = outcome;
  let html = `<p>✅ Filled <strong>${filledCount}</strong> field(s) with your real info / saved answers.</p>`;
  if (draftedCount) {
    html += `<p>📝 Drafted <strong>${draftedCount}</strong> open-ended answer(s) from your resume — <em>review &amp; personalize before submitting</em> (highlighted in blue).</p>`;
  }
  html += `<p>⚠️ Flagged <strong>${flaggedCount}</strong> field(s) for you to complete manually (highlighted in yellow).</p>`;

  if (match) {
    html += `<p>Job fit score: <span class="score">${match.score}%</span></p>`;
  }

  if (tailor) {
    html += `<hr /><p><strong>Tweak your resume for this role</strong></p>`;
    html += `<p class="hint">Your own skills/bullets, re-ordered for this posting. Nothing here is invented — it's all already on your resume.</p>`;

    if (tailor.leadSkills.length) {
      html += `<p class="hint">Lead with these skills:</p><div class="chip-list">${tailor.leadSkills
        .slice(0, 10)
        .map((s) => `<span class="chip matched">${escapeHtml(s)}</span>`)
        .join("")}</div>`;
    }

    if (tailor.leadBullets.length) {
      html += `<p class="hint">Lead with these bullets:</p><ul class="bullet-list">${tailor.leadBullets
        .map((b) => `<li>${escapeHtml(b)}</li>`)
        .join("")}</ul>`;
    }

    if (tailor.gaps.length) {
      html += `<p class="hint">In the posting, not on your resume — add only if genuinely true of you:</p><div class="chip-list">${tailor.gaps
        .map((g) => `<span class="chip missing">${escapeHtml(g)}</span>`)
        .join("")}</div>`;
    }
  }

  els.fillResult.innerHTML = html;
}

// --- Q&A (user-provided answers reused verbatim, never invented) --------

let qaItems = [];

function renderQaList() {
  els.qaList.innerHTML = "";
  qaItems.forEach((qa, idx) => {
    const row = document.createElement("div");
    row.className = "qa-row";
    row.innerHTML = `
      <div class="qa-row-header">
        <label>Question</label>
        <button class="qa-remove-btn" data-idx="${idx}">Remove</button>
      </div>
      <input type="text" class="qa-question" data-idx="${idx}" placeholder="e.g. Are you authorized to work in the US?" value="${escapeHtml(qa.question)}" />
      <label>Your answer</label>
      <textarea class="qa-answer" data-idx="${idx}" rows="2" placeholder="Your exact answer — this is reused as-is, never changed">${escapeHtml(qa.answer)}</textarea>
    `;
    els.qaList.appendChild(row);
  });

  els.qaList.querySelectorAll(".qa-question").forEach((input) => {
    input.addEventListener("input", (e) => {
      qaItems[Number(e.target.dataset.idx)].question = e.target.value;
    });
  });
  els.qaList.querySelectorAll(".qa-answer").forEach((textarea) => {
    textarea.addEventListener("input", (e) => {
      qaItems[Number(e.target.dataset.idx)].answer = e.target.value;
    });
  });
  els.qaList.querySelectorAll(".qa-remove-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      qaItems.splice(Number(e.target.dataset.idx), 1);
      renderQaList();
    });
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function addQaRow(question) {
  qaItems.push({ question: question || "", answer: "" });
  renderQaList();
  const textareas = els.qaList.querySelectorAll(".qa-answer");
  const last = textareas[textareas.length - 1];
  if (last) last.focus();
}

function renderQuickAddChips() {
  els.qaQuickAdd.innerHTML = "";
  QUICK_ADD_QUESTIONS.forEach((q) => {
    const chip = document.createElement("button");
    chip.className = "chip quick-add";
    chip.textContent = q;
    chip.addEventListener("click", () => addQaRow(q));
    els.qaQuickAdd.appendChild(chip);
  });
}

function loadQaItems() {
  chrome.storage.local.get([QA_STORAGE_KEY], (result) => {
    qaItems = result[QA_STORAGE_KEY] || [];
    renderQaList();
  });
}

els.addQaBtn.addEventListener("click", () => addQaRow());

els.saveQaBtn.addEventListener("click", () => {
  const cleaned = qaItems.filter((qa) => qa.question.trim() && qa.answer.trim());
  chrome.storage.local.set({ [QA_STORAGE_KEY]: cleaned }, () => {
    qaItems = cleaned;
    renderQaList();
    els.qaSaveStatus.textContent = "Saved.";
    setTimeout(() => (els.qaSaveStatus.textContent = ""), 3000);
  });
});

// --- Floating widget toggle ------------------------------------------

chrome.storage.local.get(["widgetEnabled"], (result) => {
  els.widgetToggle.checked = result.widgetEnabled !== false;
});

els.widgetToggle.addEventListener("change", () => {
  chrome.storage.local.set({ widgetEnabled: els.widgetToggle.checked });
});

renderQuickAddChips();
loadQaItems();
loadSavedProfile();
