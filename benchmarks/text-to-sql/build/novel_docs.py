#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6"]
# ///
"""Documentation for the novel set: table cards (with value profiles), a business glossary and example queries.

Writes novel/<db>/cards/*.md (Meko knowledge base, one file per card), context.md (all cards, for
the in-prompt arm) and comments.json (table and column comments only, for the comments arm, served from
the file so the database itself carries no comments for the no-context arm to find).
Identifiers are written as plain text, never in backticks.
"""
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import dsn, execute  # noqa: E402
from novel_db import DB, OUT, PK, SCHEMA, C, T  # noqa: E402
from novel_sql import render  # noqa: E402

REGIONS = "1 = Upper Basin, 2 = Lower Basin, 3 = Eastern Foothills, 4 = Western Terraces, 5 = Delta, 6 = Highlands"

TABLE_DOC = {
    "crop": ("Crop reference list. One row per crop the company pollinates, with the recommended stocking density "
             "(hives per hectare) used to size orders.", ["block"]),
    "grower": ("Customers: fruit and seed growers who lease hives for the bloom, and the cooperatives some of them "
               "belong to. Cooperatives are rows of this table too: they own no blocks, and their members point to "
               "them through the parent grower column.", ["block", "contract"]),
    "block": ("Orchard blocks (fields) owned by growers. Each block grows one crop. Contracts are written per block "
              "and season.", ["grower", "crop", "contract"]),
    "yard": ("Bee yards (apiaries) where hives are kept when they are not out on a contract. Every hive has one home "
             "yard.", ["hive"]),
    "hive": ("Every hive (colony) the company has owned, in service or retired.", ["yard", "inspection", "placement"]),
    "staff": ("Employees: field inspectors, drivers, yard managers and office staff, current and former.",
              ["inspection", "placement"]),
    "inspection": ("Hive inspections. One row per inspection of one hive: colony strength, brood, mite test result "
                   "and queen status. Hives are inspected about monthly from February to November, and again a few "
                   "days before every delivery to a contract.", ["hive", "staff"]),
    "contract": ("Pollination contracts. One row per grower, block and bloom season: the hives ordered, the price per "
                 "hive, the minimum strength the grower requires, the bloom window and the contract status.",
                 ["grower", "block", "placement", "invoice"]),
    "placement": ("Hive placements: one row per hive delivered to a contract, with the delivery and removal dates, "
                  "the hive's strength grade at delivery and the driver who delivered it.",
                  ["contract", "hive", "staff"]),
    "invoice": ("Invoices and credit notes raised against contracts: a deposit at signing, a final invoice after the "
                "hives are removed, and credit notes for refunds.", ["contract"]),
}

