# ERPNext BoQ / MEP Estimation System — Architecture

**Source analysed:** `BQ_Eproc_MEP_Proyek_Pondok_Pesantren_Al-Khoziny_Sidoarjo_R01.xlsx`
**Target:** Custom Frappe/ERPNext app — full lifecycle (estimation → execution), shared master library.

---

## 1. The one idea that makes this clean

Your spreadsheet looks like "thousands of rows per project", but 90% of that weight is **shared master data**, not project data. Once you separate the two, a 1,000-line project becomes 1,000 *references* to a library, not 1,000 fat records.

The other key reframe: **"Analisa" is not a BoQ concept — it is an AHSP (Analisa Harga Satuan Pekerjaan), a reusable unit-rate build-up.** Analisa-1 (single item + accessories) and Analisa-2 (composite/assembly) are the same object with a different number of components. Model them as one library DocType (`Work Analysis`) and the whole system simplifies.

### Your current calculation chain (confirmed from the file)

| Layer | Excel | What it produces |
|---|---|---|
| 1 | `PRICE LIST` (~6,500 rows, multi-supplier) | raw material/labor prices per supplier |
| 2 | `Analisa-1`, `Analisa-2` | **net** unit rate (material + jasa) per work item |
| 3 | `Hit.*` (Kabel, PL, PK, HVAC) | volume / quantity takeoff |
| 4 | `EL_*`, `FF_*`, `PL_*` building sheets | line = (sell_mat + sell_labor) × volume, with per-category margin |
| 5 | `REKAP_EL/FF/PL`, `REKAP_MEP` | discipline & MEP recap (cost vs sell) |
| 6 | `RAPP`, `Direct Cost` | APP.1/2/3, profit, offer + PPN |

The markup logic, decoded from `EL_ASRAMA`:

```
M = net material rate      (= 'Analisa-1'!Q41  or  'Analisa-2'!I61)
N = net labor  rate        (= 'Analisa-1'!R41  or  'Analisa-2'!J61)
R = margin category code   (1–10, e.g. 7 = equipment, 6 = cable)
S = material margin %       = HLOOKUP(R, margin_table)
T = labor    margin %       = HLOOKUP(R, margin_table)
U = sell material rate      = ROUNDUP( M / (1 - S) )     ← margin-on-sell
V = sell labor    rate      = ROUNDUP( N / (1 - T) )
line amount  J = (U + V) × volume
line cost      = (M + N) × volume
```

This `rate / (1 - margin)` formula is the single most important thing to replicate exactly — it is margin-on-selling-price, **not** a cost markup.

---

## 2. Three layers, three lifetimes

```
MASTER LIBRARY  (shared, lives forever)      ──► referenced by every project
   Item, Item Price, Work Analysis, Margin Profile, BoQ Settings

ESTIMATION      (per project + revision)     ──► references master, freezes on award
   BoQ, BoQ Section, BoQ Item, Quantity Takeoff, Direct Cost, Project Budget

EXECUTION       (native ERPNext)             ──► generated from the awarded BoQ
   Quotation/Sales Order, Project, Material Request, Purchase Order,
   Purchase Receipt/Invoice, Sales Invoice (progress billing)
```

The rule that ties them together: **estimation references the library while in Draft, and snapshots fixed rates onto each `BoQ Item` on submit/award.** Master prices keep moving for future tenders; the awarded BoQ never changes underneath you.

---

## 3. DocType catalog

