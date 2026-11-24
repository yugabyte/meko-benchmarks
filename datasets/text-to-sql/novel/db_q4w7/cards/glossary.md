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
