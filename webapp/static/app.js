/* RPG Name Generator — Frontend (Sidebar + Catalog) */
"use strict";

// ── State ──
let catalog = null;       // {domains: [{id, label, groups: [{id, label, abbreviation, entries}]}]}
let activeDomain = "names";
let results = [];
let openGroups = {};      // group_id -> boolean (accordion state)

const sidebar = document.getElementById("sidebar");
const sidebarGroups = document.getElementById("sidebar-groups");
const sidebarSearch = document.getElementById("sidebar-search");
const rowsContainer = document.getElementById("rows-container");
const resultsSection = document.getElementById("results-section");
const resultsGrid = document.getElementById("results-grid");

// ── Init ──
document.addEventListener("DOMContentLoaded", async () => {
  await loadCatalog();
  renderSidebar();
  bindGlobalEvents();
  const group = catalog.domains.find(d => d.id === "names")?.groups.find(g => g.entries.length);
  const entry = group?.entries.find(e => e.id === "FR") || group?.entries[0];
  if (entry) addRow(entry.id, entry.label, entry.supported_types);
});

async function loadCatalog() {
  const res = await fetch("/api/catalog");
  catalog = await res.json();
}

// ── Sidebar ──
function renderSidebar() {
  const query = (sidebarSearch.value || "").toLowerCase();
  const domain = catalog.domains.find(d => d.id === activeDomain);
  if (!domain) { sidebarGroups.innerHTML = ""; return; }

  let html = "";
  for (const group of domain.groups) {
    const filtered = query
      ? group.entries.filter(e => e.label.toLowerCase().includes(query) || e.id.toLowerCase().includes(query))
      : group.entries;
    if (filtered.length === 0) continue;

    const isOpen = openGroups[group.id] === true; // default collapsed
    html += `<div class="sidebar-group${isOpen ? " open" : ""}">`;
    html += `<div class="group-header" data-group="${esc(group.id)}">`;
    html += `<span class="group-chevron">${isOpen ? "\u25BC" : "\u25B6"}</span> `;
    html += `${esc(group.label)} <span class="group-count">(${filtered.length})</span>`;
    html += `</div>`;
    html += `<div class="group-entries"${isOpen ? "" : ' style="display:none"'}>`;
    for (const entry of filtered) {
      const badge = entry.count
        ? ` <span class="entry-count">${shortNum(entry.count)}</span>`
        : ' <span class="entry-count entry-gen" title="procedural generator">&#x2699;</span>';
      html += `<div class="style-entry" data-id="${esc(entry.id)}" data-label="${esc(entry.label)}" data-types="${esc(JSON.stringify(entry.supported_types))}" title="${esc(entry.id)}">${highlight(entry.label, query)}${badge}</div>`;
    }
    html += `</div></div>`;
  }

  if (!html) html = `<div class="sidebar-empty">No matches</div>`;
  sidebarGroups.innerHTML = html;

  // Bind click handlers
  sidebarGroups.querySelectorAll(".group-header").forEach(el => {
    el.addEventListener("click", () => {
      const gid = el.dataset.group;
      const group = el.parentElement;
      const entries = group.querySelector(".group-entries");
      const isOpen = group.classList.toggle("open");
      openGroups[gid] = isOpen;
      entries.style.display = isOpen ? "" : "none";
      el.querySelector(".group-chevron").textContent = isOpen ? "\u25BC" : "\u25B6";
    });
  });

  sidebarGroups.querySelectorAll(".style-entry").forEach(el => {
    el.addEventListener("click", () => {
      const id = el.dataset.id;
      const label = el.dataset.label;
      const types = JSON.parse(el.dataset.types);
      addRow(id, label, types);
    });
  });
}

// ── Row Management ──
function addRow(styleId, label, supportedTypes) {
  const row = document.createElement("div");
  row.className = "form-row";
  row.dataset.style = styleId;

  // Type options filtered by supported_types
  let typeOpts = "";
  const typeLabels = {
    fullname: "Full Name",
    forename: "Forename",
    surname: "Surname",
    place: "Place",
  };
  for (const t of supportedTypes) {
    typeOpts += `<option value="${t}">${typeLabels[t] || t}</option>`;
  }

  const isPlace = supportedTypes.length === 1 && supportedTypes[0] === "place";

  row.innerHTML = `
    <span class="style-label" title="${esc(styleId)}">${esc(label)}</span>
    <select class="type-select">${typeOpts}</select>
    <input type="number" class="count-input" value="5" min="1" max="100">
    <select class="gender-select"${isPlace ? ' style="display:none"' : ""}>
      <option value="">Any</option>
      <option value="M">M</option>
      <option value="F">F</option>
    </select>
    <button class="btn-remove" title="Remove row">&times;</button>
  `;

  // Default: fullname if available, else first option
  const typeSelect = row.querySelector(".type-select");
  if (supportedTypes.includes("fullname")) {
    typeSelect.value = "fullname";
  }

  // Hide gender for place rows dynamically
  typeSelect.addEventListener("change", () => {
    row.querySelector(".gender-select").style.display =
      typeSelect.value === "place" ? "none" : "";
  });

  row.querySelector(".btn-remove").addEventListener("click", () => row.remove());
  rowsContainer.appendChild(row);
}

function getRowData() {
  const romanize = document.getElementById("chk-romanize").checked;
  return [...rowsContainer.querySelectorAll(".form-row")].map(row => ({
    style: row.dataset.style,
    type: row.querySelector(".type-select").value,
    count: parseInt(row.querySelector(".count-input").value, 10) || 1,
    gender: row.querySelector(".gender-select").value || null,
    romanize,
  }));
}

