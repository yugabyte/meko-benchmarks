# Database db_q4w7: tables, columns, value profiles, business terms and example queries

# Table t_z66c (database db_q4w7)

Crop reference list. One row per crop the company pollinates, with the recommended stocking density (hives per hectare) used to size orders. Usual joins: t_3mgb on k_q4xd.

About 8 rows. Primary key: k_q4xd. No foreign key constraints are declared.

Columns:

t_z66c.k_q4xd (smallint; ~8 distinct; values: '11' (12%), '12' (12%), '13' (12%), '14' (12%), '15' (12%), '16' (12%), '17' (12%), '18' (12%)): Crop id. Joins to the block table's crop id.

t_z66c.c_352q (text; ~8 distinct; values: 'Almond' (12%), 'Apple' (12%), 'Canola seed' (12%), 'European plum' (12%), 'Highbush blueberry' (12%), 'Kiwifruit' (12%), 'Pear' (12%), 'Sweet cherry' (12%)): Crop name.

t_z66c.c_xhk2 (numeric(4,1); ~6 distinct; values: '2.0' (25%), '2.5' (25%), '3.0' (12%), '5.0' (12%), '7.5' (12%), '8.0' (12%)): Recommended number of hives per hectare for this crop.


# Table t_8xjv (database db_q4w7)

Customers: fruit and seed growers who lease hives for the bloom, and the cooperatives some of them belong to. Cooperatives are rows of this table too: they own no blocks, and their members point to them through the parent grower column. Usual joins: t_3mgb on k_fj35; t_kk9b on k_fj35.

About 53 rows. Primary key: k_fj35. No foreign key constraints are declared.

Columns:

t_8xjv.k_fj35 (integer; ~53 distinct; range 1001 to 1127): Grower id. Joins to block and contract.

t_8xjv.c_qp3g (text; ~53 distinct; e.g. 'Amberley Growers', 'Ashgrove Fruit Co', 'Brackley Partners'): Grower's registered business name.

t_8xjv.c_2b7q (smallint; ~6 distinct; values: '5' (30%), '3' (25%), '4' (15%), '6' (13%), '2' (9%), '1' (8%)): Region of the grower's head office. Codes: 1 = Upper Basin, 2 = Lower Basin, 3 = Eastern Foothills, 4 = Western Terraces, 5 = Delta, 6 = Highlands.

t_8xjv.c_5dx4 (char(1); ~3 distinct; values: 'A' (79%), 'S' (13%), 'X' (8%)): Account status: A = active, S = suspended (payment hold, no new deliveries), X = closed (former customer).

t_8xjv.c_5q2z (date; ~52 distinct; range 2012-02-23 to 2024-02-18): Date the grower became a customer.

t_8xjv.c_wts6 (smallint; ~3 distinct; values: '2' (45%), '1' (34%), '3' (21%)): Credit tier: 1 = preferred, 2 = standard, 3 = watch list (must prepay).

t_8xjv.c_9dfh (integer; ~4 distinct; 66% empty; values: '1006' (44%), '1004' (28%), '1011' (17%), '1008' (11%)): For a cooperative member, the grower id of its cooperative (a row in this same table). Empty for cooperatives and independent growers.


# Table t_3mgb (database db_q4w7)

Orchard blocks (fields) owned by growers. Each block grows one crop. Contracts are written per block and season. Usual joins: t_8xjv on k_fj35; t_z66c on k_q4xd; t_kk9b on k_8r54.

About 119 rows. Primary key: k_8r54. No foreign key constraints are declared.

Columns:

t_3mgb.k_8r54 (integer; ~119 distinct; range 5001 to 5119): Block id. Joins to contract.

t_3mgb.k_fj35 (integer; ~48 distinct; range 1014 to 1127): Owner of the block. Joins to grower.

t_3mgb.k_q4xd (smallint; ~8 distinct; values: '11' (24%), '18' (17%), '16' (13%), '14' (13%), '13' (12%), '12' (10%), '17' (8%), '15' (3%)): Crop grown on the block. Joins to crop.

t_3mgb.c_v34z (text; ~84 distinct; e.g. 'Bend 10', 'Bend 11', 'Bend 2'): Grower's own name for the block. Not unique.

t_3mgb.c_9p5v (integer; ~116 distinct; range 90 to 3984): Block area in hundredths of a hectare (divide by 100 for hectares).

t_3mgb.c_c4rw (smallint; ~2 distinct; values: '1' (75%), '0' (25%)): 1 = irrigated block, 0 = dryland.