> ### 📍 Quick map — which Excel sheet becomes which DocType
>
> Read this table first, then check each DocType against your own file. Every DocType below also has a **📍 Excel source** line telling you exactly where it comes from.
>
> | Your Excel sheet / area | Becomes this DocType | Layer |
> |---|---|---|
> | `PRICE LIST` (the ~6,500-row catalog) | `Item` + `Item Price` | Master |
> | The supplier name + price columns in `PRICE LIST` / `PL_Eproc` / `PK_Eproc` | `Item Price` (one row per supplier) | Master |
> | `Analisa-1` (single item + accessories markup) | `Work Analysis` (type = Simple) | Master |
> | `Analisa-2` (composite / assembly build-up) | `Work Analysis` (type = Composite) | Master |
> | Each ingredient row *inside* an Analisa block | `Work Analysis Component` | Master |
> | The "Waste 2%" / "Mat. Bantu 15%" rows inside Analisa | `Work Analysis Component` (type = Percentage) | Master |
> | The margin table `N2:W4` (codes 1–10) on the rekap/building sheets | `Margin Profile` + `Margin Profile Row` | Master |
> | `Hit.HVAC`, `Hit.PL`, `Hit.Kabel`, `Hit.PK` (quantity takeoffs) | `Quantity Takeoff` + `Takeoff Line` | Estimation |
> | One building sheet, e.g. `EL_ASRAMA`, `FF_MASJID`, `PL_SEKOLAH` | `BoQ Section` | Estimation |
> | One **line** inside a building sheet (the columns E…J + helper M…V) | `BoQ Item` | Estimation |
> | `REKAP TOTAL_EL` / `_FF` / `_PL` and `REKAP TOTAL_MEP` | *(a report, not a table — see §4)* | Estimation |
> | The project header info (name, location, revision, schedule, DP) | `BoQ` | Estimation |
> | `Direct Cost` sheet | `Direct Cost` + `Direct Cost Line` | Estimation |
> | `RAPP` (APP.1 / APP.2 / APP.3 / profit / offer + PPN) | `Project Budget` | Estimation |
>
> Sheets like `PL_Original`, `PK_Original`, `REKAP TOTAL_EL` etc. that are *derived* (formulas pointing at other sheets) do **not** each become a table — in ERPNext they become reports or are recomputed live. Only the sheets where you actually *type data* become DocTypes.

### 3.1 Master library

#### `Item` (native — reuse, don't reinvent)
Every material and every labor/jasa line. Add custom fields only.

> **📍 Excel source:** column **B "NAMA BARANG"** of the `PRICE LIST` sheet (plus `MERK`, `TYPE/SPESIFIKASI`, `UKURAN`, `SAT.`). Each unique product/service becomes one `Item`. This is your master goods-and-services list — the thing that appears over and over across all the building sheets.

| Field | Type | Notes |
|---|---|---|
| item_group | (native) | `Material` or `Jasa / Service`; services have `is_stock_item = 0` |
| custom_discipline | Select | EL / FF / PL / AC / Common |
| custom_default_ppn_code | Select | Include / Exclude / Non PPN |

#### `Item Price` (native — reuse)
Normalize the wide multi-supplier `PRICE LIST` into one row per (item, supplier, price list). One `Price List` per supplier (or per `Buying` source).

> **📍 Excel source:** the **price columns** of `PRICE LIST` — `SUPPLIER 1 / NAMA SUPPLIER / HARGA (Rp)`, then `SUPPLIER 2`, `SUPPLIER 3`, etc. across the row. In Excel one item has many supplier columns side-by-side; in ERPNext that becomes **many `Item Price` rows** (one per supplier) for the same item. The `KODE PPN` and `UPDATE` columns map to `ppn_code` and `valid_from`. The cleaned vendor lists in `PL_Eproc` and `PK_Eproc` are the same thing for plumbing and fire-fighting.

| Field | Type | Notes |
|---|---|---|
| price_list | Link Price List | one per supplier, e.g. "Supplier – Schneider" |
| item_code, price_list_rate | (native) | the price |
| supplier | Link Supplier | who quoted it |
| custom_ppn_code | Select | Include / Exclude / Non |
| valid_from | Date | the `UPDATE` column |

A Query Report `Supplier Price Comparison` then reproduces the side-by-side columns + lowest-price pick. Never store supplier prices as columns.

#### `Work Analysis` ⭐ (custom — the AHSP library; replaces Analisa-1 + Analisa-2)
One record = one analysed unit rate.

> **📍 Excel source:** the `Analisa-1` **and** `Analisa-2` sheets. Each "block" in those sheets — one titled mini-table like *"Tangki Harian 1.000 L"* or *"NYY 4 x 4 mm2 + BC 4 mm2"* with its own `Total` row — becomes **one `Work Analysis` record**. The block's final `Total` for Material and Jasa is what gets stored in `out_material_rate` and `out_labor_rate`. `Analisa-1` blocks are the Simple type (basically one product + an accessories %); `Analisa-2` blocks are the Composite type (several ingredients added up).

