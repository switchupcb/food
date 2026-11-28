<%*
// ============================================================================
// Sync Macrofactor Brands.md — Enrich & Rename food-base/ notes from History CSV
// Extracts "<Base Food Name> By <Brand>", populates brand + aliases, and renames file
// ============================================================================

const FOOD_FOLDER = "food-base";

async function deterministicBase36Id(prefix, seed) {
  const data = new TextEncoder().encode(String(seed || "").trim().toLowerCase());
  const hashBuf = await crypto.subtle.digest("SHA-256", data);
  const bytes = new Uint8Array(hashBuf);
  let num = 0n;
  for (let i = 0; i < 6; i++) {
    num = (num << 8n) | BigInt(bytes.at(i));
  }
  return `${prefix}_${num.toString(36).padStart(8, "0").slice(0, 8)}`;
}

function pickNativeCsvFile() {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv,text/csv";
    input.style.display = "none";
    document.body.appendChild(input);

    const cleanup = () => input.remove();

    input.addEventListener("change", () => {
      const file = input.files && input.files.length > 0 ? input.files[0] : null;
      cleanup();
      resolve(file);
    });

    input.addEventListener("cancel", () => {
      cleanup();
      resolve(null);
    });

    input.click();
  });
}

function parseCSV(text) {
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;
  const clean = text.replace(/^\uFEFF/, "");

  for (let i = 0; i < clean.length; i++) {
    const ch = clean[i];
    const next = clean[i + 1];
    if (inQuotes) {
      if (ch === '"' && next === '"') {
        field += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        field += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        row.push(field);
        field = "";
      } else if (ch === "\(\r\)" && next === "\n") {
        row.push(field);
        rows.push(row);
        row = [];
        field = "";
        i++;
      } else if (ch === "\n" || ch === "\(\r\)") {
        row.push(field);
        rows.push(row);
        row = [];
        field = "";
      } else {
        field += ch;
      }
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  if (rows.length < 2) return { headers: [], records: [] };
  const headers = rows[0].map((h) => h.trim());
  const records = [];
  for (let r = 1; r < rows.length; r++) {
    if (rows[r].every((c) => c.trim() === "")) continue;
    const obj = {};
    for (let c = 0; c < headers.length; c++) {
      obj[headers[c]] = (rows[r][c] ?? "").trim();
    }
    records.push(obj);
  }
  return { headers, records };
}

function sanitizeFilename(name) {
  return String(name || "").replace(/[<>:"/\\|?*]+/g, "").replace(/\s+/g, " ").trim();
}

function normalizeKey(str) {
  return sanitizeFilename(String(str || "").replace(/__v_\d+\$/i, "")).toLowerCase();
}

// 1. Locate MacroFactor History CSV
const vaultCsvFiles = app.vault.getFiles()
  .filter((f) => f.extension.toLowerCase() === "csv" && f.name.toLowerCase().includes("macrofactor"))
  .sort((a, b) => b.stat.mtime - a.stat.mtime);

let csvRaw = "";
let csvLabel = "";

if (vaultCsvFiles.length > 0) {
  const options = [
    ...vaultCsvFiles.map((f) => `📄 Vault: ${f.path} (${new Date(f.stat.mtime).toLocaleDateString()})`),
    "📂 Browse Device (Downloads / Files app)...",
  ];
  const values = [...vaultCsvFiles, "BROWSE_NATIVE"];
  const choice = await tp.system.suggester(options, values, false, "Select MacroFactor History CSV to extract brands");
  if (!choice) return;

  if (choice === "BROWSE_NATIVE") {
    const picked = await pickNativeCsvFile();
    if (!picked) { new Notice("Brand sync cancelled."); return; }
    csvRaw = await picked.text();
    csvLabel = picked.name;
  } else {
    csvRaw = await app.vault.read(choice);
    csvLabel = choice.name;
  }
} else {
  new Notice("📂 Select your MacroFactor History CSV export...");
  const picked = await pickNativeCsvFile();
  if (!picked) { new Notice("Brand sync cancelled (no CSV selected)."); return; }
  csvRaw = await picked.text();
  csvLabel = picked.name;
}

const { headers, records } = parseCSV(csvRaw);
if (!headers.includes("Food Name")) {
  new Notice("❌ Invalid CSV: Expected a 'Food Name' column from MacroFactor History export.");
  return;
}

// 2. Build Base-Name -> Brand Map from "<Base Food Name> By <Brand>"
const brandCandidates = new Map();
for (const row of records) {
  const fullName = (row["Food Name"] || "").trim();
  if (!fullName) continue;

  const match = fullName.match(/^(.+?)\s+by\s+(.+)$/i);
  if (!match) continue;

  const baseName = match[1].trim();
  const brandName = match[2].trim();
  const key = normalizeKey(baseName);
  if (!key || !brandName) continue;

  if (!brandCandidates.has(key)) {
    brandCandidates.set(key, []);
  }
  const list = brandCandidates.get(key);
  if (!list.some((item) => item.brand.toLowerCase() === brandName.toLowerCase())) {
    list.push({ brand: brandName, fullName });
  }
}

// 3. Match, Enrich Frontmatter & Rename Existing food-base/ Notes
const foodFiles = app.vault.getMarkdownFiles().filter((f) => f.path.startsWith(`${FOOD_FOLDER}/`));
let updatedCount = 0;
let renamedCount = 0;
let skippedConflictCount = 0;
const updatedNotes = [];
const multiBrandConflicts = [];

for (const f of foodFiles) {
  const cache = app.metadataCache.getFileCache(f);
  const fm = cache?.frontmatter || {};
  if (String(fm.type || "").toLowerCase() !== "food") continue;

  const namesToCheck = [
    fm.food_name,
    f.basename,
    ...(Array.isArray(fm.aliases) ? fm.aliases : []),
  ].filter(Boolean);

  let matchedEntries = null;
  for (const candidateName of namesToCheck) {
    const key = normalizeKey(candidateName);
    if (brandCandidates.has(key)) {
      matchedEntries = brandCandidates.get(key);
      break;
    }
  }

  if (!matchedEntries || matchedEntries.length === 0) continue;

  if (matchedEntries.length > 1 && !fm.brand) {
    skippedConflictCount++;
    multiBrandConflicts.push({
      stem: f.basename,
      brands: matchedEntries.map((e) => e.brand).join(", "),
    });
    continue;
  }

  const chosen = matchedEntries[0];
  const activeBrand = fm.brand && String(fm.brand).trim() !== "" ? String(fm.brand).trim() : chosen.brand;

  // Build target branded stem preserving unit suffix "(unit)" and variant suffix "__v_N"
  const verMatch = f.basename.match(/(__v_\d+)$/i);
  const verSuffix = verMatch ? verMatch[1] : "";
  const unit = String(fm.serving_size || "serving").trim();
  const unitSuffix = unit.toLowerCase() === "serving" ? "" : ` (${sanitizeFilename(unit)})`;
  const targetStem = `${sanitizeFilename(chosen.fullName)}${unitSuffix}${verSuffix}`;
  const targetPath = `${FOOD_FOLDER}/${targetStem}.md`;

  const needsBrand = !fm.brand || String(fm.brand).trim() === "";
  const rawFoodName = fm.food_name ? String(fm.food_name).trim() : "";
  const needsRename = f.basename !== targetStem && !app.vault.getAbstractFileByPath(targetPath);

  if (needsBrand || needsRename) {
    await app.fileManager.processFrontMatter(f, (frontmatter) => {
      if (needsBrand) {
        frontmatter.brand = activeBrand;
      }
      const updatedAliases = Array.isArray(frontmatter.aliases) ? [...frontmatter.aliases] : [];
      // Keep the brandless Food Log name in aliases so future Food Log syncs match this note
      if (rawFoodName && !updatedAliases.includes(rawFoodName)) {
        updatedAliases.push(rawFoodName);
      }
      if (chosen.fullName && !updatedAliases.includes(chosen.fullName)) {
        updatedAliases.push(chosen.fullName);
      }
      if (updatedAliases.length > 0) {
        frontmatter.aliases = updatedAliases;
      }
      if (needsRename) {
        frontmatter.title = targetStem;
      }
    });

    if (needsRename) {
      await app.fileManager.renameFile(f, targetPath);
      renamedCount++;
    }

    updatedCount++;
    updatedNotes.push(`[[${needsRename ? targetStem : f.basename}]] → **${activeBrand}**${needsRename ? " *(renamed)*" : ""}`);
  }
}

// 4. Write Sync Log to _app/_logs/
const LOG_FOLDER = "_app/_logs";
if (!app.vault.getAbstractFileByPath("_app")) await app.vault.createFolder("_app");
if (!app.vault.getAbstractFileByPath(LOG_FOLDER)) await app.vault.createFolder(LOG_FOLDER);

const logStamp = tp.date.now("YYYY-MM-DD-HHmmss");
const logTitle = `brand-log-${logStamp}`;
await tp.file.move(`${LOG_FOLDER}/${logTitle}`);

const summaryLine = `[${FOOD_FOLDER}] Brands Enriched: ${updatedCount} | Renamed: ${renamedCount} | Multi-Brand Skipped: ${skippedConflictCount}`;
new Notice(`✅ ${summaryLine}`);
-%>
---
type: sync-log
timestamp: '<% tp.date.now("YYYY-MM-DDTHH:mm:ss") %>'
csv_source: "<% csvLabel.replace(/"/g, '\\"') %>"
brands_updated: <% updatedCount %>
files_renamed: <% renamedCount %>
multi_brand_skipped: <% skippedConflictCount %>
---

# MacroFactor Brand Sync Log (`<% logTitle %>`)

```text
<% summaryLine %>
```

- **CSV Source:** `<% csvLabel %>`
- **Unique Base Foods With Brands Found:** `<% brandCandidates.size %>`
- **Notes Enriched:** `<% updatedCount %>`
- **Notes Renamed:** `<% renamedCount %>`
- **Ambiguous Multi-Brand Notes Skipped:** `<% skippedConflictCount %>`

## Enriched & Renamed Foods (<% updatedNotes.length %>)
<%* if (updatedNotes.length === 0) { -%>
- *None*
<%* } else { updatedNotes.forEach((line) => { -%>
- <% line %>
<%* }); } -%>

## Ambiguous Multi-Brand Foods (Set `brand` Manually) (<% multiBrandConflicts.length %>)
<%* if (multiBrandConflicts.length === 0) { -%>
- *None*
<%* } else { multiBrandConflicts.forEach((c) => { -%>
- [[<% c.stem %>]] — Candidates: `<% c.brands %>`
<%* }); } -%>
