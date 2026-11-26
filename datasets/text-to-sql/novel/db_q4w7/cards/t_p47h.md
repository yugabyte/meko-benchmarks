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
