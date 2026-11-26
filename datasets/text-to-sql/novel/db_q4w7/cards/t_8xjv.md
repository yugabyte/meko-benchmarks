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
