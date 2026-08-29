# NeoAqua

**Bottled Water Plant, Van Sales & Distribution Suite for Frappe/ERPNext v15**
Built for the Saudi Arabian and wider GCC market by Neotec Integrated Solutions, Riyadh.

NeoAqua is a single app covering the whole water business: procure-to-pay for
preforms, caps, labels and chemicals; a five-level manufacturing chain from
source water to a palletised shrink pack; POS and van sales with salesman
geofencing; returnable 5-gallon container control; and a cash-return / day-close
settlement that reconciles cash, stock and containers in one document.

---

## 1. Requirements

| Component | Version |
|---|---|
| Frappe Framework | v15.x |
| ERPNext | v15.x |
| Python | 3.10+ |
| MariaDB | 10.6+ |

ERPNext is a hard dependency — NeoAqua extends Stock, Manufacturing, Selling,
Buying and Accounts rather than reimplementing them.

## 2. Installation

### Frappe Cloud

Add the app to your bench via the GitHub repository, then install on the site.
`after_migrate` re-applies custom fields, roles, dashboards and workspaces on
every deployment, so a push-triggered migrate is self-healing.

### Self-hosted bench

```bash
cd ~/frappe-bench
bench get-app neoaqua https://github.com/jamunachi08/neoaqua.git --branch main
bench --site yoursite.local install-app neoaqua
bench --site yoursite.local migrate
bench build --app neoaqua
```

### Is it set up? Check first

```bash
bench --site yoursite.local execute neoaqua.setup.orchestrator.print_status
```

Prints the setup checklist of what exists versus what should — item counts by
class, BOMs, routings, warehouses, accounts, cost centers, vans, batch rules.
The same checklist renders at the top of **NeoAqua Settings**.

### One command to a working plant

```bash
bench --site yoursite.local execute neoaqua.setup.install.setup_all \
  --kwargs "{'company':'Neo Aqua','with_demo':True}"
```

That runs the master seeder, the accounting setup, the BOM tree, the batch
naming rules, the dashboards and — with `with_demo` — a week of demo trading.
Drop `with_demo` for a clean production site.

### Seed the water plant

The master-data seeder runs automatically when the site has exactly one company
and no NeoAqua items yet. To run it explicitly, or for a second company:

```bash
bench --site yoursite.local execute neoaqua.setup.install.seed_plant \
  --kwargs "{'company':'Neo Aqua'}"
```

This creates, idempotently:

* UOMs, item groups, 16 warehouses (including three van warehouses)
* 25 raw materials, 7 WIP items, 6 finished bottles, 6 shrink packs
* Four price lists (Retail / Wholesale / HORECA / Purchase) with rates
* Nine workstations with hour rates, nine operations, and routings
* KSA VAT 15% sales tax and item tax templates
* Three vans, three routes, three POS profiles
* The complete multi-level BOM tree (below)
* NeoAqua Settings pre-configured

Re-run it as often as you like; nothing is duplicated.

Verify structure before any commit:

```bash
python3 verify_tree.py
```

## 3. The BOM tree

The chain is five levels deep for a small PET bottle, which is what the plant
actually costs against. BOMs are built bottom-up so ERPNext can resolve the
exploded item list and roll up cost at every level.

```
FG-PCK-600-24   Shrink Pack 600 ml x 24              [Level 1]
├── FG-BOT-600  Filled & Labelled Bottle 600 ml      [Level 2]
│   ├── WIP-BTL-600  Blown Empty Bottle              [Level 3]
│   │   └── RM-PRF-14G  PET Preform 14 g
│   ├── WIP-WTR-OZ   Mineralised & Ozonated Water    [Level 4]
│   │   ├── WIP-WTR-RO  RO Permeate Water            [Level 5]
│   │   │   ├── RM-WTR-SRC       Source water (1.35 L per litre, 74% recovery)
│   │   │   ├── RM-CHM-ANTISCAL  RO antiscalant
│   │   │   └── RM-CHM-NAOCL     Sodium hypochlorite
│   │   └── RM-CHM-MINERAL       Mineral blend
│   ├── RM-CAP-28    Closure 28 mm PCO 1810
│   └── RM-LBL-600   BOPP wrap label
├── RM-SHR-FILM      LDPE shrink film
└── RM-CTN-TRAY      Corrugated base tray
```