| Field | Type | Notes |
|---|---|---|
| analysis_code | Data, unique | e.g. `AN2-NYY-4x4-BC4` |
| analysis_name | Data | "NYY 4×4mm² + BC 4mm²" |
| discipline | Select | EL / FF / PL / AC |
| uom | Link UOM | per Mtr / Set / Unit |
| analysis_type | Select | Simple (was Analisa-1) / Composite (was Analisa-2) — informational only |
| **out_material_rate** | Currency, read-only | computed |
| **out_labor_rate** | Currency, read-only | computed |
| **out_total_rate** | Currency, read-only | = material + labor |
| status | Select | Draft / Active / Archived |
| components | Table → `Work Analysis Component` | |

`Work Analysis Component` (child):

> **📍 Excel source:** the **numbered ingredient rows inside one Analisa block** (the `No. / Uraian / Qty / Sat. / Harga Satuan Material / Jasa` lines). Each of those rows = one `Work Analysis Component`. Think of it like a cooking recipe: the `Work Analysis` is the finished dish ("NYY 4×4 cable run, per meter") and each Component is one ingredient with its quantity and price.
>
> **Worked example — the `Analisa-2` block "NYY 4 x 4 mm2 + BC 4 mm2" (per Mtr):**
>
> | Excel row | → becomes a Component with | component_type |
> |---|---|---|
> | `1  NYY 4 x 4 mm2 … 1 Mtr … 53450 / 14514` | item = NYY 4×4, qty = 1, material_rate = 53450, labor_rate = 14514 | `Item` |
> | `2  BC 4 mm2 … 1 Mtr … 11850 / 3629` | item = BC 4mm², qty = 1, material_rate = 11850, labor_rate = 3629 | `Item` |
> | `3  Waste … 2% … Terhadap Material` | percentage = 2%, percent_base = Material | `Percentage` |
> | `4  Mat. Bantu, aksesories dll. … 10% … Terhadap Upah` | percentage = 10%, percent_base = Labor | `Percentage` |
>
> Add those up and you get the block's `Total` (Material 68421 / Jasa 18143) → that total flows into the parent `Work Analysis.out_material_rate` / `out_labor_rate`. **Nothing is lost** — every row you see in Excel has a home. The only change is that the "Waste" and "Mat. Bantu" rows are flagged as `Percentage` instead of real items, because they're a % of the rows above, not a product you buy.

| Field | Type | Notes |
|---|---|---|
| component_type | Select | `Item` / `Percentage` |
| item | Link Item | when type = Item |
| description | Small Text | for Percentage rows ("Waste", "Mat. Bantu") |
| qty | Float | |
| uom | Link UOM | |
| material_rate | Currency | fetched from Item Price or manual |
| labor_rate | Currency | |
| percentage | Percent | when type = Percentage (e.g. waste 2%, bantu 15%) |
| percent_base | Select | Material / Labor / Both — what the % applies to |
| amount_material | Currency, read-only | qty × material_rate, or %·base |
| amount_labor | Currency, read-only | |

This one child table covers **everything** in both Analisa sheets: real components are `Item` rows; "Waste 2% terhadap Material" and "Mat. Bantu 15%" become `Percentage` rows. Add a **Refresh rates** button that re-pulls `material_rate` from the chosen `Item Price` (lowest, or a selected supplier).

#### `Margin Profile` (custom — the `N2:W4` lookup table)
Shared, versioned. A BoQ points to one profile.

> **📍 Excel source:** the little **margin/profit table** sitting top-right on the building and rekap sheets — the `KODE / MATERIAL / UPAH` rows at `N2:W4` (codes 1 to 10, each with a material % and a labor %). This is the table your building sheets do `HLOOKUP` against to mark a net price up to a selling price. One `Margin Profile Row` per code.

| Field | Type |
|---|---|
| profile_name | Data |
| rows | Table → `Margin Profile Row` |

