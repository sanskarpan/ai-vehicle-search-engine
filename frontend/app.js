const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(
  /[&<>"']/g,
  (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character],
);

const EMPTY_ICON = '<svg class="icon icon-empty" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="8"></circle><path d="M12 7v5l3 2"></path></svg>';
const STAR_ICON = '<svg class="icon icon-star" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-2.9-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3Z"></path></svg>';

let offset = 0;
let lastResponse = null;
let activeRequest = null;
const limit = 9;

function setNotice(message, kind = "") {
  const notice = $("#notice");
  notice.textContent = message;
  notice.className = `notice ${kind}`;
  notice.hidden = !message;
}

function formatMoney(value) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

function emptyState(title, message) {
  return `<div class="empty-state"><div class="empty-orbit">${EMPTY_ICON}</div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p></div>`;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    throw new Error(data?.error?.message || `Request failed with HTTP ${response.status}.`);
  }
  if (!data) {
    throw new Error("The service returned an unexpected response format.");
  }
  return data;
}

function vehicleCard(item) {
  const vehicle = item.vehicle;
  const safety = vehicle.safety || {};
  const stars = safety.adult_stars == null ? "Unrated" : `${safety.adult_stars}/5`;
  return `<article class="vehicle-card" data-id="${escapeHtml(vehicle.id)}" tabindex="0" role="button" aria-label="View ${escapeHtml(vehicle.make)} ${escapeHtml(vehicle.model)} details">
    <div class="card-top"><span class="card-kicker">${escapeHtml(vehicle.body_type)} · ${escapeHtml(vehicle.year)}</span><span class="card-score">${Number(item.score || 0).toFixed(2)} match</span></div>
    <h3>${escapeHtml(vehicle.make)} ${escapeHtml(vehicle.model)}</h3>
    <div class="variant">${escapeHtml(vehicle.variant)} · ${escapeHtml(vehicle.city)}</div>
    <div class="price">${formatMoney(vehicle.price_inr)}</div>
    <div class="specs"><span>${escapeHtml(vehicle.fuel_type)}</span><span>${escapeHtml(vehicle.transmission)}</span><span>${Number(vehicle.odometer_km).toLocaleString("en-IN")} km</span><span>${escapeHtml(vehicle.seats)} seats</span></div>
    <div class="reason">${escapeHtml((item.match_reasons || []).slice(0, 2).join(" · ") || "Catalogue match")}</div>
    <div class="specs"><span class="stars">${STAR_ICON} ${escapeHtml(stars)}</span><span>${vehicle.is_synthetic ? "synthetic data" : ""}</span></div>
  </article>`;
}

function bindVehicleCards() {
  document.querySelectorAll(".vehicle-card").forEach((card) => {
    const open = () => showVehicleDetail(card.dataset.id);
    card.addEventListener("click", open);
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        open();
      }
    });
  });
}

function render(body) {
  lastResponse = body;
  const results = body.results || [];
  const meta = body.meta || {};
  const clarification = body.clarification?.message || "Try widening your budget or removing one constraint.";
  $("#resultTitle").textContent = body.status === "needs_clarification"
    ? "A little more detail"
    : `${body.total || 0} ${body.total === 1 ? "vehicle" : "vehicles"} found`;
  $("#results").innerHTML = results.length
    ? results.map(vehicleCard).join("")
    : emptyState(body.status === "needs_clarification" ? "Let’s refine that search" : "No exact matches", clarification);
  $("#interpretBtn").hidden = !body.interpretation;
  $("#rawBtn").hidden = false;
  $("#pager").hidden = !body.total || body.total <= limit;
  $("#pageLabel").textContent = `${offset + 1}–${Math.min(offset + results.length, body.total)} of ${body.total}`;
  $("#prev").disabled = offset === 0;
  $("#next").disabled = !body.has_more;

  const badge = meta.provider ? `${meta.provider.toUpperCase()} · LIVE` : meta.degraded ? "OFFLINE FALLBACK" : "OFFLINE DEMO";
  $("#providerBadge").textContent = badge;
  $("#providerBadge").className = `badge ${meta.provider ? "live" : "muted"}`;
  if (meta.catalogue_version) {
    $("#version").textContent = `synthetic demo · ${meta.catalogue_version}`;
  }
  if (body.status === "needs_clarification") {
    setNotice(clarification);
  } else {
    setNotice(meta.degraded ? "Provider unavailable — showing conservative offline interpretation." : "");
  }
  bindVehicleCards();
}