t_3mgb.c_j52k (integer; ~114 distinct; range 51 to 899): Elevation in metres.


# Table t_8zf7 (database db_q4w7)

Bee yards (apiaries) where hives are kept when they are not out on a contract. Every hive has one home yard. Usual joins: t_8jk7 on k_ngt6.

About 14 rows. Primary key: k_ngt6. No foreign key constraints are declared.

Columns:

t_8zf7.k_ngt6 (integer; ~14 distinct; range 301 to 314): Yard id. Joins to the hive table's home yard.

t_8zf7.c_fv22 (text; ~14 distinct; e.g. 'Y01', 'Y02', 'Y03'): Short yard code, Y01 to Y14.

t_8zf7.c_mkm8 (smallint; ~5 distinct; values: '5' (29%), '1' (29%), '2' (21%), '4' (14%), '3' (7%)): Region the yard is in. Codes: 1 = Upper Basin, 2 = Lower Basin, 3 = Eastern Foothills, 4 = Western Terraces, 5 = Delta, 6 = Highlands.

t_8zf7.c_623g (integer; ~10 distinct; values: '150' (14%), '180' (14%), '100' (14%), '210' (14%), '90' (7%), '130' (7%), '230' (7%), '200' (7%), '120' (7%), '220' (7%)): Maximum number of hives the yard can hold.

t_8zf7.c_758d (date; ~5 distinct; 64% empty; values: '2026-11-03' (20%), '2026-11-29' (20%), '2027-12-20' (20%), '2031-08-26' (20%), '2031-12-13' (20%)): End date of the land lease. Empty means the company owns the yard.


# Table t_8jk7 (database db_q4w7)

Every hive (colony) the company has owned, in service or retired. Usual joins: t_8zf7 on k_ngt6; t_945w on k_hkv6; t_p47h on k_hkv6.

About 2000 rows. Primary key: k_hkv6. No foreign key constraints are declared.

Columns:

t_8jk7.k_hkv6 (integer; ~2000 distinct; range 20001 to 22000): Hive id. Joins to inspection and placement.

t_8jk7.k_ngt6 (integer; ~14 distinct; range 301 to 314): Home yard of the hive. Joins to yard.

t_8jk7.c_4c3j (integer; ~1389 distinct; range 2018060 to 2025120): Date the hive was set up, as a number in YYYYDDD form: the year followed by the day of the year (2024032 is 1 February 2024). Convert with to_date(value::text, 'YYYYDDD').

t_8jk7.c_p2rg (smallint; ~4 distinct; values: '1' (34%), '2' (29%), '3' (20%), '4' (16%)): Bee stock (breed): 1 = Carniolan, 2 = Italian, 3 = Buckfast, 4 = local mixed stock.

t_8jk7.c_2ks7 (date; ~357 distinct; 79% empty; range 2022-06-07 to 2025-11-30): Date the hive was taken out of service. Empty means the hive is in service.

t_8jk7.c_q4p6 (smallint; ~4 distinct; 79% empty; values: '1' (52%), '4' (24%), '2' (15%), '3' (10%)): Why the hive was retired: 1 = dead-out (colony died), 2 = absconded (colony left), 3 = sold, 4 = combined into another colony. Empty for hives in service.


# Table t_ckp3 (database db_q4w7)

Employees: field inspectors, drivers, yard managers and office staff, current and former. Usual joins: t_945w on k_7sk8; t_p47h on k_7sk8.

About 30 rows. Primary key: k_7sk8. No foreign key constraints are declared.

Columns:

t_ckp3.k_7sk8 (integer; ~30 distinct; range 71 to 100): Staff id. Joins to inspection (the inspector) and placement (the driver).

t_ckp3.c_zcd9 (text; ~30 distinct; e.g. 'Aino Brannigan', 'Anouk Zielinski', 'Bastien Szabo'): Employee's full name.

t_ckp3.c_kdc3 (char(1); ~4 distinct; values: 'I' (43%), 'D' (30%), 'O' (13%), 'M' (13%)): Role: I = field inspector, D = driver, M = yard manager, O = office.

t_ckp3.c_2r6q (date; ~30 distinct; range 2013-03-16 to 2024-05-15): Start date.

t_ckp3.c_7q9x (date; ~2 distinct; 93% empty; values: '2024-06-05' (50%), '2025-07-19' (50%)): Leaving date. Empty for current staff.