`Margin Profile Row` (child): `category_code` (Int 1–10), `category_name`, `material_margin` (Percent), `labor_margin` (Percent).

#### `BoQ Settings` (custom — Single)
Defaults: `default_ppn` (11%), `default_margin_profile`, `default_x_factor` (2.5%), financing constants for APP.3 (`bunga_kmk` 5%, `pph` 2.65%, `bank_garansi` 5%, `jaminan` 1.5%, `asuransi` 0.5%), `rounding_digits`.

> **📍 Excel source:** the **fixed % numbers you hardcode** in `RAPP` — the X-Factor `K26` (2.5%), and the financing rates row `G41:K41` (bunga 5%, PPH 2.65%, bank garansi 5%, jaminan 1.5%, asuransi 0.5%), plus PPN 11%. Instead of retyping them in every project, they live in one settings page.

---

### 3.2 Estimation layer

#### `BoQ` (custom, submittable) — the estimate header (per project + revision)

> **📍 Excel source:** the **project header block** repeated at the top of `RAPP` and every rekap sheet — `Nama Proyek`, `Lokasi`, `Tgl / Rev.`, `Schedule Proyek (Bulan)` (`H5`), `DP =` (`C7`). One `BoQ` record = one project revision (your `R00`, `R01`). It's the "cover page" that ties all the sections together.

| Field | Type | Notes |
|---|---|---|
| project | Link Project | optional until award |
| boq_name, location | Data | |
| revision | Data | R00, R01… (or use Amend) |
| date | Date | |
| status | Select / Workflow | Draft → For Approval → Awarded → Cancelled |
| margin_profile | Link Margin Profile | |
| schedule_months | Int | RAPP `H5` |
| dp_percent | Percent | RAPP `C7` |
| ppn_percent | Percent | default from settings |
| sections | Table → `BoQ Section Link` | list/order of sections |
| total_cost_material / total_cost_labor / total_sell | Currency, read-only | rolled up |

#### `BoQ Section` (custom) — **one per building × discipline** (mirrors `EL_ASRAMA`)
This is the performance keystone: each section holds ~100–250 lines in a child table, never 1,000+ in one place.

> **📍 Excel source:** **one whole building sheet tab** = one `BoQ Section`. So `EL_ASRAMA` → a section (discipline EL, building Asrama); `FF_MASJID` → a section; `PL_SEKOLAH` → a section, and so on. You have ~12 of these tabs, so you'll have ~12 sections. This is *why* the 1,000+ lines never pile into one place — they're spread across the sections exactly like your tabs already spread them.

| Field | Type | Notes |
|---|---|---|
| boq | Link BoQ | |
| discipline | Select | EL / FF / PL |
| building | Data | Asrama / Sekolah / Masjid / Utilitas |
| section_name | Data | "Pekerjaan Elektrikal – Asrama" |
| sort_order | Int | |
| subtotal_cost / subtotal_sell | Currency, read-only | |
| items | Table → `BoQ Item` | the lines |

#### `BoQ Item` (child of `BoQ Section`) — the BoQ line

> **📍 Excel source:** **one line row inside a building sheet** — e.g. row 41 of `EL_ASRAMA`, *"PP-1, NYY 4 x 4 mm2 + BC 4 mm2"*. The visible columns (`E` description, `F` volume, `G` unit, `H/I` unit prices, `J` total) plus the hidden helper columns (`M/N` net rates pulled from Analisa, `R` margin code, `U/V` selling rates) all collapse into the fields below.
>
> **Worked example — `EL_ASRAMA` row 41:**
>
> | Excel cell | Value / formula | → BoQ Item field |
> |---|---|---|
> | `E41` | "PP-1, NYY 4×4mm² + BC 4mm²" | `description` |
> | `M41 = 'Analisa-2'!I61` | net material 68421 | `net_material_rate` (snapshot from `Work Analysis`) |
> | `N41 = 'Analisa-2'!J61` | net labor 18143 | `net_labor_rate` |
> | `F41 = Hit.Kabel!D46` | volume (meters) | `volume` (from `Quantity Takeoff`) |
> | `R41` | 6 | `margin_category` |
> | `U41 = ROUNDUP(M41/(1−S41))` | selling material | `sell_material_rate` (auto) |
> | `J41 = (H41+I41)*F41` | line total | `amount` (auto) |
>
> So the row you type by hand in Excel becomes: *pick a `Work Analysis`* (gives the net rates), *set volume*, *set margin code* — and ERPNext computes the selling rates and the line total for you, identical to your `U/V/J` formulas.

