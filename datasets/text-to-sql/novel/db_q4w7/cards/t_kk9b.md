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