COL_DOC = {
    "crop.crop_id": "Crop id. Joins to the block table's crop id.",
    "crop.crop_label": "Crop name.",
    "crop.target_density": "Recommended number of hives per hectare for this crop.",
    "grower.grower_id": "Grower id. Joins to block and contract.",
    "grower.legal_name": "Grower's registered business name.",
    "grower.region_cd": f"Region of the grower's head office. Codes: {REGIONS}.",
    "grower.status_cd": "Account status: A = active, S = suspended (payment hold, no new deliveries), X = closed (former customer).",
    "grower.onboard_dt": "Date the grower became a customer.",
    "grower.credit_tier": "Credit tier: 1 = preferred, 2 = standard, 3 = watch list (must prepay).",
    "grower.parent_grower_id": "For a cooperative member, the grower id of its cooperative (a row in this same table). Empty for cooperatives and independent growers.",
    "block.block_id": "Block id. Joins to contract.",
    "block.grower_id": "Owner of the block. Joins to grower.",
    "block.crop_id": "Crop grown on the block. Joins to crop.",
    "block.block_name": "Grower's own name for the block. Not unique.",
    "block.area_ca": "Block area in hundredths of a hectare (divide by 100 for hectares).",
    "block.irrigated": "1 = irrigated block, 0 = dryland.",
    "block.elev_m": "Elevation in metres.",
    "yard.yard_id": "Yard id. Joins to the hive table's home yard.",
    "yard.yard_code": "Short yard code, Y01 to Y14.",
    "yard.region_cd": f"Region the yard is in. Codes: {REGIONS}.",
    "yard.capacity": "Maximum number of hives the yard can hold.",
    "yard.lease_end_dt": "End date of the land lease. Empty means the company owns the yard.",
    "hive.hive_id": "Hive id. Joins to inspection and placement.",
    "hive.yard_id": "Home yard of the hive. Joins to yard.",
    "hive.commission_jd": "Date the hive was set up, as a number in YYYYDDD form: the year followed by the day of the year (2024032 is 1 February 2024). Convert with to_date(value::text, 'YYYYDDD').",
    "hive.stock_cd": "Bee stock (breed): 1 = Carniolan, 2 = Italian, 3 = Buckfast, 4 = local mixed stock.",
    "hive.retired_dt": "Date the hive was taken out of service. Empty means the hive is in service.",
    "hive.retire_cd": "Why the hive was retired: 1 = dead-out (colony died), 2 = absconded (colony left), 3 = sold, 4 = combined into another colony. Empty for hives in service.",
    "staff.staff_id": "Staff id. Joins to inspection (the inspector) and placement (the driver).",
    "staff.full_name": "Employee's full name.",
    "staff.role_cd": "Role: I = field inspector, D = driver, M = yard manager, O = office.",
    "staff.hire_dt": "Start date.",
    "staff.end_dt": "Leaving date. Empty for current staff.",
    "inspection.insp_id": "Inspection id.",
    "inspection.hive_id": "Hive inspected. Joins to hive.",
    "inspection.staff_id": "Who did the inspection. Joins to staff.",
    "inspection.insp_ts": "Date and time of the inspection.",
    "inspection.fob_x10": "Frames of bees (colony strength) times 10: 85 means 8.5 frames covered with bees.",
    "inspection.brood_fr": "Number of frames with brood.",
    "inspection.mite_wash": "Varroa mites counted in an alcohol wash of 300 bees. Empty when no mite test was done. Mite load in percent is this count divided by 3.",
    "inspection.queen_cd": "Queen status: 0 = queenright (laying queen seen), 1 = queenless, 2 = virgin or unmated queen, 3 = drone-laying queen, 9 = not checked.",
    "contract.contract_id": "Contract id. Joins to placement and invoice.",
    "contract.grower_id": "Customer. Joins to grower.",
    "contract.block_id": "Block to be pollinated. Joins to block.",
    "contract.season_yr": "Season: the calendar year of the bloom.",
    "contract.hives_ord": "Number of hives ordered.",
    "contract.rate_c": "Price per hive in cents.",
    "contract.min_grade": "Minimum hive strength grade the grower requires: A, B or C (see the grades in the glossary). A hive meets the requirement when its grade is the same or better (A is best).",
    "contract.status_cd": "Status: 1 = quoted, 2 = signed, 3 = in field (hives delivered, not all removed), 4 = closed (completed), 5 = cancelled.",
    "contract.bloom_start": "Expected first day of bloom. Hives should be in place by this date.",
    "contract.bloom_end": "Expected last day of bloom.",
    "contract.signed_dt": "Date the grower signed. Empty for quotes.",
    "placement.plc_id": "Placement id.",
    "placement.contract_id": "Contract the hive was delivered for. Joins to contract.",
    "placement.hive_id": "Hive delivered. Joins to hive.",
    "placement.in_dt": "Delivery date.",
    "placement.out_dt": "Removal date. Empty while the hive is still in the field.",
    "placement.grade_in": "Strength grade of the hive at delivery, from its pre-delivery inspection: A, B, C or R (reject).",
    "placement.staff_id": "Driver who delivered the hive. Joins to staff.",
    "invoice.inv_id": "Invoice number.",
    "invoice.contract_id": "Contract invoiced. Joins to contract.",
    "invoice.inv_type": "D = deposit (25% of the contract value, at signing), F = final invoice (after removal, for the hives actually delivered less the deposit), C = credit note (a refund, with a negative amount).",
    "invoice.issued_dt": "Issue date.",
    "invoice.gross_c": "Amount before discount, in cents. Negative for credit notes.",
    "invoice.disc_bp": "Discount in basis points (100 = 1%).",
    "invoice.paid_dt": "Date the invoice was paid in full; for a credit note, the date the refund was applied. Empty when not yet paid.",
    "invoice.void_flag": "1 = voided (issued in error and replaced by a new invoice); ignore voided invoices in every total. 0 = valid.",
}