| Field | Type | Notes |
|---|---|---|
| item_no | Data | 1, 2, 3… |
| group_code / group_label | Data | "1.1 / Panel", "1.2 / Pengkabelan" |
| description | Small Text | |
| source_type | Select | Work Analysis / Item / Manual |
| work_analysis | Link Work Analysis | drives the rate |
| item | Link Item | when source = Item |
| volume | Float | manual or fetched from Quantity Takeoff |
| uom | Link UOM | |
| **net_material_rate** | Currency | fetched from `work_analysis.out_material_rate`, **snapshotted on submit** |
| **net_labor_rate** | Currency | snapshotted |
| margin_category | Int | the `R` code |
| material_margin / labor_margin | Percent, read-only | looked up from Margin Profile |
| **sell_material_rate** | Currency, read-only | `roundup(net_material/(1−material_margin))` |
| **sell_labor_rate** | Currency, read-only | `roundup(net_labor/(1−labor_margin))` |
| **amount** | Currency, read-only | `(sell_material+sell_labor) × volume` |
| **cost_amount** | Currency, read-only | `(net_material+net_labor) × volume` |
| takeoff_ref | Link Quantity Takeoff | optional source of `volume` |

#### `Quantity Takeoff` (custom — the `Hit.*` sheets; optional, recommended)
Auditable volume calc. Header + child `Takeoff Line` (`description`, `length`, `count`, `factor`, `result_qty`, `maps_to_description`). A `BoQ Item.volume` can fetch from here so quantities are traceable, not hardcoded.

> **📍 Excel source:** the `Hit.HVAC`, `Hit.PL`, `Hit.Kabel`, `Hit.PK` sheets — your **quantity takeoff / "hitungan" calculations**. These are where your volumes (cable meters, pipe lengths, counts) are worked out before they feed column `F` of a building sheet. Optional for phase 1 (you can just type the volume), but worth it later so the numbers are traceable instead of hardcoded.

#### `Direct Cost` (custom — feeds APP.2)
Header + child lines grouped: Persiapan/Direksi Kit, Mob-Demob/Perizinan/Test-Com, Alat/K3/APD, Management Proyek. Mirrors `Direct Cost` sheet rows `R41/R72/R81/R102`.

> **📍 Excel source:** the `Direct Cost` sheet — your **preliminaries / overhead** (site office, mob-demob, permits, test & commissioning, tools, K3/HSE, project management). The four group subtotals at rows `R41 / R72 / R81 / R102` are what `RAPP` pulls into APP.2.

#### `Project Budget (RAPP)` (custom) — the offer & profit model

> **📍 Excel source:** the entire `RAPP` sheet. APP.1 = the *"Real Cost / Budget VS Penawaran"* block (rows 12–22); APP.2 = the prelim/overhead block (rows 24–37); APP.3 = the financing block (rows 39–52); then *Total APP* (54–67), *Profit* (69+), and the final `Penawaran + PPN 11%` at `E5`. One `Project Budget` record per BoQ revision.

| Block | Source | Formula |
|---|---|---|
| **APP.1** budget vs offer per discipline | BoQ recap | cost (O/P/Q) vs sell (W/X/Y) per discipline |
| **APP.2** prelim/overhead | Direct Cost + x-factor | `(direct_cost / subtotal_APP1) × disciplineSell + sell × x_factor` |
| **APP.3** financing | BoQ Settings % | bunga, PPH, bank garansi, jaminan, asuransi (the `G41:K41` constants) |
| **Total APP** | | APP.1 + APP.2 + APP.3 |
| **Profit** | | `offer − Total APP` |
| **Offer + PPN** | | `subtotal_APP1 × (1 + ppn)` |

