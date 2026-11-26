# Table t_z66c (database db_q4w7)

Crop reference list. One row per crop the company pollinates, with the recommended stocking density (hives per hectare) used to size orders. Usual joins: t_3mgb on k_q4xd.

About 8 rows. Primary key: k_q4xd. No foreign key constraints are declared.

Columns:

t_z66c.k_q4xd (smallint; ~8 distinct; values: '11' (12%), '12' (12%), '13' (12%), '14' (12%), '15' (12%), '16' (12%), '17' (12%), '18' (12%)): Crop id. Joins to the block table's crop id.

t_z66c.c_352q (text; ~8 distinct; values: 'Almond' (12%), 'Apple' (12%), 'Canola seed' (12%), 'European plum' (12%), 'Highbush blueberry' (12%), 'Kiwifruit' (12%), 'Pear' (12%), 'Sweet cherry' (12%)): Crop name.

t_z66c.c_xhk2 (numeric(4,1); ~6 distinct; values: '2.0' (25%), '2.5' (25%), '3.0' (12%), '5.0' (12%), '7.5' (12%), '8.0' (12%)): Recommended number of hives per hectare for this crop.