// ── Generation ──
async function generateAll() {
  const rows = getRowData().filter(r => r.style);
  if (!rows.length) return;

  const btn = document.getElementById("btn-generate");
  btn.disabled = true;
  btn.classList.add("spinner");

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requests: rows }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Generation failed");
    results = data.results;
    renderResults();
  } catch (err) {
    alert("Request failed: " + err.message);
  } finally {
    btn.disabled = false;
    btn.classList.remove("spinner");
  }
}

async function rerollOne(index) {
  const r = results[index];
  const req = { style: r.style, type: r.type, count: r.count, gender: r.gender, romanize: r.romanize };
  const card = resultsGrid.children[index];
  const btn = card.querySelector(".btn-reroll");
  btn.textContent = "...";

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requests: [req] }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Generation failed");
    results[index] = data.results[0];
    renderCard(card, results[index], index);
  } catch (err) {
    btn.textContent = "err";
  }
}

async function rerollAll() {
  const requests = results.map(r => ({
    style: r.style, type: r.type, count: r.count, gender: r.gender, romanize: r.romanize,
  }));
  const btn = document.getElementById("btn-reroll-all");
  btn.disabled = true;
  btn.classList.add("spinner");

  try {
    const res = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requests }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Generation failed");
    results = data.results;
    renderResults();
  } catch (err) {
    alert("Re-roll failed: " + err.message);
  } finally {
    btn.disabled = false;
    btn.classList.remove("spinner");
  }
}

// ── Render ──
function renderResults() {
  resultsSection.classList.remove("hidden");
  resultsGrid.innerHTML = "";
  results.forEach((r, i) => {
    const card = document.createElement("div");
    card.className = "result-card";
    renderCard(card, r, i);
    resultsGrid.appendChild(card);
  });
}

function renderCard(card, r, index) {
  const meta = [r.type, r.gender ? `gender=${r.gender}` : null].filter(Boolean).join(" / ");
  if (r.error) {
    card.className = "result-card error";
    card.innerHTML = `
      <div class="card-head">
        <span class="card-title">${esc(r.style)}</span>
        <span class="card-meta">${esc(meta)}</span>
      </div>
      <div class="card-body">${esc(r.error)}</div>`;
  } else {
    card.className = "result-card";
    card.innerHTML = `
      <div class="card-head">
        <span class="card-title">${esc(r.style)}</span>
        <span class="card-meta">${esc(meta)}</span>
        <span class="card-actions">
          <button class="btn-copy" title="Copy to clipboard">copy</button>
          <button class="btn-reroll" data-idx="${index}">re-roll</button>
        </span>
      </div>
      <div class="card-body">
        <ul>${r.names.map(n => `<li>${esc(n)}</li>`).join("")}</ul>
      </div>`;
    card.querySelector(".btn-reroll").addEventListener("click", () => rerollOne(index));
    card.querySelector(".btn-copy").addEventListener("click", (e) => {
      const text = r.names.join("\n");
      navigator.clipboard.writeText(text).then(() => {
        e.target.textContent = "done!";
        setTimeout(() => { e.target.textContent = "copy"; }, 1000);
      });
    });
  }
}

// ── Export ──
function exportCSV() {
  if (!results.length) return;
  let csv = "style,type,gender,name\n";
  for (const r of results) {
    if (r.error) continue;
    for (const n of r.names) {
      csv += `"${r.style}","${r.type}","${r.gender || ""}","${n.replace(/"/g, '""')}"\n`;
    }
  }
  download(csv, "names.csv", "text/csv");
}

function exportJSON() {
  if (!results.length) return;
  download(JSON.stringify(results, null, 2), "names.json", "application/json");
}

function exportTXT() {
  if (!results.length) return;
  let txt = "";
  for (const r of results) {
    txt += `=== ${r.style} (${r.type}${r.gender ? ", " + r.gender : ""}) ===\n`;
    if (r.error) {
      txt += `  ERROR: ${r.error}\n`;
    } else {
      for (const n of r.names) txt += `  ${n}\n`;
    }
    txt += "\n";
  }
  download(txt, "names.txt", "text/plain");
}

function download(content, filename, mime) {
  const blob = new Blob([content], { type: mime + ";charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ── Event Bindings ──
function bindGlobalEvents() {
  document.getElementById("btn-generate").addEventListener("click", generateAll);
  document.getElementById("btn-reroll-all").addEventListener("click", rerollAll);
  document.getElementById("btn-export-csv").addEventListener("click", exportCSV);
  document.getElementById("btn-export-json").addEventListener("click", exportJSON);
  document.getElementById("btn-export-txt").addEventListener("click", exportTXT);

  // Domain tabs
  sidebar.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      sidebar.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeDomain = btn.dataset.domain;
      sidebarSearch.value = "";
      renderSidebar();
    });
  });

  // Sidebar filter
  sidebarSearch.addEventListener("input", () => renderSidebar());
}

// ── Util ──
function esc(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML.replace(/"/g, "&quot;");
}

function shortNum(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n);
}

function highlight(text, query) {
  if (!query) return esc(text);
  const idx = text.toLowerCase().indexOf(query);
  if (idx < 0) return esc(text);
  return esc(text.slice(0, idx))
    + `<b>${esc(text.slice(idx, idx + query.length))}</b>`
    + esc(text.slice(idx + query.length));
}