---

### 3.3 Execution layer (native ERPNext — the "full lifecycle" half)

On **BoQ → Awarded**, generate:

| From estimation | Native target | Purpose |
|---|---|---|
| BoQ Items (sell side) | **Quotation → Sales Order** | the client offer; basis for billing |
| BoQ + sections/groups | **Project + Tasks** | execution structure |
| BoQ cost side (net mat+labor) | **Project budget baseline** | the "Budget" column in APP.1 variance |
| BoQ Items where source = Item/material | **Material Request → Purchase Order → Purchase Receipt/Invoice** | procurement; actual buy cost lands on the project |
| BoQ Items where source = Jasa | **Purchase Order (service)** / Job Card | subcontract labor |
| % progress per item/section | **Sales Invoice (percentage billing)** | progress claims |

This closes the loop your `RAPP` only models on paper: **actual** PO/invoice cost vs the **budget** baseline = real-time version of APP.1's "Real Cost / Budget VS Penawaran".

---

### 3.4 Follow ONE line all the way up (plain language)

If the layers still feel abstract, trace a single real line — *"PP-1, NYY 4×4mm² cable"* — from the bottom of your file to the final offer. Every arrow below is a real link in the system:

1. **`PRICE LIST`** has the raw price of `NYY 4×4mm²` cable and `BC 4mm²` wire from your suppliers → these become **`Item`** + **`Item Price`** records.
2. In **`Analisa-2`**, the block *"NYY 4×4mm² + BC 4mm²"* adds those two items together with 2% waste and 10% accessories → this whole block becomes **one `Work Analysis`**, and its `Total` (68,421 material / 18,143 labor per meter) is the **net unit rate**.
3. In **`Hit.Kabel`** you calculate there are, say, 120 meters of this cable → becomes a **`Quantity Takeoff`** giving `volume = 120`.
4. In **`EL_ASRAMA`** row 41, you write the line: it pulls the net rate from Analisa-2, the volume from Hit.Kabel, applies margin code 6 from the **`Margin Profile`** to get the selling price, and multiplies by 120 → this is **one `BoQ Item`** inside the **`BoQ Section`** "EL – Asrama".
5. All the lines in that sheet sum to the sheet subtotal; all the EL sheets sum in **`REKAP TOTAL_EL`**; EL+FF+PL sum in **`REKAP TOTAL_MEP`** → in ERPNext this is a **report** that adds up the `BoQ Item` amounts (no extra table needed).
6. **`RAPP`** takes that grand total, adds prelims (APP.2 from **`Direct Cost`**), adds financing (APP.3), subtracts it all to show **profit**, and adds PPN 11% for the final offer → becomes **`Project Budget`**.

That's the whole spreadsheet, in one sentence: **raw prices → analysed unit rates → priced BoQ lines → recap → project budget.** The DocTypes are just those six stops with names.

---

## 4. Where each calculation lives (the engine)

Do all math **server-side in `validate`** (bulk per document), never per-row client round-trips — that is what keeps 1,000 lines fast.

| DocType | `validate()` does |
|---|---|
| `Work Analysis` | sum components (items: qty×rate; percentages: %·base) → set `out_material_rate`, `out_labor_rate`, `out_total_rate` |
| `BoQ Section` | for each `BoQ Item`: fetch margins from the BoQ's Margin Profile by `margin_category`; compute `sell_*_rate = roundup(net/(1−margin))`, `amount`, `cost_amount`; then `subtotal_*` |
| `BoQ` | aggregate sections → `total_*` |
| `Project Budget` | pull BoQ recap + Direct Cost + financing → APP.1/2/3, profit, offer+PPN |

**Recap (`REKAP_*`) is a report, not stored data.** Build a Query Report / Dashboard that groups `BoQ Item` by discipline and building and sums `cost_amount` vs `amount`. Don't duplicate totals into records you have to keep in sync.

---

## 5. Handling 1,000+ lines (performance)

