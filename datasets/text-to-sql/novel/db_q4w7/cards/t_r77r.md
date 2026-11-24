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