# Table t_945w (database db_q4w7)

Hive inspections. One row per inspection of one hive: colony strength, brood, mite test result and queen status. Hives are inspected about monthly from February to November, and again a few days before every delivery to a contract. Usual joins: t_8jk7 on k_hkv6; t_ckp3 on k_7sk8.

About 50651 rows. Primary key: c_z8pq. No foreign key constraints are declared.

Columns:

t_945w.c_z8pq (integer; ~50651 distinct; range 700001 to 750651): Inspection id.

t_945w.k_hkv6 (integer; ~1945 distinct; range 20001 to 22000): Hive inspected. Joins to hive.

t_945w.k_7sk8 (integer; ~17 distinct; range 71 to 96): Who did the inspection. Joins to staff.

t_945w.c_5mfp (timestamp; ~35426 distinct; range 2023-01-26 07:00:00 to 2025-11-30 16:50:00): Date and time of the inspection.

t_945w.c_5hts (integer; ~136 distinct; range 15 to 150): Frames of bees (colony strength) times 10: 85 means 8.5 frames covered with bees.

t_945w.c_2pp4 (smallint; ~12 distinct; range 1 to 12): Number of frames with brood.

t_945w.c_dmc9 (integer; ~39 distinct; 34% empty; range 0 to 39): Varroa mites counted in an alcohol wash of 300 bees. Empty when no mite test was done. Mite load in percent is this count divided by 3.

t_945w.c_m4bv (smallint; ~5 distinct; values: '0' (88%), '9' (4%), '1' (4%), '2' (3%), '3' (1%)): Queen status: 0 = queenright (laying queen seen), 1 = queenless, 2 = virgin or unmated queen, 3 = drone-laying queen, 9 = not checked.


# Table t_kk9b (database db_q4w7)

Pollination contracts. One row per grower, block and bloom season: the hives ordered, the price per hive, the minimum strength the grower requires, the bloom window and the contract status. Usual joins: t_8xjv on k_fj35; t_3mgb on k_8r54; t_p47h on k_gw37; t_r77r on k_gw37.

About 149 rows. Primary key: k_gw37. No foreign key constraints are declared.

Columns:

t_kk9b.k_gw37 (integer; ~149 distinct; range 9001 to 9149): Contract id. Joins to placement and invoice.

t_kk9b.k_fj35 (integer; ~46 distinct; range 1014 to 1127): Customer. Joins to grower.

t_kk9b.k_8r54 (integer; ~95 distinct; range 5001 to 5117): Block to be pollinated. Joins to block.

t_kk9b.c_q592 (smallint; ~4 distinct; values: '2025' (27%), '2026' (26%), '2023' (24%), '2024' (23%)): Season: the calendar year of the bloom.

t_kk9b.c_266t (integer; ~64 distinct; range 4 to 90): Number of hives ordered.

t_kk9b.c_6jv8 (integer; ~130 distinct; range 6800 to 25850): Price per hive in cents.

t_kk9b.c_tk45 (char(1); ~3 distinct; values: 'B' (50%), 'A' (42%), 'C' (8%)): Minimum hive strength grade the grower requires: A, B or C (see the grades in the glossary). A hive meets the requirement when its grade is the same or better (A is best).

t_kk9b.c_zj29 (smallint; ~5 distinct; values: '4' (68%), '1' (14%), '2' (11%), '5' (6%), '3' (1%)): Status: 1 = quoted, 2 = signed, 3 = in field (hives delivered, not all removed), 4 = closed (completed), 5 = cancelled.

t_kk9b.c_gq7j (date; ~118 distinct; range 2023-02-05 to 2026-11-11): Expected first day of bloom. Hives should be in place by this date.

t_kk9b.c_nrd5 (date; ~125 distinct; range 2023-03-05 to 2026-12-24): Expected last day of bloom.

t_kk9b.c_n8jr (date; ~119 distinct; 14% empty; range 2022-09-04 to 2026-08-01): Date the grower signed. Empty for quotes.


# Table t_p47h (database db_q4w7)

Hive placements: one row per hive delivered to a contract, with the delivery and removal dates, the hive's strength grade at delivery and the driver who delivered it. Usual joins: t_kk9b on k_gw37; t_8jk7 on k_hkv6; t_ckp3 on k_7sk8.

About 3431 rows. Primary key: c_rcd6. No foreign key constraints are declared.

Columns:

