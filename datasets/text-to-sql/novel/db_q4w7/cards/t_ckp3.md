# Table t_ckp3 (database db_q4w7)

Employees: field inspectors, drivers, yard managers and office staff, current and former. Usual joins: t_945w on k_7sk8; t_p47h on k_7sk8.

About 30 rows. Primary key: k_7sk8. No foreign key constraints are declared.

Columns:

t_ckp3.k_7sk8 (integer; ~30 distinct; range 71 to 100): Staff id. Joins to inspection (the inspector) and placement (the driver).

t_ckp3.c_zcd9 (text; ~30 distinct; e.g. 'Aino Brannigan', 'Anouk Zielinski', 'Bastien Szabo'): Employee's full name.

t_ckp3.c_kdc3 (char(1); ~4 distinct; values: 'I' (43%), 'D' (30%), 'O' (13%), 'M' (13%)): Role: I = field inspector, D = driver, M = yard manager, O = office.

t_ckp3.c_2r6q (date; ~30 distinct; range 2013-03-16 to 2024-05-15): Start date.

t_ckp3.c_7q9x (date; ~2 distinct; 93% empty; values: '2024-06-05' (50%), '2025-07-19' (50%)): Leaving date. Empty for current staff.
