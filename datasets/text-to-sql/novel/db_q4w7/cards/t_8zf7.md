# Table t_8zf7 (database db_q4w7)

Bee yards (apiaries) where hives are kept when they are not out on a contract. Every hive has one home yard. Usual joins: t_8jk7 on k_ngt6.

About 14 rows. Primary key: k_ngt6. No foreign key constraints are declared.

Columns:

t_8zf7.k_ngt6 (integer; ~14 distinct; range 301 to 314): Yard id. Joins to the hive table's home yard.

t_8zf7.c_fv22 (text; ~14 distinct; e.g. 'Y01', 'Y02', 'Y03'): Short yard code, Y01 to Y14.

t_8zf7.c_mkm8 (smallint; ~5 distinct; values: '5' (29%), '1' (29%), '2' (21%), '4' (14%), '3' (7%)): Region the yard is in. Codes: 1 = Upper Basin, 2 = Lower Basin, 3 = Eastern Foothills, 4 = Western Terraces, 5 = Delta, 6 = Highlands.

t_8zf7.c_623g (integer; ~10 distinct; values: '150' (14%), '180' (14%), '100' (14%), '210' (14%), '90' (7%), '130' (7%), '230' (7%), '200' (7%), '120' (7%), '220' (7%)): Maximum number of hives the yard can hold.

t_8zf7.c_758d (date; ~5 distinct; 64% empty; values: '2026-11-03' (20%), '2026-11-29' (20%), '2027-12-20' (20%), '2031-08-26' (20%), '2031-12-13' (20%)): End date of the land lease. Empty means the company owns the yard.
