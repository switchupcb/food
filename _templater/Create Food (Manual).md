<%*
const OUTPUT_FOLDER = "1 - food-base";

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

// 1. Prompt for core food details
const foodName = await tp.system.prompt("Food Name (e.g., Homemade Chicken Salad)");
if (!foodName) {
  new Notice("Cancelled creating custom food.");
  return;
}

const brandRaw = await tp.system.prompt("Brand Name (optional — leave blank if generic/homemade)", "");
const brandClean = brandRaw ? brandRaw.replace(/[<>:"/\\|?*]+/g, "").trim() : "";

const servingUnit = await tp.system.prompt("Serving Unit (e.g., serving, g, cup, scoop, piece)", "serving");
const servingWeightRaw = await tp.system.prompt("Serving Weight in grams (optional)", "");
const caloriesRaw = await tp.system.prompt("Calories (kcal)", "0");
const proteinRaw = await tp.system.prompt("Protein (g)", "0");
const carbsRaw = await tp.system.prompt("Carbs (g)", "0");
const fatRaw = await tp.system.prompt("Fat (g)", "0");

const userStatus = await tp.system.suggester(
  ["staple", "favorite", "occasional", "avoid", "(leave blank)"],
  ["staple", "favorite", "occasional", "avoid", ""],
  false,
  "Select My Status (optional)"
);

// 2. Complete MacroFactor 56-nutrient groups (snake_case keys match Food Database.base 1:1)
const nutrientGroups = {
  label: [
    ["saturated_fat_g", "Saturated Fat (g)"],
    ["trans_fat_g", "Trans Fat (g)"],
    ["cholesterol_mg", "Cholesterol (mg)"],
    ["sodium_mg", "Sodium (mg)"],
    ["fiber_g", "Fiber (g)"],
    ["sugars_g", "Sugars (g)"],
    ["added_sugars_g", "Added Sugars (g)"],
    ["sugar_alcohols_g", "Sugar Alcohols (g)"],
    ["starch_g", "Starch (g)"],
    ["vitamin_d_mcg", "Vitamin D (mcg)"],
    ["calcium_mg", "Calcium (mg)"],
    ["iron_mg", "Iron (mg)"],
    ["potassium_mg", "Potassium (mg)"],
  ],
  fats: [
    ["monounsaturated_fat_g", "Monounsaturated Fat (g)"],
    ["polyunsaturated_fat_g", "Polyunsaturated Fat (g)"],
    ["omega_3_g", "Omega-3 Total (g)"],
    ["omega_3_ala_g", "Omega-3 ALA (g)"],
    ["omega_3_dha_g", "Omega-3 DHA (g)"],
    ["omega_3_epa_g", "Omega-3 EPA (g)"],
    ["omega_6_g", "Omega-6 (g)"],
  ],
  minerals: [
    ["magnesium_mg", "Magnesium (mg)"],
    ["phosphorus_mg", "Phosphorus (mg)"],
    ["zinc_mg", "Zinc (mg)"],
    ["copper_mg", "Copper (mg)"],
    ["manganese_mg", "Manganese (mg)"],
    ["selenium_mcg", "Selenium (mcg)"],
  ],
  vitamins: [
    ["vitamin_a_mcg", "Vitamin A (mcg)"],
    ["vitamin_c_mg", "Vitamin C (mg)"],
    ["vitamin_e_mg", "Vitamin E (mg)"],
    ["vitamin_k_mcg", "Vitamin K (mcg)"],
    ["b1_thiamine_mg", "B1 Thiamine (mg)"],
    ["b2_riboflavin_mg", "B2 Riboflavin (mg)"],
    ["b3_niacin_mg", "B3 Niacin (mg)"],
    ["b5_pantothenic_acid_mg", "B5 Pantothenic Acid (mg)"],
    ["b6_pyridoxine_mg", "B6 Pyridoxine (mg)"],
    ["b9_folate_mcg", "B9 Folate (mcg)"],
    ["b12_cobalamin_mcg", "B12 Cobalamin (mcg)"],
    ["choline_mg", "Choline (mg)"],
  ],
  amino_acids: [
    ["cysteine_g", "Cysteine (g)"],
    ["histidine_g", "Histidine (g)"],
    ["isoleucine_g", "Isoleucine (g)"],
    ["leucine_g", "Leucine (g)"],
    ["lysine_g", "Lysine (g)"],
    ["methionine_g", "Methionine (g)"],
    ["phenylalanine_g", "Phenylalanine (g)"],
    ["threonine_g", "Threonine (g)"],
    ["tryptophan_g", "Tryptophan (g)"],
    ["tyrosine_g", "Tyrosine (g)"],
    ["valine_g", "Valine (g)"],
  ],
  other: [
    ["water_g", "Water (g)"],
    ["caffeine_mg", "Caffeine (mg)"],
    ["alcohol_g", "Alcohol (g)"],
  ],
};

const numOrNull = (val) => {
  if (!val || val.trim() === "") return null;
  const parsed = parseFloat(val.trim());
  return Number.isFinite(parsed) ? parsed : null;
};

const collectedNutrients = new Map();

// 3. Optional category loop so you can enter any/all MacroFactor nutrients
while (true) {
  const choice = await tp.system.suggester(
    [
      "✅ Finish & Save Note",
      "🏷️ Standard Nutrition Label (Sat/Trans Fat, Chol, Sodium, Fiber, Sugars, Vit D, Ca, Fe, K)",
      "🥑 Detailed Fats & Omegas (Mono, Poly, Omega-3/ALA/DHA/EPA, Omega-6)",
      "🪨 Minerals (Mg, P, Zn, Cu, Mn, Se)",
      "💊 Vitamins & Choline (Vit A, C, E, K, B1–B12, Choline)",
      "🧬 Amino Acids (Leu, Ile, Val, Lys, Met, Cys, Phe, Tyr, Thr, Trp, His)",
      "☕ Other (Water, Caffeine, Alcohol)",
    ],
    ["done", "label", "fats", "minerals", "vitamins", "amino_acids", "other"],
    false,
    "Add optional MacroFactor nutrients? (Esc or Finish to save)"
  );

  if (!choice || choice === "done") break;

  for (const [key, label] of nutrientGroups[choice]) {
    const existing = collectedNutrients.has(key) ? String(collectedNutrients.get(key)) : "";
    const raw = await tp.system.prompt(`${label} (Enter to skip)`, existing);
    if (raw === null) break;
    const parsed = numOrNull(raw);
    if (parsed !== null) {
      collectedNutrients.set(key, parsed);
    } else {
      collectedNutrients.delete(key);
    }
  }
}

// 4. Sanitize filename and move note into food-base/
const baseFoodClean = foodName.replace(/[<>:"/\\|?*]+/g, "").trim();
const fullFoodName = brandClean && !/\s+by\s+/i.test(baseFoodClean)
  ? `${baseFoodClean} By ${brandClean}`
  : baseFoodClean;
const targetPath = `${OUTPUT_FOLDER}/${fullFoodName}`;
const targetStem = targetPath.split("/").pop().replace(/\.md$/i, "");
const foodId = await deterministicBase36Id("food", targetStem);
await tp.file.move(targetPath);

const weightG = numOrNull(servingWeightRaw);
const calories = numOrNull(caloriesRaw) ?? 0;
const protein = numOrNull(proteinRaw) ?? 0;
const carbs = numOrNull(carbsRaw) ?? 0;
const fat = numOrNull(fatRaw) ?? 0;
const discovered = tp.date.now("YYYY-MM-DDTHH:mm:ss");
-%>
---
title: "<% fullFoodName %>"
type: food
food_id: <% foodId %>
schema_version: 3
source: manual
version_status: latest
ban_status: unreviewed
<%* if (brandClean) { -%>
brand: "<% brandClean %>"
<%* } -%>
<%* if (userStatus) { -%>
status: <% userStatus %>
<%* } -%>
discovered: '<% discovered %>'
food_name: "<% fullFoodName %>"
serving_size: "<% servingUnit.trim() || 'serving' %>"
serving_qty: 1
<%* if (weightG !== null) { -%>
serving_weight_g: <% weightG %>
<%* } -%>
calories_kcal: <% calories %>
protein_g: <% protein %>
carbs_g: <% carbs %>
fat_g: <% fat %>
<%* for (const [key, val] of collectedNutrients) { -%>
<% key %>: <% val %>
<%* } -%>
aliases: []
ingredients: []
alternatives: []
tags: []
---

## Notes & Preparation
- 
