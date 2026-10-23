const state = {
  opportunities: [],
  filter: "all",
};

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const number = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
});

document.addEventListener("DOMContentLoaded", () => {
  document
    .getElementById("recommendation-filter")
    .addEventListener("change", (event) => {
      state.filter = event.target.value;
      renderOpportunities();
      renderMap();
    });

  document.getElementById("close-report").addEventListener("click", () => {
    document.getElementById("report-dialog").close();
  });

  loadDashboard();
});

async function loadDashboard() {
  let payload = null;
  try {
    const response = await fetch("/opportunities?limit=50");
    if (response.ok) {
      payload = await response.json();
    }
  } catch (_error) {
    payload = null;
  }

  payload = payload || window.ESTATEIQ_DEMO_DATA;
  if (!payload) {
    renderError("Unable to load EstateIQ opportunity data.");
    return;
  }
  state.opportunities = payload.opportunities || [];
  renderMetrics();
  renderTopOpportunity();
  renderOpportunities();
  renderMap();
}

function renderMetrics() {
  const markets = new Set(state.opportunities.map((item) => item.market?.zip_code).filter(Boolean));
  const contacts = state.opportunities.reduce((total, item) => total + (item.contacts?.length || 0), 0);
  const bestScore = state.opportunities[0]?.score?.score;

  setText("metric-properties", state.opportunities.length);
  setText("metric-markets", markets.size);
  setText("metric-contacts", contacts);
  setText("metric-score", bestScore ? number.format(bestScore) : "--");
}

function renderTopOpportunity() {
  const top = state.opportunities[0];
  const container = document.getElementById("top-opportunity");
  if (!top) {
    container.innerHTML = "<p>No opportunities are available yet.</p>";
    return;
  }

  container.innerHTML = `
    <div class="top-score">${number.format(top.score.score)}</div>
    <h2>${escapeHtml(top.property.address)}</h2>
    <p class="muted">${escapeHtml(top.property.city)}, ${escapeHtml(top.property.state)} | ${escapeHtml(top.score.recommendation)}</p>
    <p>${escapeHtml(firstReason(top))}</p>
    <button class="report-button" data-report-id="${escapeHtml(top.property.source_id)}">Read investment report</button>
  `;
  wireReportButtons(container);
}

function renderOpportunities() {
  const list = document.getElementById("opportunity-list");
  const filtered = filteredOpportunities();
  if (!filtered.length) {
    list.innerHTML = "<p class=\"muted\">No opportunities match this filter.</p>";
    return;
  }

  list.innerHTML = filtered
    .map((item) => {
      const property = item.property;
      const score = item.score;
      const market = item.market;
      const contact = item.contacts?.[0];
      return `
        <article class="opportunity-card">
          <div class="card-header">
            <div>
              <span class="tag">${escapeHtml(score.recommendation)}</span>
              <h3>${escapeHtml(property.address)}</h3>
              <p class="muted">${escapeHtml(property.city)}, ${escapeHtml(property.state)} ${escapeHtml(property.zip_code)}</p>
            </div>
            <div class="score-pill">${number.format(score.score)}</div>
          </div>
          <div class="card-stats">
            <div>
              <span class="meta-label">Price</span>
              <strong>${currency.format(property.price)}</strong>
            </div>
            <div>
              <span class="meta-label">Cap rate</span>
              <strong>${number.format(score.cap_rate_pct)}%</strong>
            </div>
            <div>
              <span class="meta-label">Cash flow</span>
              <strong>${currency.format(score.annual_cash_flow)}</strong>
            </div>
          </div>
          <ul class="reasons">
            ${(score.reasons || []).slice(0, 2).map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}
          </ul>
          <p class="muted">
            ${market ? `${escapeHtml(market.city)} market: ${number.format(market.job_growth_pct)}% job growth, ${number.format(market.rent_growth_pct)}% rent growth.` : "Market data pending."}
            ${contact ? ` Public contact: ${escapeHtml(contact.name)}.` : ""}
          </p>
          <div class="card-actions">
            <button class="report-button" data-report-id="${escapeHtml(property.source_id)}">Open report</button>
          </div>
        </article>
      `;
    })
    .join("");
  wireReportButtons(list);
}

function renderMap() {
  const canvas = document.getElementById("map-canvas");
  const details = document.getElementById("map-details");
  const opportunities = filteredOpportunities();
  canvas.innerHTML = "";

  if (!opportunities.length) {
    details.innerHTML = "<h3>No map results</h3><p>Change the recommendation filter to show more opportunities.</p>";
    return;
  }

  const lats = opportunities.map((item) => item.property.latitude);
  const lngs = opportunities.map((item) => item.property.longitude);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);

  opportunities.forEach((item, index) => {
    const pin = document.createElement("button");
    pin.className = "map-pin";
    pin.textContent = Math.round(item.score.score);
    pin.style.left = `${scale(item.property.longitude, minLng, maxLng)}%`;
    pin.style.top = `${100 - scale(item.property.latitude, minLat, maxLat)}%`;
    pin.title = `${item.property.address} - ${item.score.recommendation}`;
    pin.addEventListener("click", () => {
      document.querySelectorAll(".map-pin").forEach((element) => element.classList.remove("active"));
      pin.classList.add("active");
      renderMapDetails(item);
    });
    canvas.appendChild(pin);
    if (index === 0) {
      pin.classList.add("active");
      renderMapDetails(item);
    }
  });
}

