# NIC BoQ / MEP Estimation System — Architecture (as built)

**App:** `nic_addon` · module **NIC Custom App**
**Source analysed:** `BQ_Eproc_MEP_Proyek_Pondok_Pesantren_Al-Khoziny_Sidoarjo_R01.xlsx`
**Scope of this doc:** the estimation lifecycle actually implemented — master unit-rate library → priced BoQ → project budget (RAPP). Execution (award → Sales Order) is on the roadmap (§10).

> This document reflects the **real DocTypes and formulas in the codebase**, verified to the rupiah against the source spreadsheet (§9).

---

## 1. The core idea

A 1,000-line project is 90% **shared master data**, not project data. Separate the two and each BoQ line becomes a *reference* to a library, not a fat record.

Two reframes drive the whole design:

1. **"Analisa" is an AHSP (reusable unit-rate build-up), not a BoQ concept.** It lives in the master library as **`Work Analysis`**.
2. **A project is one thing with many disciplines**, not many projects. Disciplines (Elektrikal / Pemadam / Plumbing / …) vary per project (the client bids different tenders) so they are their own master DocType, **`Discipline`**, scoped per project — and each becomes one Sales Order line at award.

### The calculation chain (confirmed from the file)

| Layer | Excel | Becomes | Produces |
|---|---|---|---|
| 1 | `PRICE LIST` | `Item` + `Item Price` (native) | raw supplier prices |
| 2 | `Analisa-1` / `Analisa-2` | **`Work Analysis`** (Simple / Composite) | net unit rate (material + jasa) |
| 3 | `EL_*`, `FF_*`, `PL_*` sheets | **`BOQ Section`** + **`Boq Item`** | priced lines (net → margin → sell) |
| 4 | margin table `N2:W4` | **`Margin Profile`** | material/labor margin per category |
| 5 | `Direct Cost` | **`Direct Cost`** | 4 overhead group subtotals (APP.2) |
| 6 | `RAPP` | **`BoQ`** (+ `BoQ Recap`) | APP.1/2/3, profit, offer + PPN |

**The single most important formula** — margin-on-selling-price, replicated exactly:

```
sell_rate = ROUNDUP( net_rate / (1 - margin) )     ← NOT a cost markup
```

---

## 2. Three layers, three lifetimes

```
MASTER LIBRARY  (shared, lives forever)
   Item, Item Price (native) · Work Analysis (+ Component)
   Margin Profile (+ Component) · Discipline · BoQ Settings

ESTIMATION      (per project + revision)
   BOQ Section (+ Boq Item) · Direct Cost (+ Line) · BoQ (+ BoQ Recap)

EXECUTION       (native ERPNext — roadmap §10)
   Quotation / Sales Order · Project · Sales Invoice (progress billing)
```

Rule that ties them: **estimation references the library while in Draft, and snapshots net rates onto each `Boq Item` on save/submit.** Master prices keep moving for future tenders; the awarded BoQ never changes underneath you (§6).

---

## 3. DocType catalog (as implemented)

### 3.1 Master library

#### `Item` / `Item Price` (native — reused)
Every material and service line, and its supplier prices. `Item Price` uses native `valid_from` / `valid_upto` / `supplier` / `buying`. A whitelisted helper `work_analysis.get_item_price(item_code, posting_date)` picks the **latest buying price valid on the posting date** (largest `valid_from ≤ posting_date`, not past `valid_upto`).

#### `Work Analysis` ⭐ (submittable) — the AHSP library
One record = one analysed unit rate. Two shapes:

- **Simple** (was Analisa-1): one item priced **in the header** — `item_code`, `material_rate`, `material_percentage`, `labor_rate`, `labor_percentage`. 1 item = 1 record (light to open/save, flows cleanly to BoQ). The component table is hidden.
- **Composite** (was Analisa-2): an assembly keyed by `analysis_code` (a **non-stock** Item) with a `components` child table.

| Field | Notes |
|---|---|
| project, posting_date | posting_date drives the price fetch |
| analysis_type | `Simple` / `Composite` |
| analysis_code | Composite only · Link Item (non-stock) · the assembly's identity |
| item_code | Simple only · Link Item · the single analysed item |
| material_rate, material_percentage | Simple · rate auto-fetched from Item Price by posting_date |
| labor_rate, labor_percentage | Simple |
| item_price, item_price_rate | Simple · the resolved Item Price |
| alias | rename to match the customer BoQ wording |
| uom | fetched from the item's stock_uom |
| components | Composite · Table → `Work Analysis Component` |
| **out_material_rate / out_labor_rate / out_total_rate** | read-only, computed (§4) — the net unit rate consumed by BoQ |

**Validations:** Composite `analysis_code` must be a non-stock Item **and** must not appear among its own components (no self-reference).

