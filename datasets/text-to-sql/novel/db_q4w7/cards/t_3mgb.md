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