Yield factors are baked into the component quantities rather than left implicit:
RO recovery 74 %, blow-moulding yield 98.5 %, filling yield 98.5 %, packing
yield 99.8 %.

The 18.9 L (5-gallon) line skips blow moulding — the polycarbonate bottle is a
returnable asset that is washed and refilled, so its BOM consumes 2 % fleet
attrition plus cap, label and CIP chemical.

### SKU range

| Format | Bottle | Pack |
|---|---|---|
| 200 ml | FG-BOT-200 | x 48 shrink |
| 330 ml | FG-BOT-330 | x 40 shrink |
| 600 ml | FG-BOT-600 | x 24 and x 12 |
| 1.5 L | FG-BOT-1500 | x 6 |
| 5 L | FG-BOT-5000 | x 4 |
| 18.9 L (5 gal) | FG-BOT-18900 | single, returnable |

Names shown with the seeded brand; yours will carry whatever you set. These are
the formats actually on shelf in KSA. Note that the market standard
small bottle is **330 ml**, not 300 ml — 300 ml is not a sold format here, so the
seeder ships 330 ml. Add a 300 ml SKU by appending one row to `FG_BOTTLES` and
one to `LEVEL_2` in `neoaqua/setup/`.

## 5. Process flows

### Procure to pay

```
Material Request (Purchase)  →  Request for Quotation  →  Supplier Quotation
        →  Purchase Order  →  Purchase Receipt  →  Purchase Invoice  →  Payment Entry
```

NeoAqua adds two gates on the standard cycle:

* **Purchase Order** — a supplier of food-contact material (preforms, closures,
  labels, PC bottles) must hold an SFDA registration and an unexpired CR.
* **Purchase Receipt** — food-contact material cannot be received without a
  Certificate of Analysis reference.

### Production

```
Material Request (Manufacture) or Production Plan
        →  Work Order (per level)  →  Job Card per operation
        →  Stock Entry: Material Transfer for Manufacture
        →  Stock Entry: Manufacture  →  Finished Goods Store
```

A Water Quality Check is auto-raised on Work Order submit for any item flagged
`Requires Water Quality Check`. When `Block FG Transfer without Passed QC` is on,
a Manufacture entry into the FG warehouse is refused unless the batch has a
submitted Finished Goods check with result Pass or Conditional Release. A failed
check disables the batch outright.

### Van sales day

```
Van Load Request / Van Trip  →  Stock Entry: plant → van warehouse
        →  Salesman Check In (GPS, geofence evaluated)
        →  POS Invoice / Sales Invoice against the van warehouse
        →  Payment Entry (tagged to the trip)
        →  Van return: unsold stock → plant, damaged → scrap
        →  Salesman Day Close  →  Journal Entry (cash deposit)
```

## 6. Geofencing

Two zone shapes are supported: **Circle** (centre + radius, haversine distance)
and **Polygon** (ray-casting point-in-polygon). Enforcement is a setting:

| Level | Behaviour |
|---|---|
| Warn Only | A message is shown; nothing is blocked. |
| Block Check-in | `Salesman Check In` cannot be submitted outside the fence without an override reason. |
| Block Invoice | A Sales Invoice is refused unless an in-fence check-in exists for that customer today. |

Every check-in stores latitude, longitude, GPS accuracy, the resolved zone, the
computed distance and a within/outside flag — so the compliance report is based
on measured data, not self-declaration.

## 7. Day close / cash return

`Salesman Day Close` is the single settlement document. It pulls every invoice,
credit note, payment entry and the load sheet from the trip, then reconciles
three independent balances:

**Cash** — `opening float + cash sales + collections − route expenses` versus
cash physically declared. Variance beyond the configured tolerance forces a
reason and a treatment (ignore / recover from salesman / write off) and, if a
Day Close Approver Role is set, restricts submission to that role.

**Stock** — `loaded − sold − returned − damaged`. Returned quantity posts a
transfer back to the plant; damaged quantity posts a write-off to scrap.