t_p47h.c_rcd6 (integer; ~3431 distinct; range 400001 to 403431): Placement id.

t_p47h.k_gw37 (integer; ~102 distinct; range 9001 to 9111): Contract the hive was delivered for. Joins to contract.

t_p47h.k_hkv6 (integer; ~1713 distinct; range 20001 to 21999): Hive delivered. Joins to hive.

t_p47h.c_43dk (date; ~302 distinct; range 2023-01-30 to 2025-11-12): Delivery date.

t_p47h.c_2qbr (date; ~286 distinct; 1% empty; range 2023-03-05 to 2025-12-13): Removal date. Empty while the hive is still in the field.

t_p47h.c_3knh (char(1); ~4 distinct; values: 'A' (59%), 'B' (34%), 'C' (7%), 'R' (0%)): Strength grade of the hive at delivery, from its pre-delivery inspection: A, B, C or R (reject).

t_p47h.k_7sk8 (integer; ~9 distinct; values: '84' (12%), '91' (12%), '90' (11%), '88' (11%), '89' (11%), '87' (11%), '92' (11%), '86' (10%), '85' (10%)): Driver who delivered the hive. Joins to staff.


# Table t_r77r (database db_q4w7)

Invoices and credit notes raised against contracts: a deposit at signing, a final invoice after the hives are removed, and credit notes for refunds. Usual joins: t_kk9b on k_gw37.

About 297 rows. Primary key: c_5dd6. No foreign key constraints are declared.

Columns:

t_r77r.c_5dd6 (integer; ~297 distinct; range 88001 to 88297): Invoice number.

t_r77r.k_gw37 (integer; ~117 distinct; range 9001 to 9117): Contract invoiced. Joins to contract.

t_r77r.c_9q3t (char(1); ~3 distinct; values: 'D' (40%), 'F' (35%), 'C' (24%)): D = deposit (25% of the contract value, at signing), F = final invoice (after removal, for the hives actually delivered less the deposit), C = credit note (a refund, with a negative amount).

t_r77r.c_9kvq (date; ~250 distinct; range 2022-09-08 to 2025-11-23): Issue date.

t_r77r.c_rdk7 (bigint; ~284 distinct; range -175688 to 1138750): Amount before discount, in cents. Negative for credit notes.

t_r77r.c_p5f2 (integer; ~6 distinct; values: '0' (74%), '250' (11%), '500' (4%), '300' (4%), '100' (4%), '750' (2%)): Discount in basis points (100 = 1%).

t_r77r.c_7w32 (date; ~231 distinct; 13% empty; range 2022-10-24 to 2025-11-20): Date the invoice was paid in full; for a credit note, the date the refund was applied. Empty when not yet paid.

t_r77r.c_j45j (smallint; ~2 distinct; values: '0' (97%), '1' (3%)): 1 = voided (issued in error and replaced by a new invoice); ignore voided invoices in every total. 0 = valid.


# Business glossary (database db_q4w7)

Definitions the business uses when it asks questions of this database. Data are current to 15 December 2025.

Regions. Region codes in the grower and yard tables: 1 = Upper Basin, 2 = Lower Basin, 3 = Eastern Foothills, 4 = Western Terraces, 5 = Delta, 6 = Highlands.

Active, suspended and closed growers. A grower is active when its status code is A, suspended when S and closed when X.

Cooperatives and members. A cooperative is a grower row that other growers point to through their parent grower column (t_8xjv.c_9dfh). Cooperatives own no blocks. A member grower is one whose parent grower column is filled; an independent grower has no parent and is not a cooperative.

Hectares. Block area is stored in hundredths of a hectare: hectares = t_3mgb.c_9p5v / 100.

Hive in service. A hive is in service when its retired date (t_8jk7.c_2ks7) is empty. Colony losses are hives retired as dead-outs or absconded (retire codes 1 and 2); sold and combined hives are not losses.

Hive age. A hive's commission date is stored as YYYYDDD (t_8jk7.c_4c3j); convert with to_date(t_8jk7.c_4c3j::text, 'YYYYDDD').

Frames of bees and strength grades. Frames of bees = t_945w.c_5hts / 10. Strength grade: A = 8.0 frames of bees or more, B = 6.0 to 7.9, C = 4.0 to 5.9, R (reject) = below 4.0. A hive is strong when it is grade A. A hive meets a contract's minimum grade when its grade is equal or better: a C contract accepts A, B and C, a B contract accepts A and B, an A contract accepts only A.

