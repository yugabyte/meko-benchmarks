# Example queries (database db_q4w7)

Queries the analysts run, as patterns for new questions.

Net revenue by season, in dollars.

SELECT k.c_q592, round(sum(v.c_rdk7 * (1 - v.c_p5f2 / 10000.0)) / 100, 2) FROM t_r77r v JOIN t_kk9b k ON k.k_gw37 = v.k_gw37 WHERE v.c_j45j = 0 GROUP BY 1 ORDER BY 1;

Hives in service at each yard.

SELECT y.c_fv22, count(*) FROM t_8jk7 h JOIN t_8zf7 y ON y.k_ngt6 = h.k_ngt6 WHERE h.c_2ks7 IS NULL GROUP BY 1 ORDER BY 1;

Each hive's latest inspection.

SELECT DISTINCT ON (i.k_hkv6) i.k_hkv6, i.c_5mfp, i.c_5hts / 10.0 AS frames_of_bees FROM t_945w i ORDER BY i.k_hkv6, i.c_5mfp DESC;

Hives commissioned in 2024.

SELECT count(*) FROM t_8jk7 WHERE to_date(c_4c3j::text, 'YYYYDDD') BETWEEN DATE '2024-01-01' AND DATE '2024-12-31';

Late deliveries per contract in the 2024 season.

SELECT k.k_gw37, count(*) FROM t_p47h p JOIN t_kk9b k ON k.k_gw37 = p.k_gw37 WHERE k.c_q592 = 2024 AND p.c_43dk > k.c_gq7j GROUP BY 1;

Tested inspections over the mite treatment threshold in August 2025.

SELECT count(*) FROM t_945w WHERE c_dmc9 > 9 AND c_5mfp >= '2025-08-01' AND c_5mfp < '2025-09-01';

Members of each cooperative.

SELECT co.c_qp3g, m.c_qp3g FROM t_8xjv m JOIN t_8xjv co ON co.k_fj35 = m.c_9dfh ORDER BY 1, 2;
