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
