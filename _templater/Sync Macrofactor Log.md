<%*
// ============================================================================
// Sync Macrofactor Log.md — Native Obsidian JS Sync Engine (Desktop + Mobile)
// SCHEMA_VERSION = 3 (56 Nutrients, Alias-Aware Brand Matching, Algorithmic Alternatives)
// ============================================================================
const OUTPUT_FOLDER = "1 - food-base";
const SCHEMA_VERSION = 3;

const NUTRIENT_MAP = {
  "Calories (kcal)": "calories_kcal",
  "Fat (g)": "fat_g",
  "Carbs (g)": "carbs_g",
  "Protein (g)": "protein_g",
  "Saturated Fat (g)": "saturated_fat_g",
  "Trans Fat (g)": "trans_fat_g",
  "Monounsaturated Fat (g)": "monounsaturated_fat_g",
  "Polyunsaturated Fat (g)": "polyunsaturated_fat_g",
  "Cholesterol (mg)": "cholesterol_mg",
  "Sodium (mg)": "sodium_mg",
  "Fiber (g)": "fiber_g",
  "Sugars (g)": "sugars_g",
  "Sugars Added (g)": "added_sugars_g",
  "Sugar Alcohols (g)": "sugar_alcohols_g",
  "Starch (g)": "starch_g",
  "Vitamin A (mcg)": "vitamin_a_mcg",
  "Vitamin C (mg)": "vitamin_c_mg",
  "Vitamin D (mcg)": "vitamin_d_mcg",
  "Vitamin E (mg)": "vitamin_e_mg",
  "Vitamin K (mcg)": "vitamin_k_mcg",
  "B1, Thiamine (mg)": "b1_thiamine_mg",
  "B2, Riboflavin (mg)": "b2_riboflavin_mg",
  "B3, Niacin (mg)": "b3_niacin_mg",
  "B5, Pantothenic Acid (mg)": "b5_pantothenic_acid_mg",
  "B6, Pyridoxine (mg)": "b6_pyridoxine_mg",
  "B9, Folate (mcg)": "b9_folate_mcg",
  "Folate (mcg)": "b9_folate_mcg",
  "B12, Cobalamin (mcg)": "b12_cobalamin_mcg",
  "Choline (mg)": "choline_mg",
  "Calcium (mg)": "calcium_mg",
  "Iron (mg)": "iron_mg",
  "Magnesium (mg)": "magnesium_mg",
  "Phosphorus (mg)": "phosphorus_mg",
  "Potassium (mg)": "potassium_mg",
  "Zinc (mg)": "zinc_mg",
  "Copper (mg)": "copper_mg",
  "Manganese (mg)": "manganese_mg",
  "Selenium (mcg)": "selenium_mcg",
  "Omega-3 (g)": "omega_3_g",
  "Omega-3 ALA (g)": "omega_3_ala_g",
  "Omega-3 DHA (g)": "omega_3_dha_g",
  "Omega-3 EPA (g)": "omega_3_epa_g",
  "Omega-6 (g)": "omega_6_g",
  "Cysteine (g)": "cysteine_g",
  "Histidine (g)": "histidine_g",
  "Isoleucine (g)": "isoleucine_g",
  "Leucine (g)": "leucine_g",
  "Lysine (g)": "lysine_g",
  "Methionine (g)": "methionine_g",
  "Phenylalanine (g)": "phenylalanine_g",
  "Threonine (g)": "threonine_g",
  "Tryptophan (g)": "tryptophan_g",
  "Tyrosine (g)": "tyrosine_g",
  "Valine (g)": "valine_g",
  "Alcohol (g)": "alcohol_g",
  "Caffeine (mg)": "caffeine_mg",
  "Water (g)": "water_g",
};

const ROUND_DECIMALS = {
  calories_kcal: 2,
  fat_g: 2,
  carbs_g: 2,
  protein_g: 2,
  fiber_g: 2,
  sugars_g: 2,
  added_sugars_g: 2,
  sodium_mg: 2,
  potassium_mg: 2,
  calcium_mg: 2,
  iron_mg: 2,
  cholesterol_mg: 2,
};

const IGNORED_FOOD_PATTERNS = [
  /^quick\s*-?\s*add(\s+calories)?$/i,
  /^custom\s+calories$/i,
];

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