GLOSSARY = """# Business glossary (database {db})

Definitions the business uses when it asks questions of this database. Data are current to 15 December 2025.

Regions. Region codes in the grower and yard tables: {regions}.

Active, suspended and closed growers. A grower is active when its status code is A, suspended when S and closed when X.

Cooperatives and members. A cooperative is a grower row that other growers point to through their parent grower column ({g}.{gpar}). Cooperatives own no blocks. A member grower is one whose parent grower column is filled; an independent grower has no parent and is not a cooperative.

Hectares. Block area is stored in hundredths of a hectare: hectares = {b}.{barea} / 100.

Hive in service. A hive is in service when its retired date ({h}.{hret}) is empty. Colony losses are hives retired as dead-outs or absconded (retire codes 1 and 2); sold and combined hives are not losses.

Hive age. A hive's commission date is stored as YYYYDDD ({h}.{hcomm}); convert with to_date({h}.{hcomm}::text, 'YYYYDDD').

Frames of bees and strength grades. Frames of bees = {i}.{ifob} / 10. Strength grade: A = 8.0 frames of bees or more, B = 6.0 to 7.9, C = 4.0 to 5.9, R (reject) = below 4.0. A hive is strong when it is grade A. A hive meets a contract's minimum grade when its grade is equal or better: a C contract accepts A, B and C, a B contract accepts A and B, an A contract accepts only A.

Mite load and treatment threshold. Mite load (%) = {i}.{imite} / 3 (mites per 100 bees). A hive is over the treatment threshold when its mite load is above 3%, that is more than 9 mites in the wash. Inspections with an empty mite count were not tested and are left out of mite statistics.

Queenright. An inspection is queenright when the queen code is 0. A hive with a queen problem has code 1, 2 or 3; code 9 means the queen was not checked.

Latest inspection. A hive's current strength, mite load or queen status comes from its most recent inspection ({i}.{its}).

Booked contracts. Contracts with status 2, 3 or 4 (signed, in field or closed); quotes (1) and cancelled contracts (5) are not booked.

Contract value. Hives ordered times the price per hive: {k}.{kord} * {k}.{krate} / 100 dollars.

Hives delivered and shortfall. Hives delivered to a contract is its number of placements. Shortfall = hives ordered minus hives delivered, for contracts in field or closed.

On-time and late delivery. A placement is on time when the hive was delivered on or before the contract's bloom start ({p}.{pin} <= {k}.{kbs}); otherwise it is late. A contract was delivered on time when all its placements were on time.

Hive-days. For a removed hive, the days it spent in the field: {p}.{pout} - {p}.{pin}. Hives still in the field are left out.

Stocking rate. Hives delivered per hectare of the block. A contract is understocked when its stocking rate is below the crop's target density ({cr}.{cdens}).

Grade shortfall. A placement whose grade at delivery is worse than the contract's minimum grade. The grower receives a credit note for half the price of each such hive.

Valid invoices. Voided invoices ({v}.{vvoid} = 1) are ignored in every total and count.

Net amount and revenue. Net amount of an invoice in dollars = {v}.{vgross} * (1 - {v}.{vdisc} / 10000.0) / 100. Revenue is the sum of the net amounts of valid invoices of all types, so credit notes reduce it. Revenue for a season uses the contract's season; revenue for a fiscal year uses the invoice issue date.

Fiscal year. The fiscal year runs from 1 July to 30 June and is named after the year it ends in: FY2025 is 1 July 2024 to 30 June 2025.

Outstanding invoices. Valid deposit and final invoices (types D and F) with no paid date. Credit notes are never outstanding.

Days to pay and late payment. Days to pay = paid date minus issue date. A paid invoice was paid late when it took more than 30 days.

Current staff. Staff with no leaving date. Inspectors are role I and drivers role D.
"""

EXAMPLES = [
    ("Net revenue by season, in dollars.",
     "SELECT k.[contract.season_yr], round(sum(v.[invoice.gross_c] * (1 - v.[invoice.disc_bp] / 10000.0)) / 100, 2) "
     "FROM [invoice] v JOIN [contract] k ON k.[contract.contract_id] = v.[invoice.contract_id] "
     "WHERE v.[invoice.void_flag] = 0 GROUP BY 1 ORDER BY 1"),
    ("Hives in service at each yard.",
     "SELECT y.[yard.yard_code], count(*) FROM [hive] h JOIN [yard] y ON y.[yard.yard_id] = h.[hive.yard_id] "
     "WHERE h.[hive.retired_dt] IS NULL GROUP BY 1 ORDER BY 1"),
    ("Each hive's latest inspection.",
     "SELECT DISTINCT ON (i.[inspection.hive_id]) i.[inspection.hive_id], i.[inspection.insp_ts], "
     "i.[inspection.fob_x10] / 10.0 AS frames_of_bees FROM [inspection] i "
     "ORDER BY i.[inspection.hive_id], i.[inspection.insp_ts] DESC"),
    ("Hives commissioned in 2024.",
     "SELECT count(*) FROM [hive] WHERE to_date([hive.commission_jd]::text, 'YYYYDDD') "
     "BETWEEN DATE '2024-01-01' AND DATE '2024-12-31'"),
    ("Late deliveries per contract in the 2024 season.",
     "SELECT k.[contract.contract_id], count(*) FROM [placement] p JOIN [contract] k "
     "ON k.[contract.contract_id] = p.[placement.contract_id] WHERE k.[contract.season_yr] = 2024 "
     "AND p.[placement.in_dt] > k.[contract.bloom_start] GROUP BY 1"),
    ("Tested inspections over the mite treatment threshold in August 2025.",
     "SELECT count(*) FROM [inspection] WHERE [inspection.mite_wash] > 9 "
     "AND [inspection.insp_ts] >= '2025-08-01' AND [inspection.insp_ts] < '2025-09-01'"),
    ("Members of each cooperative.",
     "SELECT co.[grower.legal_name], m.[grower.legal_name] FROM [grower] m JOIN [grower] co "
     "ON co.[grower.grower_id] = m.[grower.parent_grower_id] ORDER BY 1, 2"),
]