**Containers** — full containers issued versus empties returned.

On submit the document creates the return Stock Entry, the damage Stock Entry
and the cash-deposit Journal Entry, and closes the trip.

## 8. Returnable containers

`Container Ledger Entry` is a per-customer sub-ledger for the 18.9 L
polycarbonate fleet. Entry types cover issue, return, deposit received, deposit
refunded, lost/damaged and opening balance. Deposits post to a liability account
against the customer — the bottle is never revenue until it is written off. The
`Customer Container Balance` report shows containers in the market, deposits
held, deposit liability and the uncovered exposure between them.

## 9. Accounting

The seeder builds the accounts NeoAqua posts against, wires them into the
Company defaults and turns on perpetual inventory. Without this an installed
site cannot raise its first invoice, because items have no income account.

| Group | Accounts created |
|---|---|
| Stock assets | Raw Material Stock, Work In Progress Stock, Finished Goods Stock, Van Stock, Quarantine Stock, Returnable Containers in Market |
| Cash | Van Cash in Hand (separate from the cashier's till) |
| Liabilities | Container Deposit Liability |
| Income | Sale of Bottled Water, Container Forfeiture Income, Cash Overage |
| Cost of sales | Cost of Bottled Water Sold, Stock Adjustment, Stock Damage and Scrap, Cash Shortage |
| Route expenses | Fuel, Toll and Salik, Parking, Vehicle Repair, Loading Labour, Driver Meals, Municipality Fines, Other |

**Cost centers**: Production (RO Plant, Blow Moulding, Line 1/2/3, Packing) and
Distribution (one per van), under the company root.

**Warehouse accounts**: each warehouse is mapped to its own stock account, so
the balance sheet shows raw material, WIP, finished goods and van stock as
separate lines rather than one undifferentiated Stock In Hand.

**Item defaults**: every item gets a complete Item Default row — warehouse,
income account, expense account, buying and selling cost center. Item Group
defaults are set too, so items added later inherit them without anyone
remembering.

**Route expenses**: `NeoAqua Settings` holds an expense-type to account map,
so a salesman entering fuel on a day close never picks a GL account.

**Cash variance** posts by sign: a shortage debits Cash Shortage, an overage
credits Cash Overage.

---

## 10. Demo Data

`NeoAqua Demo Tool` (single doctype) generates one coherent week of trading:

| Area | What it creates |
|---|---|
| Parties | 4 suppliers with SFDA/CR data, 10 customers across every channel with geofenced locations in Riyadh, 3 salesmen with route stops |
| Stock | Opening raw material receipt across 24 items |
| Procurement | Material request, purchase orders per supplier, receipts with CoA references, purchase invoices |
| Production | A five-level run — RO permeate, ozonated water, blown bottle, filled bottle, shrink pack — with batches and passed quality checks at each gate |
| Distribution | 3 van trips with GPS check-ins, POS and credit invoices, a collection, container issues, and a settled day close (one van deliberately short SAR 12, so the variance workflow is visible) |

### Stage isolation

The accounting stage creates accounts and cost centers first, then wires
company defaults, warehouse accounts, item group defaults and settings. Only
the first part is load-bearing — the item master needs the accounts to *exist*,
not to be fully wired. A failure in a wiring step is recorded as a warning on
the stage and does not skip items, BOMs, vans and batch rules behind it.

The item master behaves the same way: each of the 44 items is created
independently, so one rejected item costs you that item and not the other
forty-three.

### If the tool says the plant is not set up

The demo needs the item master and BOM tree to exist before it can trade with
anything. The tool shows a readiness banner on open, and carries two actions:

* **Run Plant Setup** — runs the full ten-stage setup for the selected company
  from the browser. No bench command needed.
* **Diagnose Setup** — shows the 19-point checklist, any stage that Failed or
  was Skipped with its reason, and the recent NeoAqua entries from the Error
  Log. Stage tracebacks are logged rather than shown, which is right for an
  install and useless when you are staring at an empty item master; this is how
  you get at them.

If the site has several companies, Diagnose lists them — setup applies to the
one selected on the form, not to all of them.

### Deleting it again

Every document created is logged to `NeoAqua Demo Record` with a monotonic
sequence number. Deletion walks that log in **reverse** order — dependents were
created after their dependencies, so reverse order is a valid topological
order — cancelling submitted documents before deleting them so ERPNext reverses
its own ledgers, and retrying across up to five passes because a link that
blocks deletion on pass one is often gone by pass two.

Type `DELETE` in the confirmation field, then use **Danger Zone → Delete Demo
Data**. Demo customers and suppliers are kept unless you tick
*Also Delete Demo Customers and Suppliers*.

It only ever touches documents in its own log. Anything you entered yourself is
untouched — which is the point of tracking rather than pattern-matching on names.

If a site has been used for open-ended testing and you want a clean opening
position, `neoaqua.setup.demo_cleanup.delete_all_company_transactions` wraps
ERPNext's own company transaction wipe. That removes **all** transactions, not
just demo ones, and keeps masters and the chart of accounts.

---

## 11. Batch Numbering

Batch codes are composed by a rule engine rather than a fixed naming series.

### The builder

`Batch Code Builder` (desk page, linked from the Water Manufacturing workspace)
is the tool. Pick segments from a palette, reorder them, set length, padding,
case and separator per segment, and watch the code assemble live. Four presets
ship with it, and the canvas saves to a `Batch Naming Rule`.

### Segment types

| Group | Segments |
|---|---|
| Literal | Fixed Text, Plant Code, Company Abbreviation |
| Item | Item Code, Item Batch Code, Item Group Code, Fill Volume |
| Production | Production Line Code, Shift Code, Work Order Suffix |
| Manufacture date | Year (YY/YYYY), Month (MM / letter A–L), Day, Julian Day (DDD), Week, Date (YYMMDD) |
| Expiry date | Expiry Year, Month, Day, Expiry (YYMMDD) — derived from item shelf life |
| Sequence | Sequence Counter with eight scope options |
| Anything else | Custom Field on Item, Work Order, Batch or Stock Entry |

Each segment can be passed through a **value map**, so `Line 1 - Small PET`
prints as `L1` and `Bottled Water - Small PET` prints as `SPET`.

### Counter scopes

Global · Per Year · Per Month · Per Day · Per Item · Per Item per Day ·
Per Line per Day · Per Line per Shift per Day.

Counters are allocated inside a row lock on `Batch Sequence Counter`, so two
concurrent Manufacture entries on the same line cannot take the same number.

### A note on the endpoints

`preview_rule` and `generate_combinations` accept a saved rule name, a dict, or
a JSON string, because `frappe.call` serialises a dict argument to JSON before
it crosses the wire. A draft that has never been saved is built with
`get_doc(dict)`, which never touches the database — that is what lets the
builder preview a rule that does not exist yet.

### Combination explorer

The tool's **Test All Combinations** action renders the full matrix of codes a
rule will produce across selected items, lines and shifts, and flags any two
combinations that collapse to the same code — which is the failure mode that
otherwise only surfaces after a week of production. Same check is available
from the rule form.

### Rule resolution

Item-specific beats Item Group, which beats Production Line, which beats All
Items. Ties break on priority, highest first. When no rule matches, the engine
stays out of the way and ERPNext's own `batch_number_series` on the item applies.

### Seeded rules

| Rule | Scope | Example |
|---|---|---|
| Small PET Line Coder | Line 1 | `B600260824L1A001` — compact, no separators, for the high-speed inkjet coder |
| Large PET Line Coder | Line 2 | `B15L-260824-L2-001` |
| Five Gallon Refill | Line 3 | `5G-260824-270220-001` — carries expiry, since 180-day shelf life is what the driver checks at the door |
| Default Batch Code | All items | `B600-260824-001` |

### Auto creation on manufacturing

With **Reserve Batch at Work Order Submit** enabled, the batch is created when
the work order is submitted, not when the finished goods are transferred. This
is what makes the QC gate workable — quality needs something to test against
before the transfer, and a batch that only exists at the moment of transfer is
too late. Cancelling a work order deletes the reserved batch if nothing has
moved against it.

The Manufacture stock entry then stamps that batch onto the finished item row
and carries work order, line, shift and manufacture date onto the batch record.

### Decoding

Because the composing rule is stored on each batch, `Decode Batch Code` on the
Batch form (and in the builder) splits an existing code back into its segments
— so a QA auditor can read a code off a bottle and recover the line, shift and
date without a lookup table.

---

## 12. Van POS — how the day actually runs

The salesman loads the van, drives his area, and at each customer decides the
quantity at the door. Two kinds of stop, and they are not the same transaction:

| Stop | What happens | Endpoint |
|---|---|---|
| **Van Sale** | Nobody ordered in advance. Quantity agreed at the door, stock off the van, invoice raised and printed on the spot. | `van_pos.van_sale` |
| **Order Delivery** | The customer phoned the office, so a Sales Order already exists. The invoice is made **from** the order, keeping the agreed prices and closing the order properly. | `van_pos.deliver_order` |

`Van Trip → Pull Pending Orders` adds a stop for every open Sales Order on the
route, so the salesman's obligations for the day are on his list rather than
communicated separately. Each stop carries a **Stop Type**, and every invoice
records a **Sale Type**, so van sales and order deliveries can be reported apart.

Short delivery is normal, so `deliver_order` accepts per-line quantities. An
override adjusts only the lines it names — lines the handheld does not mention
keep the ordered quantity. To drop a line, send it explicitly with qty 0.

### Collection is a separate transaction

Money at the door may settle today's invoice, older ones, part of either, or
none. `van_pos.collect` takes an amount and an optional allocation, and defaults
to **oldest invoice first** — which is what a salesman means by "he paid me two
hundred". Anything beyond the total outstanding stays on account as an advance
rather than being refused.

`van_pos.customer_outstanding` returns the aged list for the collection screen:
each invoice with its age in days and whether it is past due.

### Mobile endpoints

| Endpoint | Purpose |
|---|---|
| `route_plan` | The day: typed stops, pending orders per customer, outstanding balance, live van stock |
| `van_stock` | What is on the vehicle, with the van's price list applied |
| `van_sale` | Ad-hoc sale at the door, optional part payment |
| `deliver_order` | Invoice from a Sales Order, with short-delivery support |
| `customer_outstanding` | Aged invoice list for collections |
| `collect` | Payment against chosen invoices, or oldest-first |
| `receipt` | Print payload for the thermal printer |

A check-in is logged automatically when the handheld sends coordinates, so the
salesman is not asked to check in as a separate step before selling.

### The printed receipt

`NeoAqua Van Receipt 80mm` is a bilingual EN/AR simplified tax invoice sized for
a 72 mm print area on a mobile thermal printer: company VAT and SFDA numbers,
line detail, VAT breakdown, balance due when payment is partial, container
movement when relevant, and a signature line. It is set as the default print
format on the seeded van POS profiles.

If a KSA e-invoicing app is installed and populates `ksa_einv_qr`, the ZATCA QR
renders on the receipt. NeoAqua does not generate that QR itself — that belongs
to the compliance layer, not here.

---

## 13. NeoAqua Hub — the master workspace

`/app/neoaqua-hub` — the single entry point, linked from every workspace, from
the Control Tower and from Settings.

### It adapts to who is looking

The hub detects a persona from the user's roles and reorders itself around it:

| Roles | Persona | Opens on |
|---|---|---|
| Van Salesman, Van Supervisor | Field Sales | Distribution |
| Plant Operator, Manufacturing User | Plant | Production |
| QC Inspector, Quality Manager | Quality | Production |
| Accounts Manager / User, Cashier | Finance | Settlement |
| Purchase Manager / User | Procurement | Procurement |
| NeoAqua Manager, System Manager | Operations | Everything |

**Your work** sits at the top: three to five things this person should act on
now. A salesman sees today's trip with stops covered and value invoiced, or a
prompt to load the van if there is no trip. A QC inspector sees batches awaiting
release. An accountant sees receivables and day closes needing approval.

### The process map

Four lanes — Procure, Produce, Distribute, Settle — each a row of steps with a
live count, connected by animated flow lines. Click any step to open its list,
already filtered. Hovering a step explains what the number means: *"Arrived, not
yet invoiced"*, *"Failed — batches blocked"*, *"Cash stays unreconciled until
these settle"*.

Below it, module tiles for everything else, and one-tap create buttons.

### Permissions are enforced on the server

This is the part that matters. Every lane, node, tile, link and action is tested
with `frappe.has_permission` **before it is sent to the browser**. A user who
cannot read Van Trip never receives the Van Trip node — not a hidden one, not a
disabled one. It is not in the payload.

That extends to the counts, because a count is itself information: telling a
salesman there are fourteen unpaid purchase invoices leaks something he has no
right to know.

Three link types, three different checks:

* **DocType** — `has_permission(doctype)`.
* **Report** — permission follows the report's `ref_doctype`, plus the report's
  own role list. Checking `has_permission("Report")` would be wrong; that only
  says whether the user may edit report *definitions*.
* **Page** — the page's own role list, empty meaning public.

A tile whose links are all filtered out is dropped rather than shown empty, and
a user with no NeoAqua access at all gets a plain message telling them which
role to ask for.

---

## 14. Control Tower

`/app/neoaqua-control-tower` — the operational front door, linked from every
workspace and from NeoAqua Settings.

A workspace of links tells you where things are. This tells you what state they
are in. Everything on the page is live and clickable through to the underlying
list.

**Process rails.** The four stages of the business, each with the counts that
actually gate work:

| Rail | Shows |
|---|---|
| Procure to Pay | Open material requests, orders to receive, invoices to pay |
| Plan to Produce | Work orders in process, batches awaiting QC, units produced today |
| Load to Deliver | Vans on the road, visits logged today, invoices today |
| Settle and Collect | Trips awaiting day close, day closes pending approval, customers owing |

**KPI strip.** Sales and collections today, receivables, cash variance MTD,
seven-day QC pass rate, containers in the market, finished-goods value and
stock sitting on vans. Colour-coded by tone, so a negative cash variance and a
sub-95% pass rate read red without you hunting for them.

**Van board.** One row per active van: state (idle, loaded, on route, awaiting
day close, settled), a coverage bar with visited-over-planned stops, invoiced
against collected, and the value of stock on the vehicle. Click through to the
trip, or to the van when there is no trip today.

**Line board.** Seven-day attainment per production line, banded green above
97%, amber above 85%, red below.

**Needs attention.** Ranked by what it costs to ignore — failed quality checks
and unsettled trips first, then off-fence check-ins, cash variances and
near-expiry batches, then expired supplier CRs. Each row states the
consequence, not just the count: *"Batches are blocked from release."*

**Sales sparkline** for the last fourteen days, today highlighted.

The whole page is one API call — a cockpit that fires fifteen requests to draw
itself is a cockpit nobody leaves open. It refreshes every 90 seconds, and each
panel is computed in isolation, so a panel that cannot be built comes back
empty and names its error instead of taking the page down. If the plant is not
fully set up, a banner says so and links straight to setup, because otherwise
the numbers are quietly wrong rather than loudly absent.

---

## 15. Dashboards

| Dashboard | Contents |
|---|---|
| NeoAqua Sales | Daily sales value, sales by van, sales by channel, route coverage %, visit outcomes + 6 number cards |
| NeoAqua Manufacturing | Production by line, daily output, QC results + 4 number cards |
| NeoAqua Finance | Monthly revenue, cash variance trend, purchases by supplier + 4 number cards |

Three workspaces (`Water Sales & Distribution`, `Water Manufacturing`,
`Water Finance`) group the shortcuts, links and reports for each function.

## 16. Business Review — the management pack

`/app/neoaqua-business-review`. A board does not read fifteen reports; it reads
one document. This assembles that document from the same data the reports use.

| Section | Contents |
|---|---|
| Headline | Revenue with movement against the previous period *and* the same period last year, gross margin, collections as a percentage of revenue, receivables, units produced, cash variance |
| Summary | Sentences **generated from the numbers** — "1 route did not cover its own cost: Van 02" appears because the arithmetic found it, and stays silent when it did not |
| Sales by channel | Revenue, customers and invoice count per channel |
| Route performance | Trips, coverage, revenue, cost and net per route, negatives in red |
| Top products | By revenue |
| Production | Orders, planned, produced and yield per line, with QC pass rate |
| Customer movement | Who was won, who was lost, and what the lost ones were worth |
| Risks and exceptions | Over-90 receivables, cash shortages, failed QC, container exposure, expired supplier CRs |

**Four ways out.** Print (A4 layout), Download PDF, Download Excel (the
underlying tables, for anyone who wants to re-cut them), and Email — which puts
the review in the message body as well as attaching the PDF, so it reads on a
phone without opening anything.

Set **Monthly Review Recipients** in NeoAqua Settings and it goes out
automatically each month. Leave it empty and it never does.

---

## 17. Reports

**Sales**

* Sales Register (Van & Channel) — every invoice with van, salesman, channel, VAT, collected and outstanding
* Item-wise Sales and Margin — revenue against true cost of sales taken from the stock ledger, not today's valuation rate, so margin reflects what the goods actually cost when sold
* Customer Sales Trend — this period vs previous vs the same period last year, classifying each customer as New, Growing, Steady, Declining or **Lost**, with the value at risk
* Salesman Performance Scorecard — sales, collections, collection %, average drop size, coverage, strike rate, geofence adherence, cash variance and damage in one row

**Financial**

* Receivables Aging by Route — 0-30 / 31-60 / 61-90 / 90+ per customer, with route, salesman, credit limit and the amount over it
* Daily Cash and Sales Summary — the day book: gross, returns, VAT, cash vs credit, collections, route expenses, expected vs declared cash, variance, deposits
* VAT Summary (KSA) — monthly output and input VAT with the net position. A review of what the books say the return should look like; it is not a ZATCA submission

**Business analysis**

* Route and Van Profitability — revenue less cost of sales, route expenses and stock losses, per route. Revenue alone flatters a long route that burns fuel and loses stock; two routes selling the same can contribute very differently
* Customer Profitability and Cost to Serve — margin less the cost of visiting. A customer taking small drops on a long route, paying late and holding twenty containers can be unprofitable at a healthy gross margin
* Product Contribution and Pareto — contribution ranked with an ABC class from the cumulative curve. The A items justify a line slot and a safety stock; the C tail usually costs more in changeovers than it contributes
* Working Capital and Cash Cycle — DSO, inventory days, DPO and the cash conversion cycle by month. The number that governs how much cash the business needs to stand still

**Operational**

* Van Sales Summary — loaded vs invoiced vs collected, sell-through, coverage
* Salesman Day Close Variance — cash short/over with chart and summary
* Route Visit Compliance — coverage, geofence adherence, strike rate
* Customer Container Balance — containers in market and deposit exposure
* Production Yield and Scrap — yield %, planned vs actual cost per work order
* Batch QC Register — SFDA-ready batch release register
* Van Stock Position — live valued stock across all van warehouses

## 18. Roles

`NeoAqua Manager`, `Van Salesman`, `Van Supervisor`, `Plant Operator`,
`QC Inspector`, `Cashier - Water`, plus four role profiles.

A user holding only `Van Salesman` sees only their own Van Trips, Check-ins and
Day Closes — enforced through `permission_query_conditions` and `has_permission`,
not through UI hiding.

## 19. Mobile endpoints

`neoaqua/api/mobile.py` exposes whitelisted methods for a van salesman client.
Each resolves the caller's own Sales Person from the session user, so a salesman
cannot read or post against another van.

| Method | Purpose |
|---|---|
| `my_trip` | Open trip, live van stock with prices, remaining stops |
| `customer_snapshot` | Outstanding, credit limit, last invoice, containers held |
| `check_geofence` | Evaluate a coordinate against the customer's zone |
| `day_close_preview` | Settlement figures before cash is declared |
| `quick_check_in` | Create and submit a check-in in one call |

## 20. Configuration

All behaviour is driven from **NeoAqua Settings** (single doctype): default
warehouses, van sales controls, geofence enforcement level and radius,
returnable container item and deposit, QC gate, and SFDA / water source licence
numbers for print formats.

---

© 2026 Neotec Integrated Solutions, Riyadh, Kingdom of Saudi Arabia.
Commercial licence. All rights reserved.