`Work Analysis Component` (child, Composite only):
`item_code, item_name, brand, alias, qty, uom, material_rate, material_percentage, item_price, item_price_rate, labor_rate, labor_percentage, amount_material, amount_labor`. Each ingredient row is `qty × rate`; percentage rows ("Waste 2%") add `% × subtotal`.

#### `Margin Profile` (submittable) — the `N2:W4` lookup
`is_active`, `project`, `component` (Table). The BoQ engine auto-resolves the **active** profile (project match → project-less → any).

`Margin Profile Component` (child): `kode` (`Material` / `Upah`), `number` (category code 1–10), `percentage`, `label`.

#### `Discipline` (master) — the per-project work package
`discipline_name`, `project` (**mandatory**), `item` (non-stock Item — the future Sales Order line), `is_active`, `description`. A discipline groups several `BOQ Section`s (e.g. EL_Asrama + EL_Sekolah + EL_Masjid = Elektrikal) and is the row RAPP groups by.

#### `BoQ Settings` (Single) — constants
`default_ppn_percent` (11), `default_x_factor` (2.5), `default_dp_percent` (10), `sell_rate_precision` (2), and APP.3 financing: `bunga_kmk` (5), `pph` (2.65), `bank_garansi` (5), `jaminan` (1.5), `asuransi` (0.5).

### 3.2 Estimation layer

#### `BOQ Section` (submittable) — one per building × discipline
`project`, `boq` (owner, set via BoQ's *Get Sections*), `discipline` (Link, filtered to the project's active disciplines), `building`, `section_name`, `items` (Table → `Boq Item`).
Computed subtotals (read-only), split for RAPP APP.1: `subtotal_cost_material/labor/cost`, `subtotal_sell_material/labor`, `sub_total`.

`Boq Item` (child) — the BoQ line:

| Field | Notes |
|---|---|
| source_type | Link `Work Analysis` — drives the rate; **filtered** to analyses that price `item_code` in this project (§7) |
| item_code, alias, description, group_label | line identity |
| volume, uom | quantity |
| **net_material / net_labor** | snapshot from `source_type.out_*_rate` |
| margin_category | the `R` code looked up in the Margin Profile |
| material_margin / labor_margin | read-only, from Margin Profile by category |
| **sell_material_rate / sell_labor_rate** | `ROUNDUP(net / (1 − margin), precision)` |
| **amount** | `(sell_material + sell_labor) × volume` |
| **cost_amount** | `(net_material + net_labor) × volume` |

Picking a `source_type` auto-fetches `alias`, `uom`, `net_material`, `net_labor`.

#### `Direct Cost` (submittable) — preliminaries feeding APP.2
`project`, `boq`, `posting_date`, `lines` (Table → `Direct Cost Line`), and four read-only group totals + grand total: `total_persiapan`, `total_mobdemob`, `total_alat`, `total_management`, `total_direct_cost`.

`Direct Cost Line` (child): `category` (`Persiapan` / `Mob-Demob & Test Com` / `Alat & Perlengkapan` / `Management Proyek`), `description`, `qty`, `uom`, `rate`, `amount` (= qty × rate). Category subtotals map to APP.2.1–2.4.

#### `BoQ` (submittable) — the offer & profit model (RAPP)
The project cover page + RAPP engine.

| Field | Notes |
|---|---|
| project, boq_name, location, revision, date, status | header |
| schedule_months, ppn_percent, dp_percent, x_factor | params (default from `BoQ Settings`) |
| direct_cost | Link — else auto-resolved by project |
| recap | Table → `BoQ Recap` (one row per discipline) |
| subtotal_cost, subtotal_offer | Σ budget / Σ penawaran |
| total_app2, total_app3, total_app, total_profit | rolled up |
| **offer_with_ppn** | `subtotal_offer × (1 + ppn)` — RAPP `E5` |

**`Get Sections`** button attaches every project `BOQ Section` not yet owned by a BoQ, then rebuilds the recap.

`BoQ Recap` (child, per discipline): `discipline`, `discipline_name`, `cost_material/labor/total`, `sell_material/labor/total`, `app2`, `app3`, `total_app`, `profit`.

---

## 4. The calculation engine (all server-side in `validate`)

Do all math per-document in `validate()`, never per-row client round-trips — that keeps 1,000 lines fast. Client scripts only mirror the math for live feedback.

| DocType | `validate()` does |
|---|---|
| `Work Analysis` | **Simple:** `out_material = material_rate × (1 + material_percentage/100)` (labor likewise). **Composite:** each component `amount = qty×rate + percentage% × (Σ qty×rate)`; `out_* = Σ component amounts`. |
| `BOQ Section` | per `Boq Item`: snapshot `net_*` from the Work Analysis `out_*`; look up `material/labor_margin` from the active Margin Profile by `margin_category`; `sell_*_rate = ROUNDUP(net / (1 − margin/100), precision)`; `amount`, `cost_amount`; then the split subtotals. |
| `Direct Cost` | `amount = qty × rate` per line; sum per category → the four APP.2 totals + grand total. |
| `BoQ` | group owned sections by discipline → APP.1; APP.2/APP.3 per discipline (below); Total APP, Profit, Offer+PPN. |