Mite load and treatment threshold. Mite load (%) = t_945w.c_dmc9 / 3 (mites per 100 bees). A hive is over the treatment threshold when its mite load is above 3%, that is more than 9 mites in the wash. Inspections with an empty mite count were not tested and are left out of mite statistics.

Queenright. An inspection is queenright when the queen code is 0. A hive with a queen problem has code 1, 2 or 3; code 9 means the queen was not checked.

Latest inspection. A hive's current strength, mite load or queen status comes from its most recent inspection (t_945w.c_5mfp).

Booked contracts. Contracts with status 2, 3 or 4 (signed, in field or closed); quotes (1) and cancelled contracts (5) are not booked.

Contract value. Hives ordered times the price per hive: t_kk9b.c_266t * t_kk9b.c_6jv8 / 100 dollars.

Hives delivered and shortfall. Hives delivered to a contract is its number of placements. Shortfall = hives ordered minus hives delivered, for contracts in field or closed.

On-time and late delivery. A placement is on time when the hive was delivered on or before the contract's bloom start (t_p47h.c_43dk <= t_kk9b.c_gq7j); otherwise it is late. A contract was delivered on time when all its placements were on time.

Hive-days. For a removed hive, the days it spent in the field: t_p47h.c_2qbr - t_p47h.c_43dk. Hives still in the field are left out.

Stocking rate. Hives delivered per hectare of the block. A contract is understocked when its stocking rate is below the crop's target density (t_z66c.c_xhk2).

Grade shortfall. A placement whose grade at delivery is worse than the contract's minimum grade. The grower receives a credit note for half the price of each such hive.

Valid invoices. Voided invoices (t_r77r.c_j45j = 1) are ignored in every total and count.

Net amount and revenue. Net amount of an invoice in dollars = t_r77r.c_rdk7 * (1 - t_r77r.c_p5f2 / 10000.0) / 100. Revenue is the sum of the net amounts of valid invoices of all types, so credit notes reduce it. Revenue for a season uses the contract's season; revenue for a fiscal year uses the invoice issue date.

Fiscal year. The fiscal year runs from 1 July to 30 June and is named after the year it ends in: FY2025 is 1 July 2024 to 30 June 2025.

Outstanding invoices. Valid deposit and final invoices (types D and F) with no paid date. Credit notes are never outstanding.

Days to pay and late payment. Days to pay = paid date minus issue date. A paid invoice was paid late when it took more than 30 days.

Current staff. Staff with no leaving date. Inspectors are role I and drivers role D.


# Example queries (database db_q4w7)

Queries the analysts run, as patterns for new questions.

Net revenue by season, in dollars.

SELECT k.c_q592, round(sum(v.c_rdk7 * (1 - v.c_p5f2 / 10000.0)) / 100, 2) FROM t_r77r v JOIN t_kk9b k ON k.k_gw37 = v.k_gw37 WHERE v.c_j45j = 0 GROUP BY 1 ORDER BY 1;

Hives in service at each yard.

SELECT y.c_fv22, count(*) FROM t_8jk7 h JOIN t_8zf7 y ON y.k_ngt6 = h.k_ngt6 WHERE h.c_2ks7 IS NULL GROUP BY 1 ORDER BY 1;

Each hive's latest inspection.

SELECT DISTINCT ON (i.k_hkv6) i.k_hkv6, i.c_5mfp, i.c_5hts / 10.0 AS frames_of_bees FROM t_945w i ORDER BY i.k_hkv6, i.c_5mfp DESC;

Hives commissioned in 2024.

SELECT count(*) FROM t_8jk7 WHERE to_date(c_4c3j::text, 'YYYYDDD') BETWEEN DATE '2024-01-01' AND DATE '2024-12-31';

Late deliveries per contract in the 2024 season.

SELECT k.k_gw37, count(*) FROM t_p47h p JOIN t_kk9b k ON k.k_gw37 = p.k_gw37 WHERE k.c_q592 = 2024 AND p.c_43dk > k.c_gq7j GROUP BY 1;

Tested inspections over the mite treatment threshold in August 2025.

SELECT count(*) FROM t_945w WHERE c_dmc9 > 9 AND c_5mfp >= '2025-08-01' AND c_5mfp < '2025-09-01';

Members of each cooperative.

SELECT co.c_qp3g, m.c_qp3g FROM t_8xjv m JOIN t_8xjv co ON co.k_fj35 = m.c_9dfh ORDER BY 1, 2;