function renderMapDetails(item) {
  const details = document.getElementById("map-details");
  const property = item.property;
  const market = item.market;
  details.innerHTML = `
    <p class="card-label">${escapeHtml(item.score.recommendation)}</p>
    <h3>${escapeHtml(property.address)}</h3>
    <p class="muted">${escapeHtml(property.city)}, ${escapeHtml(property.state)} | ${currency.format(property.price)}</p>
    <div class="card-stats">
      <div><span class="meta-label">Score</span><strong>${number.format(item.score.score)}</strong></div>
      <div><span class="meta-label">Demand</span><strong>${number.format(item.score.demand_score)}</strong></div>
      <div><span class="meta-label">Market</span><strong>${number.format(item.score.market_strength)}</strong></div>
    </div>
    <p>${escapeHtml(firstReason(item))}</p>
    ${market ? `<p class="muted">Population growth ${number.format(market.population_growth_pct)}%, appreciation ${number.format(market.appreciation_pct)}%.</p>` : ""}
    <button class="report-button" data-report-id="${escapeHtml(property.source_id)}">Open report</button>
  `;
  wireReportButtons(details);
}

async function openReport(sourceId) {
  const dialog = document.getElementById("report-dialog");
  const title = document.getElementById("report-title");
  const body = document.getElementById("report-body");
  title.textContent = "Loading report";
  body.innerHTML = "<p class=\"muted\">Generating investment report...</p>";
  dialog.showModal();

  let report = null;
  try {
    const response = await fetch(`/properties/${encodeURIComponent(sourceId)}/report`);
    if (response.ok) {
      const payload = await response.json();
      report = payload.report;
    }
  } catch (_error) {
    report = null;
  }

  report = report || fallbackReport(sourceId);
  if (!report) {
    title.textContent = "Report unavailable";
    body.innerHTML = "<p>EstateIQ could not load this report.</p>";
    return;
  }
  title.textContent = report.title;
  body.innerHTML = `
    <section>
      <h3>Executive summary</h3>
      <p>${escapeHtml(report.executive_summary)}</p>
    </section>
    ${reportSection("Positives", report.positives)}
    ${reportSection("Risks", report.risks)}
    ${reportSection("Next steps", report.next_steps)}
  `;
}

function fallbackReport(sourceId) {
  const item = state.opportunities.find((opportunity) => opportunity.property.source_id === sourceId);
  if (!item) {
    return null;
  }
  const property = item.property;
  const score = item.score;
  const market = item.market;
  const contact = item.contacts?.[0];
  const positives = score.reasons || [firstReason(item)];
  const risks = [];
  if (score.annual_cash_flow < 0) {
    risks.push("Modeled cash flow is negative before investor-specific financing assumptions.");
  }
  if (score.cap_rate_pct < 5.5) {
    risks.push("Cap rate is below the preferred threshold for income-focused acquisitions.");
  }
  if (market?.inventory_level > 800) {
    risks.push("Inventory is elevated, which can weaken pricing power.");
  }
  if (!risks.length) {
    risks.push("No major model-level risks detected; verify condition, rents, and title history.");
  }
  const nextSteps = [
    "Validate rent estimate against active comparable leases.",
    "Review public records for liens, permits, assessed value, and ownership history.",
    "Underwrite financing terms, taxes, insurance, repairs, and vacancy assumptions.",
  ];
  if (contact) {
    nextSteps.push(`Contact ${contact.name} (${contact.role}) using the public business contact record.`);
  }
  return {
    title: `${property.address}, ${property.city}, ${property.state} - ${score.recommendation}`,
    executive_summary: `This ${property.property_type} opportunity scores ${number.format(score.score)}/100. The model estimates a ${number.format(score.cap_rate_pct)}% cap rate and ${currency.format(score.annual_cash_flow)} in annual cash flow, supported by market growth indicators.`,
    positives,
    risks,
    next_steps: nextSteps,
  };
}

function reportSection(title, items) {
  return `
    <section>
      <h3>${escapeHtml(title)}</h3>
      <ul>${(items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>
  `;
}

function wireReportButtons(root) {
  root.querySelectorAll("[data-report-id]").forEach((button) => {
    button.addEventListener("click", () => openReport(button.dataset.reportId));
  });
}

function filteredOpportunities() {
  if (state.filter === "all") {
    return state.opportunities;
  }
  return state.opportunities.filter((item) => item.score.recommendation === state.filter);
}

function firstReason(item) {
  return item.score?.reasons?.[0] || "Opportunity requires deeper underwriting.";
}

function scale(value, min, max) {
  if (max === min) {
    return 50;
  }
  return ((value - min) / (max - min)) * 84 + 8;
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function renderError(message) {
  document.getElementById("opportunity-list").innerHTML = `<p class="muted">${escapeHtml(message)}</p>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