### RAPP formulas (per discipline) — verified to the rupiah

```
offer_share  = sell_total / Σ sell_total(all disciplines)
APP.1 budget = cost_total          (Σ cost_amount)
APP.1 offer  = sell_total          (Σ amount)

APP.2 = direct_cost_pool × offer_share  +  sell_total × x_factor
        (direct_cost_pool = persiapan + mobdemob + alat + management)

DP_base = sell_total × dp_percent × (1 + ppn)          ← DP incl. PPN
APP.3   = sell_total × bunga_kmk
        + sell_total × pph
        + DP_base    × bank_garansi
        + DP_base    × jaminan
        + sell_total × asuransi

Total APP = cost_total + APP.2 + APP.3
Profit    = sell_total − Total APP
Offer+PPN = Σ sell_total × (1 + ppn)
```

---

## 5. Price fetch & posting date

In **Work Analysis**, setting `item_code` (Simple) or a component's `item_code` (Composite) calls `get_item_price` to pull the buying `Item Price` valid on the analysis `posting_date`: latest `valid_from ≤ posting_date`, not past `valid_upto`. Changing the posting date re-prices every line.

---

## 6. Rate snapshotting (shared-library safety net)

```
Draft    : Boq Item.net_*  ← live from Work Analysis.out_*_rate (recomputed each save)
On submit : the same save freezes the values (submitted docs are locked)
Future    : master prices move freely; the submitted BoQ is untouched
Re-price a draft: re-open source_type / re-save; submitted docs need an Amend
```

---

## 7. UX helpers & guards

- **`source_type` filter** (`work_analysis_query`): a `Boq Item` only offers Work Analyses that price its `item_code` — matching **`item_code` for Simple** and **`analysis_code` for Composite** (the "two item fields" case) — scoped to the project (+ shared, project-less analyses).
- **`discipline` filter**: only the section project's active disciplines.
- **`analysis_code` / component filters**: only non-stock items; a component can't be the assembly item itself.
- **Connections dashboards**: `Work Analysis → BOQ Section`; `BOQ Section → Work Analysis, Item`; `BoQ → BOQ Section, Direct Cost`.

---

## 8. Handling 1,000+ lines (performance)

1. **Split by section** (~12 sections × 100–250 lines) — never one 1,000-row table.
2. **Master data referenced, not copied** — a `Boq Item` stores a Link + a few numbers.
3. **Bulk `validate`**, no per-row client round-trips.
4. **Snapshot on save/submit** so history is frozen.
5. **1 item = 1 Simple Work Analysis** — light docs instead of a 250-row book.

---

## 9. Parity with Excel (verified)

Reproduced from the source `RAPP` sheet, to the rupiah:

| Output | System | Excel |
|---|---|---|
| Penawaran (excl PPN) | 8,680,000,000 | 8,680,000,000 |
| APP.2 total | 1,424,600,000 | 1,424,600,000 |
| APP.3 total | 770,046,200 | 770,046,200 |
| Total Profit | 1,715,301,788 | 1,715,301,788 |
| **Penawaran + PPN** | **9,634,800,000** | **9,634,800,000** |

Per-discipline APP.2 / APP.3 / Total APP / Profit also match (e.g. Elektrikal APP.2 = 569,511,751). `Total APP` differs by ≤ 1 rupiah (float rounding).

---

## 10. Reporting & roadmap

**Built**
- Full estimation chain: Work Analysis → BOQ Section → BoQ (RAPP) with the calc engine above.
- **RAPP Print Format** on `BoQ` (module print format, Jinja) reproducing the Excel RAPP layout (APP.1 cost-vs-offer, APP.2/3/Total/Profit, Offer+PPN).
- Connections dashboards; link-query and validation guards.

**Pending**
- **Award → Quotation / Sales Order**: each `Discipline` becomes one lump-sum SO line via `Discipline.item`; progress billing (Sales Invoice %) per discipline.
- **APP.2 / APP.3 sub-column detail** stored on `BoQ Recap` for a fully itemised RAPP.
- **REKAP query report** (discipline × building) and **Quantity Takeoff** (auditable volumes).

---

## 11. DocType quick reference

| DocType | Type | Key role |
|---|---|---|
| Work Analysis (+ Component) | submittable | net unit-rate library (Simple / Composite) |
| Margin Profile (+ Component) | submittable | material/labor margin by category |
| Discipline | master | per-project work package → SO line |
| BoQ Settings | single | PPN, X-Factor, DP, financing constants |
| BOQ Section (+ Boq Item) | submittable | priced lines; cost & sell subtotals |
| Direct Cost (+ Line) | submittable | 4 overhead group totals → APP.2 |
| BoQ (+ BoQ Recap) | submittable | RAPP: APP.1/2/3, profit, offer + PPN |