1. **Split by section.** ~12 sections (4 buildings × 3 disciplines) × ~100–250 lines = comfortable child tables. One 1,000-row child table is the thing that makes ERPNext crawl — avoid it.
2. **Master data is referenced, not copied.** A `BoQ Item` stores a Link + a few numbers, not the full analysis. The 6,500 prices and ~580 analyses exist once.
3. **Bulk `validate`,** no per-row client scripts. Compute the whole section in one Python pass.
4. **Snapshot on submit.** Store `net_*_rate` on the item at award so you never re-query the library for a frozen BoQ (and so master price changes don't rewrite history).
5. **Recap via SQL/report,** not stored rollups.
6. **Import masters via Data Import / CSV** (Section 7), not manual entry.

---

## 6. Rate snapshotting (the shared-library safety net)

```
Draft BoQ      : BoQ Item.net_rate  ← live fetch from Work Analysis (always current)
On submit/award: copy Work Analysis.out_*_rate → BoQ Item.net_*_rate  (frozen)
Future projects: master prices update freely; awarded BoQ is untouched
Re-price a draft: "Refresh rates" button re-pulls; submitted docs need an Amend
```

Implement with a `fetch_from` for live draft display **plus** an explicit copy in `on_submit`. This is the single most important behaviour for "shared library + full lifecycle" to coexist safely.

---

## 7. Migrating the existing Excel

Scripted, in this order (each is a `frappe.get_doc(...).insert()` loop or a Data Import):

1. **PRICE LIST → Item + Item Price.** Dedupe items by (nama_barang + merk + type + ukuran). Each supplier column → one `Item Price` row under that supplier's Price List. Carry `KODE PPN` and `UPDATE`.
2. **Margin table (`N2:W4`) → Margin Profile** (codes 1–10, material/labor %).
3. **Analisa-1 + Analisa-2 → Work Analysis.** Each analysis block = one `Work Analysis`; component lines = `Item` child rows; "Waste %" / "Mat. Bantu %" = `Percentage` child rows. Keep a mapping `{excel_cell_ref → analysis_code}` (e.g. `Analisa-2!I61 → AN2-NYY-4x4-BC4`) — you need it for step 5.
4. **`Hit.*` → Quantity Takeoff** (optional first pass: just import resulting volumes).
5. **Building sheets → BoQ Section + BoQ Item.** For each line, resolve its `='Analisa-X'!...` reference through the step-3 mapping to set `work_analysis`; set `volume`, `margin_category` (the `R` value), `group_code`.
6. **RAPP + Direct Cost → Project Budget + Direct Cost.**

A Python pre-processor (openpyxl/pandas) that emits clean CSVs per DocType is the fastest path; ERPNext Data Import ingests the CSVs.

---

## 8. Build roadmap

| Phase | Deliverable | Outcome |
|---|---|---|
| 0 | App scaffold `boq`, `BoQ Settings`, UOM/Item Group setup | foundation |
| 1 | `Item` + `Item Price` + import PRICE LIST; Supplier Comparison report | master prices live |
| 2 | `Work Analysis` (+ components, Refresh rates); import Analisa-1/2 | unit-rate library live |
| 3 | `Margin Profile`; `BoQ` + `BoQ Section` + `BoQ Item` + calc engine | a project BoQ computes end-to-end |
| 4 | `Direct Cost` + `Project Budget` (APP.1/2/3, profit, PPN); REKAP report | full offer reproduces the Excel |
| 5 | Award → Quotation/SO + Project + Material Request/PO; cost-vs-budget | execution lifecycle |
| 6 | `Quantity Takeoff`; progress billing (Sales Invoice %) | full lifecycle |

Phases 1–4 reproduce your spreadsheet exactly; 5–6 are the upgrade the spreadsheet can't do.

---

## 9. Validation checks (prove parity with Excel)

- Pick 5 `Work Analysis` records; their `out_total_rate` must equal the Excel "Total" cell to the rupiah.
- Pick 5 `BoQ Item` lines; `sell_material_rate` must equal `ROUNDUP(M/(1−S))` from the sheet.
- A full `BoQ` discipline subtotal must equal `REKAP_*!I30`.
- `Project Budget` offer+PPN must equal `RAPP!E5`.

Lock these as automated tests so future master-price edits never silently break a tendered number.
