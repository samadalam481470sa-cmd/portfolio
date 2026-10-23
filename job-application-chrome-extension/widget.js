/**
 * Always-available floating helper widget, injected on every page (unless
 * the user disables it from the popup). Shows a small draggable bubble;
 * clicking it opens a panel with one-click actions:
 *   - Fill Name / Email / Phone (from the saved resume)
 *   - Full Autofill + Job Fit Score (runs the same engine as the popup)
 *
 * Nothing here submits forms or simulates mouse movement — it only fills
 * fields the user explicitly asks it to fill, with their own real data.
 */
(function () {
  if (window.__resumeFitWidgetInjected) return;
  window.__resumeFitWidgetInjected = true;

  // Don't bother rendering inside iframes, on non-html documents, etc.
  if (window.top !== window.self) return;

  chrome.storage.local.get(["widgetEnabled"], (res) => {
    if (res.widgetEnabled === false) return;
    initWidget();
  });

  function initWidget() {
    const root = document.createElement("div");
    root.id = "resume-fit-widget-root";
    root.style.cssText = "all:initial;";
    document.documentElement.appendChild(root);

    const shadow = root.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = `
      * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
      .bubble {
        position: fixed; bottom: 24px; right: 24px; width: 48px; height: 48px;
        border-radius: 50%; background: #4338ca; color: #fff; display: flex;
        align-items: center; justify-content: center; font-size: 20px;
        cursor: grab; box-shadow: 0 4px 14px rgba(0,0,0,0.3); z-index: 2147483647;
        user-select: none;
      }
      .bubble:active { cursor: grabbing; }
      .panel {
        position: fixed; bottom: 82px; right: 24px; width: 260px;
        background: #1a1a2e; color: #fff; border-radius: 12px;
        box-shadow: 0 8px 28px rgba(0,0,0,0.35); z-index: 2147483647;
        padding: 12px; display: none; font-size: 12px; line-height: 1.5;
      }
      .panel.open { display: block; }
      .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
      .panel-header strong { font-size: 13px; }
      .close-btn { cursor: pointer; opacity: 0.7; font-size: 16px; background:none; border:none; color:#fff; }
      .row { display: flex; gap: 6px; margin-bottom: 6px; }
      button.action {
        flex: 1; background: #2d2d4d; color: #fff; border: none; border-radius: 6px;
        padding: 6px 4px; font-size: 11px; cursor: pointer;
      }
      button.action:hover { background: #3a3a63; }
      button.primary { background: #4338ca; }
      button.primary:hover { background: #3730a3; }
      .status { margin-top: 8px; opacity: 0.85; font-size: 11px; white-space: pre-line; }
    `;
    shadow.appendChild(style);

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = "RF";
    bubble.title = "Resume-Fit Assistant";
    shadow.appendChild(bubble);

    const panel = document.createElement("div");
    panel.className = "panel";
    panel.innerHTML = `
      <div class="panel-header">
        <strong>Resume-Fit Assistant</strong>
        <button class="close-btn" id="closeBtn">&times;</button>
      </div>
      <div class="row">
        <button class="action" id="fillNameBtn">Fill Name</button>
        <button class="action" id="fillEmailBtn">Fill Email</button>
        <button class="action" id="fillPhoneBtn">Fill Phone</button>
      </div>
      <div class="row">
        <button class="action primary" id="fullAutofillBtn" style="flex:2;">Full Autofill + Job Score</button>
      </div>
      <div class="status" id="widgetStatus"></div>
    `;
    shadow.appendChild(panel);

    let dragged = false;

    bubble.addEventListener("click", () => {
      if (dragged) {
        dragged = false;
        return;
      }
      panel.classList.toggle("open");
    });

    panel.querySelector("#closeBtn").addEventListener("click", () => panel.classList.remove("open"));

    makeDraggable(bubble, () => {
      dragged = true;
    });

    async function getProfileAndQa() {
      const stored = await chrome.storage.local.get(["resumeProfile", "customAnswers"]);
      return {
        profile: stored.resumeProfile,
        qaItems: (stored.customAnswers || []).filter((qa) => qa && qa.question && qa.answer),
      };
    }

    function setStatus(text) {
      panel.querySelector("#widgetStatus").innerHTML = text;
    }

    panel.querySelector("#fillNameBtn").addEventListener("click", async () => {
      const { profile } = await getProfileAndQa();
      if (!profile) return setStatus("Set up your resume in the extension popup first.");
      const count =
        window.ResumeFitEngine.fillFieldType(profile, "name") +
        window.ResumeFitEngine.fillFieldType(profile, "firstName") +
        window.ResumeFitEngine.fillFieldType(profile, "lastName");
      setStatus(count > 0 ? `Filled ${count} name field(s).` : "No matching name field found on this page.");
    });

    panel.querySelector("#fillEmailBtn").addEventListener("click", async () => {
      const { profile } = await getProfileAndQa();
      if (!profile) return setStatus("Set up your resume in the extension popup first.");
      const count = window.ResumeFitEngine.fillFieldType(profile, "email");
      setStatus(count > 0 ? `Filled ${count} email field(s).` : "No matching email field found on this page.");
    });

    panel.querySelector("#fillPhoneBtn").addEventListener("click", async () => {
      const { profile } = await getProfileAndQa();
      if (!profile) return setStatus("Set up your resume in the extension popup first.");
      const count = window.ResumeFitEngine.fillFieldType(profile, "phone");
      setStatus(count > 0 ? `Filled ${count} phone field(s).` : "No matching phone field found on this page.");
    });

    panel.querySelector("#fullAutofillBtn").addEventListener("click", async () => {
      const { profile, qaItems } = await getProfileAndQa();
      if (!profile || (!profile.email && !profile.name)) {
        setStatus("Set up your resume in the extension popup first (Resume tab).");
        return;
      }
      const outcome = window.ResumeFitEngine.runFullAutofill(profile, qaItems);
      let text = `Filled: ${outcome.filledCount} | Drafted: ${outcome.draftedCount} | Needs review: ${outcome.flaggedCount}`;
      if (outcome.match) text += `\nJob fit score: ${outcome.match.score}%`;
      text += "\nNothing was submitted — review highlighted fields first.";
      setStatus(text);
    });

    function makeDraggable(handle, onDragStart) {
      let startX, startY, startRight, startBottom, moved;
      handle.addEventListener("mousedown", (e) => {
        moved = false;
        startX = e.clientX;
        startY = e.clientY;
        const rect = handle.getBoundingClientRect();
        startRight = window.innerWidth - rect.right;
        startBottom = window.innerHeight - rect.bottom;
        e.preventDefault();

        function onMouseMove(ev) {
          const dx = ev.clientX - startX;
          const dy = ev.clientY - startY;
          if (Math.abs(dx) > 3 || Math.abs(dy) > 3) {
            moved = true;
            if (onDragStart) onDragStart();
          }
          const newRight = Math.max(4, startRight - dx);
          const newBottom = Math.max(4, startBottom - dy);
          handle.style.right = `${newRight}px`;
          handle.style.bottom = `${newBottom}px`;
          panel.style.right = `${newRight}px`;
          panel.style.bottom = `${newBottom + 58}px`;
        }

        function onMouseUp() {
          document.removeEventListener("mousemove", onMouseMove);
          document.removeEventListener("mouseup", onMouseUp);
        }

        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", onMouseUp);
      });
    }
  }
})();