// 1. Locate MacroFactor CSV (Vault auto-detect + Native OS File Picker)
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

  const choice = await tp.system.suggester(options, values, false, "Select MacroFactor Food Log CSV to sync");
  if (!choice) return;

  if (choice === "BROWSE_NATIVE") {
    const picked = await pickNativeCsvFile();
    if (!picked) {
      new Notice("Sync cancelled.");
      return;
    }
    csvRaw = await picked.text();
    csvLabel = picked.name;
  } else {
    csvRaw = await app.vault.read(choice);
    csvLabel = choice.name;
  }
} else {
  new Notice("📂 Select your MacroFactor Food Log CSV export...");
  const picked = await pickNativeCsvFile();
  if (!picked) {
    new Notice("Sync cancelled (no CSV selected).");
    return;
  }
  csvRaw = await picked.text();
  csvLabel = picked.name;
}

new Notice(`⏳ Syncing ${csvLabel}...`);

// 2. RFC-4180 Compliant CSV Parser
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
      } else if (ch === "\r" && next === "\n") {
        row.push(field);
        rows.push(row);
        row = [];
        field = "";
        i++;
      } else if (ch === "\n" || ch === "\r") {
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

// 3. Normalization & Matching Helpers
function sanitizeFilename(name) {
  return name.replace(/[<>:"/\\|?*]+/g, "").replace(/\s+/g, " ").trim();
}

function stripVariantSuffix(name) {
  return name.replace(/__v_\d+$/i, "").trim();
}

function extractBrand(name) {
  const noVer = stripVariantSuffix(name);
  const m = noVer.match(/\s+by\s+(.+)$/i);
  return m ? m[1].trim() : "";
}

function canonicalKey(name) {
  const noVer = stripVariantSuffix(name);
  return sanitizeFilename(noVer).toLowerCase();
}

function parseFloatSafe(val) {
  if (val === null || val === undefined || val === "") return null;
  const n = Number(val);
  return Number.isFinite(n) ? n : null;
}

function isValidWeight(weightG, unit) {
  if (weightG === null || weightG <= 0) return false;
  const u = unit.toLowerCase();
  if (weightG < 1.0 && !["g", "gram", "grams", "mg", "mcg"].includes(u)) {
    return false;
  }
  return true;
}

function roundNutrient(key, val) {
  const dec = ROUND_DECIMALS[key] ?? 4;
  const factor = Math.pow(10, dec);
  return Math.round(val * factor) / factor;
}

function nutrientsMatch(a, b, keys, relTol, absTol) {
  for (const k of keys) {
    const va = Number(a[k] ?? 0);
    const vb = Number(b[k] ?? 0);
    const diff = Math.abs(va - vb);
    const allowed = Math.max(absTol, relTol * Math.max(Math.abs(va), Math.abs(vb)));
    if (diff > allowed) return false;
  }
  return true;
}

function buildDiffReason(existing, incoming, keys) {
  const diffs = [];
  for (const k of keys) {
    const va = Number(existing[k] ?? 0);
    const vb = Number(incoming[k] ?? 0);
    const diff = Math.abs(va - vb);
    if (diff > Math.max(0.05, 0.02 * Math.max(Math.abs(va), Math.abs(vb)))) {
      diffs.push(`${k}: ${va} -> ${vb}`);
    }
  }
  return diffs.slice(0, 6).join(", ") || "Macro variation";
}

function extractWikiTarget(raw) {
  if (!raw) return "";
  const s = String(raw).trim();
  const m = s.match(/^\[\[([^\]|#]+)/);
  return m ? m[1].trim() : s;
}

// 4. Parse CSV & Group by (canonical_key, serving_size)
const { headers, records } = parseCSV(csvRaw);
const csvNutrientKeys = [...new Set(
  Object.entries(NUTRIENT_MAP)
    .filter(([csvCol]) => headers.includes(csvCol))
    .map(([, yamlKey]) => yamlKey)
)];

if (!app.vault.getAbstractFileByPath(OUTPUT_FOLDER)) {
  await app.vault.createFolder(OUTPUT_FOLDER);
}

const groupedRows = new Map();
for (const row of records) {
  const rawName = (row["Food Name"] || "").trim();
  if (!rawName) continue;
  if (IGNORED_FOOD_PATTERNS.some((rx) => rx.test(rawName))) continue;

  const qty = parseFloatSafe(row["Serving Qty"]);
  if (!qty || qty <= 0) continue;

  const unit = (row["Serving Size"] || "serving").trim();
  const cKey = canonicalKey(rawName);
  const groupId = `${cKey}|||${unit.toLowerCase()}`;

  const rawWeight = parseFloatSafe(row["Serving Weight (g)"]);
  const normWeight = isValidWeight(rawWeight, unit) ? roundNutrient("serving_weight_g", rawWeight / qty) : null;

  const normalized = {};
  for (const [csvCol, yamlKey] of Object.entries(NUTRIENT_MAP)) {
    if (!headers.includes(csvCol)) continue;
    const rawNum = parseFloatSafe(row[csvCol]);
    normalized[yamlKey] = rawNum !== null ? roundNutrient(yamlKey, rawNum / qty) : 0;
  }

  const entry = {
    rawName: stripVariantSuffix(rawName),
    cKey,
    unit,
    normWeight,
    exactUnitSource: Math.abs(qty - 1.0) < 1e-6,
    date: row["Date"] || "",
    nutrients: normalized,
  };

  if (!groupedRows.has(groupId)) groupedRows.set(groupId, []);
  groupedRows.get(groupId).push(entry);
}

const targetVariants = [];
for (const rows of groupedRows.values()) {
  rows.sort((a, b) => (b.exactUnitSource ? 1 : 0) - (a.exactUnitSource ? 1 : 0));
  const variants = [];

  for (const r of rows) {
    const relTol = r.exactUnitSource ? 0.02 : 0.06;
    const absTol = r.exactUnitSource ? 0.05 : 0.85;
    const match = variants.find((v) =>
      nutrientsMatch(v.nutrients, r.nutrients, csvNutrientKeys, relTol, absTol)
    );

    if (match) {
      if (r.rawName !== match.food_name && !match.aliases.includes(r.rawName)) {
        match.aliases.push(r.rawName);
      }
      if (r.exactUnitSource && !match.exactUnitSource) {
        match.nutrients = r.nutrients;
        match.exactUnitSource = true;
        if (r.normWeight !== null) match.normWeight = r.normWeight;
      }
    } else {
      variants.push({
        cKey: r.cKey,
        food_name: r.rawName,
        unit: r.unit,
        normWeight: r.normWeight,
        exactUnitSource: r.exactUnitSource,
        nutrients: r.nutrients,
        aliases: [],
      });
    }
  }

  variants.forEach((v, idx) => {
    v.variantIndex = idx + 1;
    v.isLatest = idx === variants.length - 1;
    targetVariants.push(v);
  });
}

// 5. Index Existing Markdown Notes in food-base/ (By Stem AND Alias+Unit)
const existingFiles = app.vault.getMarkdownFiles().filter((f) => f.path.startsWith(`${OUTPUT_FOLDER}/`));
const existingByStem = new Map();
const existingByAliasAndUnit = new Map();

for (const f of existingFiles) {
  const cache = app.metadataCache.getFileCache(f);
  const fm = { ...(cache?.frontmatter || {}) };
  const record = { file: f, fm };
  existingByStem.set(f.basename, record);

  const unitKey = String(fm.serving_size || "serving").trim().toLowerCase();
  const namesToIndex = [
    fm.food_name,
    f.basename,
    ...(Array.isArray(fm.aliases) ? fm.aliases : []),
  ].filter(Boolean);

  for (const n of namesToIndex) {
    const lookup = `${canonicalKey(String(n))}|||${unitKey}`;
    if (!existingByAliasAndUnit.has(lookup)) {
      existingByAliasAndUnit.set(lookup, record);
    }
  }
}

let stats = { synced: 0, added: 0, unlogged: 0, errors: 0 };
const debugLog = {
  added: [],
  needsReview: [],
  unlogged: [],
};

const matchedStems = new Set();
const nowIso = new Date().toISOString().slice(0, 19);

// 5B. Execute User Declarative Controls (duplicate_of, set_as_unique, set_as_only_version)
let controlsExecuted = false;

for (const [stem, item] of existingByStem.entries()) {
  const fm = item.fm;
  if (String(fm.source || "").toLowerCase() === "manual") continue;

  // 1) duplicate_of: Merge food_name & aliases into target note, then delete duplicate
  if (fm.duplicate_of) {
    const targetStem = extractWikiTarget(fm.duplicate_of);
    const targetItem = existingByStem.get(targetStem);
    if (targetItem && targetStem !== stem) {
      await app.fileManager.processFrontMatter(targetItem.file, (tfm) => {
        const aliases = Array.isArray(tfm.aliases) ? [...tfm.aliases] : [];
        const toMerge = [fm.food_name, ...(Array.isArray(fm.aliases) ? fm.aliases : [])].filter(Boolean);
        for (const name of toMerge) {
          if (name !== tfm.food_name && !aliases.includes(name)) aliases.push(name);
        }
        if (aliases.length > 0) tfm.aliases = aliases;
      });
      await app.vault.trash(item.file, true);
      controlsExecuted = true;
      continue;
    }
  }

  // 2) set_as_unique: Fork variant into standalone food, keep raw CSV food_name in aliases
  if (fm.set_as_unique && String(fm.set_as_unique).trim() !== "") {
    const uniqueName = sanitizeFilename(String(fm.set_as_unique).trim());
    const unit = String(fm.serving_size || "serving").trim();
    const unitSuffix = unit.toLowerCase() === "serving" ? "" : ` (${sanitizeFilename(unit)})`;
    const newStem = `${uniqueName}${unitSuffix}`;
    const newPath = `${OUTPUT_FOLDER}/${newStem}.md`;

    if (newStem !== stem && !app.vault.getAbstractFileByPath(newPath)) {
      const oldCsvName = fm.food_name;
      await app.fileManager.processFrontMatter(item.file, (ufm) => {
        ufm.title = newStem;
        ufm.food_name = uniqueName;
        ufm.version_status = "latest";
        ufm.needs_review = false;
        delete ufm.review_reason;
        delete ufm.previous_version;
        delete ufm.set_as_unique;
        const aliases = Array.isArray(ufm.aliases) ? [...ufm.aliases] : [];
        if (oldCsvName && !aliases.includes(oldCsvName)) aliases.push(oldCsvName);
        if (aliases.length > 0) ufm.aliases = aliases;
      });
      await app.fileManager.renameFile(item.file, newPath);
      controlsExecuted = true;
      continue;
    }
  }

  // 3) set_as_only_version: Collapse all other versions of this (food, unit), promote to clean base stem
  if (fm.set_as_only_version === true) {
    const unit = String(fm.serving_size || "serving").trim();
    const unitSuffix = unit.toLowerCase() === "serving" ? "" : ` (${sanitizeFilename(unit)})`;
    const baseFoodClean = sanitizeFilename(String(fm.food_name || stem).replace(/__v_\d+$/i, ""));
    const cleanStem = `${baseFoodClean}${unitSuffix}`;
    const cKey = canonicalKey(baseFoodClean);

    // Trash all sibling variants in the same (canonical_key, unit) group
    for (const [otherStem, otherItem] of existingByStem.entries()) {
      if (otherStem === stem) continue;
      const otherUnit = String(otherItem.fm.serving_size || "serving").trim().toLowerCase();
      const otherKey = canonicalKey(String(otherItem.fm.food_name || otherStem));
      if (otherKey === cKey && otherUnit === unit.toLowerCase()) {
        await app.vault.trash(otherItem.file, true);
      }
    }

    await app.fileManager.processFrontMatter(item.file, (ofm) => {
      ofm.title = cleanStem;
      ofm.version_status = "latest";
      ofm.set_as_final_version = true;
      ofm.set_as_only_version = true;
      ofm.needs_review = false;
      delete ofm.review_reason;
      delete ofm.previous_version;
    });

    const cleanPath = `${OUTPUT_FOLDER}/${cleanStem}.md`;
    if (stem !== cleanStem && !app.vault.getAbstractFileByPath(cleanPath)) {
      await app.fileManager.renameFile(item.file, cleanPath);
    }
    controlsExecuted = true;
  }
}

// Re-index if any files were trashed or renamed by declarative controls
if (controlsExecuted) {
  existingByStem.clear();
  existingByAliasAndUnit.clear();
  const updatedList = app.vault.getMarkdownFiles().filter((f) => f.path.startsWith(`${OUTPUT_FOLDER}/`));
  for (const f of updatedList) {
    const cache = app.metadataCache.getFileCache(f);
    const fm = { ...(cache?.frontmatter || {}) };
    const record = { file: f, fm };
    existingByStem.set(f.basename, record);

    const unitKey = String(fm.serving_size || "serving").trim().toLowerCase();
    const namesToIndex = [
      fm.food_name,
      f.basename,
      ...(Array.isArray(fm.aliases) ? fm.aliases : []),
    ].filter(Boolean);

    for (const n of namesToIndex) {
      const lookup = `${canonicalKey(String(n))}|||${unitKey}`;
      if (!existingByAliasAndUnit.has(lookup)) {
        existingByAliasAndUnit.set(lookup, record);
      }
    }
  }
}

// 6. Upsert Variants Idempotently
for (const v of targetVariants) {
  const baseClean = sanitizeFilename(v.food_name);
  const unitSuffix = v.unit.toLowerCase() === "serving" ? "" : ` (${sanitizeFilename(v.unit)})`;
  const verSuffix = v.variantIndex > 1 ? `__v_${v.variantIndex}` : "";
  const defaultStem = `${baseClean}${unitSuffix}${verSuffix}`;

  const aliasLookup = `${v.cKey}|||${v.unit.toLowerCase()}`;
  const existing = existingByStem.get(defaultStem) || (v.variantIndex === 1 ? existingByAliasAndUnit.get(aliasLookup) : null);
  const activeStem = existing ? existing.file.basename : defaultStem;
  const filePath = `${OUTPUT_FOLDER}/${activeStem}.md`;

  matchedStems.add(activeStem);
  const detectedBrand = extractBrand(v.food_name);

  if (!existing) {
	const createdFile = await app.vault.create(filePath, "---\n---\n");
	const resolvedFoodId = await deterministicBase36Id("food", createdFile.basename);

	await app.fileManager.processFrontMatter(createdFile, (fm) => {
	  fm.type = "food";
	  fm.food_id = resolvedFoodId;
	  fm.title = createdFile.basename;
      fm.schema_version = SCHEMA_VERSION;
      fm.source = "macrofactor";
      fm.food_name = v.food_name;
      if (detectedBrand) fm.brand = detectedBrand;
      fm.serving_size = v.unit;
      fm.serving_qty = 1;
      if (v.normWeight !== null) fm.serving_weight_g = v.normWeight;
      fm.exact_unit_source = v.exactUnitSource;
      fm.version_status = v.isLatest ? "latest" : "previous";
      fm.discovered = nowIso;
      fm.ban_status = "unreviewed";
      fm.needs_review = v.variantIndex > 1;

      if (v.variantIndex > 1) {
        const prevStem = `${baseClean}${unitSuffix}${v.variantIndex > 2 ? `__v_${v.variantIndex - 1}` : ""}`;
        fm.previous_version = `[[${prevStem}]]`;
        const prevItem = existingByStem.get(prevStem);
        if (prevItem) {
          fm.review_reason = buildDiffReason(prevItem.fm, v.nutrients, csvNutrientKeys);
        }
      }
      if (v.aliases.length > 0) {
        fm.aliases = [...v.aliases];
      }
      for (const [k, val] of Object.entries(v.nutrients)) {
        fm[k] = val;
      }
    });
    stats.added++;
    debugLog.added.push(activeStem);
    if (v.variantIndex > 1) debugLog.needsReview.push(activeStem);
  } else {
    const isManual = String(existing.fm.source || "").toLowerCase() === "manual";
    const resolvedFoodId = existing.fm?.food_id || (await deterministicBase36Id("food", existing.file.basename));
    
	await app.fileManager.processFrontMatter(existing.file, (fm) => {
	  fm.food_id = resolvedFoodId;

      fm.schema_version = SCHEMA_VERSION;
      if (!fm.ban_status) fm.ban_status = "unreviewed";
      if (detectedBrand && !fm.brand) fm.brand = detectedBrand;
      if (isManual) return;

      fm.source = "macrofactor";
      fm.food_name = v.food_name;
      fm.serving_size = v.unit;
      fm.serving_qty = 1;
      if (v.normWeight !== null) fm.serving_weight_g = v.normWeight;
      fm.exact_unit_source = v.exactUnitSource;

      if (!fm.set_as_final_version) {
        fm.version_status = v.isLatest ? "latest" : "previous";
      }
      if (fm.reviewed === true) {
        fm.needs_review = false;
      }

      const curAliases = Array.isArray(fm.aliases) ? [...fm.aliases] : [];
      for (const a of v.aliases) {
        if (!curAliases.includes(a)) curAliases.push(a);
      }
      if (curAliases.length > 0) fm.aliases = curAliases;

      if (!fm.set_as_final_version) {
        for (const [k, val] of Object.entries(v.nutrients)) {
          fm[k] = val;
        }
      }
    });
    stats.synced++;
  }
}

// Mark unlogged macrofactor notes not present in this CSV
for (const [stem, item] of existingByStem.entries()) {
  if (matchedStems.has(stem)) continue;
  if (String(item.fm.source || "").toLowerCase() !== "macrofactor") continue;
  if (item.fm.version_status !== "unlogged") {
    await app.fileManager.processFrontMatter(item.file, (fm) => {
      fm.version_status = "unlogged";
    });
    stats.unlogged++;
    debugLog.unlogged.push(stem);
  }
}

// 7A. Recursive 4-State Ingredient Ban Propagation (unreviewed | allowed | banned | override)
const refreshedFiles = app.vault.getMarkdownFiles().filter((f) => f.path.startsWith(`${OUTPUT_FOLDER}/`));
const graph = new Map();
for (const f of refreshedFiles) {
  const cache = app.metadataCache.getFileCache(f);
  const fm = cache?.frontmatter || {};
  const ings = Array.isArray(fm.ingredients)
    ? fm.ingredients.map(extractWikiTarget).filter(Boolean)
    : [];
  graph.set(f.basename, {
    file: f,
    ban_status: String(fm.ban_status || "unreviewed").trim().toLowerCase(),
    ban_reason: fm.ban_reason ? String(fm.ban_reason).trim() : "",
    ban_status_prev: fm.ban_status_prev ? String(fm.ban_status_prev).trim().toLowerCase() : null,
    ingredients: ings,
  });
}

function findBannedAncestor(stem, visited = new Set()) {
  if (visited.has(stem)) return null;
  visited.add(stem);
  const node = graph.get(stem);
  if (!node) return null;

  for (const ingStem of node.ingredients) {
    const ingNode = graph.get(ingStem);
    if (!ingNode) continue;
    if (ingNode.ban_status === "banned") return ingStem;
    const deeper = findBannedAncestor(ingStem, visited);
    if (deeper) return deeper;
  }
  return null;
}

for (const [stem, node] of graph.entries()) {
  const isAutoReason = node.ban_reason.startsWith("Contains [[") || node.ban_reason.startsWith("Overrides [[");
  const bannedIng = findBannedAncestor(stem, new Set());

  if (bannedIng) {
    if (node.ban_status === "override" || (node.ban_status === "allowed" && isAutoReason)) {
      const expected = `Overrides [[${bannedIng}]]`;
      if (node.ban_status !== "override" || node.ban_reason !== expected) {
        await app.fileManager.processFrontMatter(node.file, (fm) => {
          fm.ban_status = "override";
          fm.ban_reason = expected;
        });
      }
      continue;
    }

    const expected = `Contains [[${bannedIng}]]`;
    const needReason = (!node.ban_reason || isAutoReason) && node.ban_reason !== expected;
    if (node.ban_status !== "banned" || needReason || !node.ban_status_prev) {
      await app.fileManager.processFrontMatter(node.file, (fm) => {
        if (!fm.ban_status_prev) fm.ban_status_prev = node.ban_status;
        fm.ban_status = "banned";
        if (needReason) fm.ban_reason = expected;
      });
    }
  } else {
    if (node.ban_status === "override") {
      await app.fileManager.processFrontMatter(node.file, (fm) => {
        fm.ban_status = "allowed";
        delete fm.ban_status_prev;
        if (isAutoReason) delete fm.ban_reason;
      });
    } else if (node.ban_status === "banned" && (isAutoReason || node.ban_status_prev)) {
      const restored = ["allowed", "banned", "unreviewed"].includes(node.ban_status_prev)
        ? node.ban_status_prev
        : "unreviewed";
      await app.fileManager.processFrontMatter(node.file, (fm) => {
        fm.ban_status = restored;
        delete fm.ban_status_prev;
        if (isAutoReason) delete fm.ban_reason;
      });
    }
  }
}

// 7B. Algorithmic Alternatives (100% Ordered Ingredients + Matching Unit & Macros)
const MACRO_COMPARE_KEYS = [
  "calories_kcal",
  "protein_g",
  "carbs_g",
  "fat_g",
  "fiber_g",
  "sodium_mg",
];

const altCandidates = [];
for (const f of refreshedFiles) {
  const cache = app.metadataCache.getFileCache(f);
  const fm = cache?.frontmatter || {};
  const rawIngs = Array.isArray(fm.ingredients)
    ? fm.ingredients.map((i) => extractWikiTarget(i).toLowerCase()).filter(Boolean)
    : [];

  altCandidates.push({
    file: f,
    stem: f.basename,
    unit: String(fm.serving_size || "serving").trim().toLowerCase(),
    ingredients: rawIngs,
    ingSignature: rawIngs.join(" -> "),
    nutrients: fm,
    existingAlts: Array.isArray(fm.algorithmic_alternatives) ? fm.algorithmic_alternatives : [],
  });
}

for (const item of altCandidates) {
  let matchedLinks = [];

  if (item.ingredients.length > 0) {
    matchedLinks = altCandidates
      .filter((other) => {
        if (other.stem === item.stem) return false;
        if (other.ingredients.length === 0) return false;
        if (other.unit !== item.unit) return false;
        if (other.ingSignature !== item.ingSignature) return false;
        return nutrientsMatch(item.nutrients, other.nutrients, MACRO_COMPARE_KEYS, 0.02, 0.05);
      })
      .map((other) => `[[${other.stem}]]`)
      .sort();
  }

  const prevSorted = [...item.existingAlts].map(String).sort();
  const changed =
    matchedLinks.length !== prevSorted.length ||
    matchedLinks.some((val, idx) => val !== prevSorted[idx]);

  if (changed) {
    await app.fileManager.processFrontMatter(item.file, (fm) => {
      if (matchedLinks.length > 0) {
        fm.algorithmic_alternatives = matchedLinks;
      } else {
        delete fm.algorithmic_alternatives;
      }
    });
  }
}

// 8. Move & format the created note into _app/_logs/log-<timestamp>.md
const LOG_FOLDER = "_app/_logs";
if (!app.vault.getAbstractFileByPath("_app")) {
  await app.vault.createFolder("_app");
}
if (!app.vault.getAbstractFileByPath(LOG_FOLDER)) {
  await app.vault.createFolder(LOG_FOLDER);
}

const logStamp = tp.date.now("YYYY-MM-DD-HHmmss");
const logTitle = `log-${logStamp}`;
await tp.file.move(`${LOG_FOLDER}/${logTitle}`);

const summaryLine = `[${OUTPUT_FOLDER}] Synced: ${stats.synced} | Added: ${stats.added} | Unlogged: ${stats.unlogged} | Errors: ${stats.errors}`;
new Notice(`✅ ${summaryLine}`);
-%>
---
type: sync-log
timestamp: '<% tp.date.now("YYYY-MM-DDTHH:mm:ss") %>'
schema_version: <% SCHEMA_VERSION %>
csv_source: "<% csvLabel.replace(/"/g, '\\"') %>"
total_csv_rows: <% records.length %>
unique_variants_processed: <% targetVariants.length %>
synced: <% stats.synced %>
added: <% stats.added %>
unlogged: <% stats.unlogged %>
errors: <% stats.errors %>
---

# MacroFactor Sync Log (`<% logTitle %>`)

```text
<% summaryLine %>
```

- **CSV Source:** `<% csvLabel %>`
- **CSV Rows Parsed:** `<% records.length %>`
- **Normalized Food Variants:** `<% targetVariants.length %>`
- **Detected Nutrient Columns:** `<% csvNutrientKeys.length %>`

## Added Notes (<% debugLog.added.length %>)
<%* if (debugLog.added.length === 0) { -%>
- *None*
<%* } else { debugLog.added.forEach((item) => { -%>
- [[<% item %>]]
<%* }); } -%>

## Needs Review (<% debugLog.needsReview.length %>)
<%* if (debugLog.needsReview.length === 0) { -%>
- *None*
<%* } else { debugLog.needsReview.forEach((item) => { -%>
- [[<% item %>]]
<%* }); } -%>

## Marked Unlogged (<% debugLog.unlogged.length %>)
<%* if (debugLog.unlogged.length === 0) { -%>
- *None*
<%* } else { debugLog.unlogged.forEach((item) => { -%>
- [[<% item %>]]
<%* }); } -%>