async function search() {
  const query = $("#query").value.trim();
  if (!query) {
    setNotice("Describe the vehicle you are looking for.", "error");
    return;
  }
  activeRequest?.abort();
  const controller = new AbortController();
  activeRequest = controller;
  const submit = $('#searchForm button[type="submit"]');
  submit.disabled = true;
  submit.setAttribute("aria-busy", "true");
  setNotice("");
  $("#resultTitle").textContent = "Searching…";
  $("#results").innerHTML = emptyState("Reading your brief", "Applying exact catalogue filters.");
  const body = { query, limit, offset };
  if ($("#sort").value) body.sort = $("#sort").value;
  try {
    const data = await fetchJson("/api/v1/search", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (activeRequest === controller) render(data);
  } catch (error) {
    if (error.name !== "AbortError" && activeRequest === controller) {
      setNotice(error.message, "error");
      $("#resultTitle").textContent = "Search unavailable";
      $("#results").innerHTML = "";
    }
  } finally {
    if (activeRequest === controller) {
      activeRequest = null;
      submit.disabled = false;
      submit.removeAttribute("aria-busy");
    }
  }
}

async function showVehicleDetail(id) {
  try {
    const data = await fetchJson(`/api/v1/vehicles/${encodeURIComponent(id)}`);
    const vehicle = data.vehicle;
    const safety = vehicle.safety || {};
    $("#detailContent").innerHTML = `<div class="detail">
      <span class="eyebrow">${escapeHtml(vehicle.body_type)} · ${escapeHtml(vehicle.condition)} · ${escapeHtml(vehicle.city)}</span>
      <h2>${escapeHtml(vehicle.make)} ${escapeHtml(vehicle.model)}</h2>
      <div class="sub">${escapeHtml(vehicle.variant)} · ${escapeHtml(vehicle.year)} · synthetic catalogue listing</div>
      <div class="price">${formatMoney(vehicle.price_inr)}</div>
      <div class="detail-grid">
        <div><small>Odometer</small><strong>${Number(vehicle.odometer_km).toLocaleString("en-IN")} km</strong></div>
        <div><small>Powertrain</small><strong>${escapeHtml(vehicle.fuel_type)} · ${escapeHtml(vehicle.transmission)}</strong></div>
        <div><small>Seats</small><strong>${escapeHtml(vehicle.seats)}</strong></div>
        <div><small>Safety adult</small><strong>${safety.adult_stars == null ? "Unknown" : escapeHtml(`${safety.adult_stars}/5`)}</strong></div>
        <div><small>Safety child</small><strong>${safety.child_stars == null ? "Unknown" : escapeHtml(`${safety.child_stars}/5`)}</strong></div>
        <div><small>Features</small><strong>${escapeHtml((vehicle.features || []).join(", ") || "None listed")}</strong></div>
      </div>
      <p class="sub">${escapeHtml(vehicle.description)}</p>
    </div>`;
    $("#detailDialog").showModal();
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function resetSearch() {
  activeRequest?.abort();
  activeRequest = null;
  const submit = $('#searchForm button[type="submit"]');
  submit.disabled = false;
  submit.removeAttribute("aria-busy");
  offset = 0;
  lastResponse = null;
  $("#query").value = "";
  $("#sort").value = "";
  $("#interpretation").hidden = true;
  $("#rawBtn").hidden = true;
  $("#interpretBtn").hidden = true;
  $("#pager").hidden = true;
  setNotice("");
  $("#resultTitle").textContent = "Ready when you are";
  $("#results").innerHTML = emptyState("Search the catalogue", "Use one of the example briefs above or describe your ideal vehicle.");
}

$("#searchForm").addEventListener("submit", (event) => {
  event.preventDefault();
  offset = 0;
  search();
});
document.querySelectorAll("[data-query]").forEach((button) => {
  button.addEventListener("click", () => {
    $("#query").value = button.dataset.query;
    offset = 0;
    search();
  });
});
$("#sort").addEventListener("change", () => {
  if ($("#query").value.trim()) {
    offset = 0;
    search();
  }
});
$("#reset").addEventListener("click", resetSearch);
$("#prev").addEventListener("click", () => {
  offset = Math.max(0, offset - limit);
  search();
});
$("#next").addEventListener("click", () => {
  if (lastResponse?.has_more) {
    offset += limit;
    search();
  }
});
$("#interpretBtn").addEventListener("click", () => {
  const interpretation = lastResponse?.interpretation;
  if (!interpretation) return;
  $("#interpretation").innerHTML = `<strong>Extracted intent</strong><br>${(interpretation.predicates || []).map((predicate) => `<code>${escapeHtml(predicate.field)} ${escapeHtml(predicate.op)} ${escapeHtml((predicate.values || []).join(", "))}</code>`).join(" ")}<br><span>${escapeHtml((interpretation.assumptions || []).join(" "))}</span>`;
  $("#interpretation").hidden = false;
});
$("#rawBtn").addEventListener("click", () => {
  $("#detailContent").innerHTML = `<div class="raw">${escapeHtml(JSON.stringify(lastResponse, null, 2))}</div>`;
  $("#detailDialog").showModal();
});
$("#dialogClose").addEventListener("click", () => $("#detailDialog").close());

fetchJson("/health/ready")
  .then(() => {
    $("#health").classList.add("ok");
    $("#health").innerHTML = "<i></i> service ready";
  })
  .catch(() => {
    $("#health").classList.add("bad");
    $("#health").innerHTML = "<i></i> service unavailable";
  });