def profile(conn, t, col, typ):
    tab, c = T(t), C(t, col)
    rows, _ = execute(conn, f"SELECT count(DISTINCT {c}), count(*) - count({c}), count(*), min({c})::text, max({c})::text FROM {tab}")
    nd, nulls, n, lo, hi = rows[0]
    bits = [typ, f"~{nd} distinct"]
    if nulls:
        bits.append(f"{round(100 * nulls / n)}% empty")
    if nd <= 10:
        top, _ = execute(conn, f"SELECT {c}::text, count(*) FROM {tab} WHERE {c} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC")
        tot = sum(r[1] for r in top)
        bits.append("values: " + ", ".join(f"'{v}' ({round(100 * k / tot)}%)" for v, k in top))
    elif lo is not None and typ != "text":
        bits.append(f"range {lo} to {hi}")
    elif typ == "text":
        top, _ = execute(conn, f"SELECT {c} FROM {tab} WHERE {c} IS NOT NULL ORDER BY {c} LIMIT 3")
        bits.append("e.g. " + ", ".join(f"'{r[0]}'" for r in top))
    return "; ".join(bits)


def main():
    cards = OUT / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    for f in cards.glob("*.md"):
        f.unlink()
    comments = {"tables": {}}
    texts = []
    with psycopg.connect(dsn(DB), autocommit=False) as conn:
        for t, cols in SCHEMA.items():
            desc, related = TABLE_DOC[t]
            n = execute(conn, f"SELECT count(*) FROM {T(t)}")[0][0][0]
            lines = [f"# Table {T(t)} (database {DB})", "", f"{desc} Usual joins: " + "; ".join(
                f"{T(r)} on {', '.join(C(t, c) for c, _ in cols if c in {x for x, _ in SCHEMA[r]} and c in (PK[r], PK[t]))}"
                for r in related) + ".", "",
                f"About {n} rows. Primary key: {C(t, cols[0][0])}. No foreign key constraints are declared.", "", "Columns:", ""]
            comments["tables"][T(t)] = {"comment": desc, "columns": {}}
            for col, typ in cols:
                doc = COL_DOC[f"{t}.{col}"]
                comments["tables"][T(t)]["columns"][C(t, col)] = doc
                lines += [f"{T(t)}.{C(t, col)} ({profile(conn, t, col, typ)}): {doc}", ""]
            text = "\n".join(lines)
            (cards / f"{T(t)}.md").write_text(text)
            texts.append(text)
    sub = {"db": DB, "regions": REGIONS, "g": T("grower"), "gpar": C("grower", "parent_grower_id"),
           "b": T("block"), "barea": C("block", "area_ca"), "h": T("hive"), "hret": C("hive", "retired_dt"),
           "hcomm": C("hive", "commission_jd"), "i": T("inspection"), "ifob": C("inspection", "fob_x10"),
           "imite": C("inspection", "mite_wash"), "its": C("inspection", "insp_ts"), "k": T("contract"),
           "kord": C("contract", "hives_ord"), "krate": C("contract", "rate_c"), "kbs": C("contract", "bloom_start"),
           "p": T("placement"), "pin": C("placement", "in_dt"), "pout": C("placement", "out_dt"), "cr": T("crop"),
           "cdens": C("crop", "target_density"), "v": T("invoice"), "vvoid": C("invoice", "void_flag"),
           "vgross": C("invoice", "gross_c"), "vdisc": C("invoice", "disc_bp")}
    gl = GLOSSARY.format(**sub)
    (cards / "glossary.md").write_text(gl)
    ex = [f"# Example queries (database {DB})", "", "Queries the analysts run, as patterns for new questions.", ""]
    with psycopg.connect(dsn(DB), autocommit=False) as conn:
        for title, sql in EXAMPLES:
            s = render(sql)
            rows, err = execute(conn, s)
            assert err is None, (title, err)
            ex += [f"{title}", "", s + ";", ""]
    ex = "\n".join(ex)
    (cards / "examples.md").write_text(ex)
    head = f"# Database {DB}: tables, columns, value profiles, business terms and example queries\n\n"
    (OUT / "context.md").write_text(head + "\n\n".join(texts + [gl, ex]))
    (OUT / "comments.json").write_text(json.dumps(comments, indent=1))
    print("context.md", len((OUT / "context.md").read_text()), "chars;", len(list(cards.glob("*.md"))), "cards")


if __name__ == "__main__":
    main()
