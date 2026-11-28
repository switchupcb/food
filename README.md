# Food Base (`Sync Macrofactor Log.md`)

**Your personal food database in an Obsidian Vault.**

| Module              | What You Can Do                                                                                                                          | Where Is It?                                                         |
| :------------------ | :--------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------- |
| **Food Base**       | Synchronize your MacroFactor food log with Obsidian notes/bases, recursively manage ingredients, and query foods.                        | ✅ Core Templater commands (`Sync Log`, `Sync Brands`, `Create Food`) |
| **Food Base Diet**  | Manage your diets' foods, macronutrient, and micronutrient targets.                                                                      | Starter Kit                                                          |
| **Food Base Bank**  | Manage your food as an asset, your food cost, and your food storage locations.                                                           | Starter Kit                                                          |
| **Food Base Route** | Generate food-asset restock-routes optimized to save you energy, time, money, or any other customized cost-value when you shop for food. | Starter Kit                                                          |

_Food Base doesn't require AI yet structures all the information your AI assistant needs for even more food workflows!_

![Spreadsheet with Obsidian Base Views and Food Macronutrients, Micronutrients, and Minerals](/preview/food-database-preview.png)

---

You can get started by running the Obsidian `templater` files at [`/_templater/`](/_templater/).

> **Where is the plug-and-play Obsidian Vault?**  
> You get the Starter Kit at **[SwitchUpCB (Food)](https://switchupcb.com/food/checkout)**.
>
> This kit includes
> - **SETUP GUIDE.md** which saves you time setting up your personal food database.
> - **Pre-Configured Obsidian Vault (40+ files)**: Ready to open on Desktop, iOS, and Android with plugins pre-installed and configured.
> - **All Template Commands (Mobile/Desktop Supported)** used to synchronize your MacroFactor CSV data on a phone or computer.
>   - `Sync All` modules with a single command, 
>   - `Generate Restock Routes`, 
>   - `Log Bank Action`,
>   - `Manage Diets`, `Food (Manual)`, `Diet (Manual, RDAs)`,
>   - and more.
> - **All Database Views** used to manage the
>   - `Food Database.base`
>   - `Food Diet Database.base`
>   - `Food Bank Database.base`
>   - `Food Route Database.base`
> **56-nutrient formulas**
>   - `_template.base` food query saves you time creating food queries.
>   - `.base` views contain 56-nutrient formulas with custom serving quantity scaling.
> - **`properties.md`** frontmatter autofill-configuration file for property-value autocompletion in every `.md` and `.base` file.

![Dropdown with Obisidian Template Options](/preview/food-database-mobile_sync-preview.png)

## Table of Contents

| Section                                                                                                                                                          | Description                                                                                                                      |
| :--------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------- |
| **[What does Food Base (`Sync Macrofactor Log.md`) do?](#what-does-food-base-do)**                                                                               | Overview of MacroFactor food log synchronization, Obsidian Bases food queries, ingredient auto-banning, and diet protocols.      |
| **[Quickstart](#quickstart-how-do-you-set-up-food-base)**                                                                                                        | 3-step setup guide for installing dependencies, exporting your food log from Macrofactor, and running `Sync Macrofactor Log.md`. |
| **[FAQ: How do you resolve foods with the same name, but different macronutrients?](#how-do-you-resolve-foods-with-the-same-name-but-different-macronutrients)** | Frontmatter controls (`reviewed`, `set_as_final_version`, `set_as_only_version`, `set_as_unique`, `duplicate_of`).               |
| **[LICENSE](#license)**                                                                                                                                          | MIT open-source licensing and contribution guidelines.                                                                           |




## What does Food Base (`Sync Macrofactor Log.md`) do?

**MacroFactor Synchronization**
- Parses `MacroFactor-*.csv` exports into normalized `1x serving` Markdown notes inside `./food-base`. 
- Deduplicates brand suffixes into `aliases`, separates conflicting units (`cup` vs `g`), and reconciles macro mismatches deterministically without overwriting your personal notes.

**Food Queries (Obsidian Bases)** 
- Designed for native Obsidian Bases—dynamically scales `1g`/`1ml` items to `100g` (or any `custom_qty`) across all 42+ macros and micronutrients.
- Pairs with pre-filtered query templates for situational meal selection.

**Ingredient Management (4-State Auto-Ban)** 
- Audit foods as `unreviewed`, `allowed`, `banned`, or `override`. 
- Linking `[[Ingredients]]` in YAML automatically propagates `banned` status and `ban_reason: "Contains [[Ingredient]]"` across every parent food containing a blocked ingredient—and cleanly restores prior status if unbanned.

## Quickstart (How do you set up Food Base?)

### 1. Add Templates to Your Obsidian Vault

1. Create an Obsidian vault (`v1.9+`).
2. Install the community plugin [**Templater**](https://silentvoid13.github.io/Templater/) and enable it.
3. Copy the template files from [`/_templater/`](/_templater/) into your vault's Templater folder (e.g., `/_templater/`):
   - `Sync Macrofactor Log.md`
   - `Sync Macrofactor Brands.md`
   - `Create Food (Manual).md`

### 2. Export Your MacroFactor Food Log

1. Open the **MacroFactor** app.
2. Go to **More → Data Management (Data Export) → Granular Export → Logs (Food Log) → select `All Time` → click `Export Food Log`**.
3. Save the `.csv` file anywhere on your phone or computer.

### 3. Sync Your Foods & Brands in Obsidian

1. Open Obsidian's Command Palette (`Ctrl/Cmd + P` on desktop, or `≡ → >_ Open command palette` on mobile).
2. Run **`Templater: Create new note from template` → `Sync Macrofactor Log`** and select your exported `.csv` file.
3. Run **`Templater: Create new note from template` → `Sync Macrofactor Brands`** to attach brand metadata to your foods
4. You can use **`Create Food (Manual)`** to add custom foods and foods as ingredients by hand.

## FAQ

### How do you resolve foods with the same name, but different macronutrients?

`Sync Macrofactor Log.md` flags same `(food, unit)` with different nutrition numbers with  (`needs_review: true`) and an exact `review_reason` diff when MacroFactor logs the same `(food, unit)` with different nutrition numbers.

![](/preview/food-database-sndm-resolution-preview.png)

Here is how to resolve these foods using the Frontmatter/Obsidian Base table.

| Property                     | Type     | Effect on Next Sync                                                                                                                                         |
| :--------------------------- | :------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reviewed: true`             | Checkbox | Check to dismiss the warning and keep both `previous` and `latest` versions.                                                                                |
| `set_as_final_version: true` | Checkbox | Check to set the note's macros as `latest` and stop creating versions of this food during CSV synchronization.                                              |
| `set_as_only_version: true`  | Checkbox | Check to move the macros of this onto a clean base filename, delete all other versions, and stop creating versions of this food during CSV synchronization. |
| `set_as_unique: "New Name"`  | Text     | Check to split the food variation into a unique food while preserving the original food name (from the CSV) in frontmatter property `aliases`.              |
| `duplicate_of: "[[Target]]"` | Link     | Set to merge the note's `food_name` into the target's `aliases` frontmatter property and remove the duplicate food during the next CSV synchronization.     |

---

## LICENSE

[MIT License - Copyright (c) 2026 SwitchUpCB](/LICENSE)

_PRs for Cronometer, MyFitnessPal, and other food-tracking adapters are accepted._
