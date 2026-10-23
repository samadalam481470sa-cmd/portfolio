/**
 * Injected on-demand from the popup's "Analyze & Fill This Page" button (or
 * the right-click context menu item). Delegates the actual field-matching
 * work to lib/autofillEngine.js (shared with widget.js) and shows a summary
 * panel + job-fit score. Never clicks Submit/Next/Apply, never simulates
 * mouse movement.
 */
(async function resumeFitFill() {
  const existingPanel = document.getElementById("resume-fit-panel");
  if (existingPanel) existingPanel.remove();

  function sendResult(payload) {
    chrome.runtime.sendMessage({ type: "RESUME_FIT_RESULT", payload });
  }

  const stored = await chrome.storage.local.get(["resumeProfile", "customAnswers"]);
  const profile = stored.resumeProfile;
  const qaItems = (stored.customAnswers || []).filter((qa) => qa && qa.question && qa.answer);

  if (!profile || (!profile.email && !profile.name)) {
    sendResult({ error: "No resume profile saved yet. Go to the Resume tab in the extension popup first." });
    return;
  }

  const outcome = window.ResumeFitEngine.runFullAutofill(profile, qaItems);

  const panel = document.createElement("div");
  panel.id = "resume-fit-panel";
  panel.style.cssText =
    "position:fixed;top:16px;right:16px;z-index:2147483647;background:#1a1a2e;color:#fff;" +
    "font-family:-apple-system,sans-serif;font-size:12px;padding:12px 14px;border-radius:10px;" +
    "box-shadow:0 8px 24px rgba(0,0,0,0.3);max-width:260px;line-height:1.5;";
  panel.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
      <strong>Resume-Fit Assistant</strong>
      <span id="resume-fit-close" style="cursor:pointer;opacity:0.7;">&times;</span>
    </div>
    <div>Filled: <strong>${outcome.filledCount}</strong></div>
    <div>Drafted (review needed): <strong>${outcome.draftedCount}</strong></div>
    <div>Needs your review: <strong>${outcome.flaggedCount}</strong></div>
    ${outcome.match ? `<div style="margin-top:6px;">Job fit score: <strong>${outcome.match.score}%</strong></div>` : ""}
    <div style="margin-top:6px;opacity:0.7;">Nothing was submitted. Review highlighted fields before applying.</div>
  `;
  document.body.appendChild(panel);
  document.getElementById("resume-fit-close").addEventListener("click", () => panel.remove());

  sendResult(outcome);
})();
