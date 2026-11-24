#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6"]
# ///
"""Questions and gold SQL for the novel set, written in logical names and rendered to the random schema.

  ./novel_questions.py build    write novel/questions.json (then T2S_SET=novel ../verify_gold.py caches the gold results)
  ./novel_questions.py show     print each question with the first rows of its gold result
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from novel_db import DB, OUT  # noqa: E402
from novel_sql import render  # noqa: E402

NET = "v.[invoice.gross_c] * (1 - v.[invoice.disc_bp] / 10000.0)"
REV = "round(sum(" + NET + ") / 100, 2)"
VK = "[invoice] v JOIN [contract] k ON k.[contract.contract_id] = v.[invoice.contract_id]"
PK = "[placement] p JOIN [contract] k ON k.[contract.contract_id] = p.[placement.contract_id]"
LATEST = ("(SELECT DISTINCT ON (i.[inspection.hive_id]) i.* FROM [inspection] i "
          "ORDER BY i.[inspection.hive_id], i.[inspection.insp_ts] DESC)")
REGION = ("CASE {c} WHEN 1 THEN 'Upper Basin' WHEN 2 THEN 'Lower Basin' WHEN 3 THEN 'Eastern Foothills' "
          "WHEN 4 THEN 'Western Terraces' WHEN 5 THEN 'Delta' WHEN 6 THEN 'Highlands' END")
COMM = "to_date(h.[hive.commission_jd]::text, 'YYYYDDD')"
COOPS = "(SELECT [grower.parent_grower_id] FROM [grower] WHERE [grower.parent_grower_id] IS NOT NULL)"
DELIV = ("(SELECT k.[contract.contract_id] AS cid, k.[contract.hives_ord] AS ord, count(p.[placement.plc_id]) AS got "
         "FROM [contract] k LEFT JOIN [placement] p ON p.[placement.contract_id] = k.[contract.contract_id] "
         "WHERE k.[contract.status_cd] IN (3, 4) {w} GROUP BY 1, 2)")

S, M, H = "simple", "moderate", "challenging"
Q = [
    # ---------------------------------------------------------------- simple
    (S, "How many active growers are there, not counting cooperatives?",
     f"SELECT count(*) FROM [grower] g WHERE g.[grower.status_cd] = 'A' AND g.[grower.grower_id] NOT IN {COOPS}"),
    (S, "How many hives are in service?", "SELECT count(*) FROM [hive] WHERE [hive.retired_dt] IS NULL"),
    (S, "How many bee yards does the company own rather than lease?",
     "SELECT count(*) FROM [yard] WHERE [yard.lease_end_dt] IS NULL"),
    (S, "What is the total area, in hectares, of all almond blocks?",
     "SELECT sum(b.[block.area_ca]) / 100.0 FROM [block] b JOIN [crop] c ON c.[crop.crop_id] = b.[block.crop_id] "
     "WHERE c.[crop.crop_label] = 'Almond'"),
    (S, "How many inspections in 2025 found the colony queenless?",
     "SELECT count(*) FROM [inspection] WHERE [inspection.queen_cd] = 1 AND [inspection.insp_ts] >= '2025-01-01' "
     "AND [inspection.insp_ts] < '2026-01-01'"),
    (S, "List the codes of the bee yards in the Delta region.",
     "SELECT [yard.yard_code] FROM [yard] WHERE [yard.region_cd] = 5"),
    (S, "How many contracts for the 2023 season were cancelled?",
     "SELECT count(*) FROM [contract] WHERE [contract.season_yr] = 2023 AND [contract.status_cd] = 5"),
    (S, "How many hives were commissioned in 2021?",
     f"SELECT count(*) FROM [hive] h WHERE {COMM} BETWEEN DATE '2021-01-01' AND DATE '2021-12-31'"),
    (S, "What is the price per hive, in dollars, on contract 9050?",
     "SELECT [contract.rate_c] / 100.0 FROM [contract] WHERE [contract.contract_id] = 9050"),
    (S, "How many drivers currently work for the company?",
     "SELECT count(*) FROM [staff] WHERE [staff.role_cd] = 'D' AND [staff.end_dt] IS NULL"),
    (S, "How many Buckfast hives are in service?",
     "SELECT count(*) FROM [hive] WHERE [hive.stock_cd] = 3 AND [hive.retired_dt] IS NULL"),
    (S, "Which crop needs the most hives per hectare? Give the crop name.",
     "SELECT [crop.crop_label] FROM [crop] ORDER BY [crop.target_density] DESC LIMIT 1"),
    (S, "How many invoices have been voided?", "SELECT count(*) FROM [invoice] WHERE [invoice.void_flag] = 1"),
    (S, "How many growers are on the watch-list credit tier?",
     "SELECT count(*) FROM [grower] WHERE [grower.credit_tier] = 3"),
    (S, "How many blocks are not irrigated?", "SELECT count(*) FROM [block] WHERE [block.irrigated] = 0"),
    (S, "What was the highest mite load, in percent, found in any inspection in 2024? Round to 2 decimal places.",
     "SELECT round(max([inspection.mite_wash]) / 3.0, 2) FROM [inspection] WHERE [inspection.insp_ts] >= '2024-01-01' "
     "AND [inspection.insp_ts] < '2025-01-01'"),
    (S, "How many hives have been lost because the colony absconded?",
     "SELECT count(*) FROM [hive] WHERE [hive.retire_cd] = 2"),
    (S, "Which grower became a customer most recently? Give its name.",
     "SELECT [grower.legal_name] FROM [grower] ORDER BY [grower.onboard_dt] DESC LIMIT 1"),
    (S, "How many hives were delivered for the 2025 season?",
     f"SELECT count(*) FROM {PK} WHERE k.[contract.season_yr] = 2025"),
    (S, "How many contracts for the 2026 season are still only quotes?",
     "SELECT count(*) FROM [contract] WHERE [contract.season_yr] = 2026 AND [contract.status_cd] = 1"),
    (S, "How many valid credit notes have been issued?",
     "SELECT count(*) FROM [invoice] WHERE [invoice.inv_type] = 'C' AND [invoice.void_flag] = 0"),
    (S, "What is the total hive capacity of the yards in the Upper Basin region?",
     "SELECT sum([yard.capacity]) FROM [yard] WHERE [yard.region_cd] = 1"),
    (S, "How many staff left the company in 2025?",
     "SELECT count(*) FROM [staff] WHERE [staff.end_dt] BETWEEN DATE '2025-01-01' AND DATE '2025-12-31'"),
    (S, "What is the average elevation, in metres, of apple blocks? Round to 1 decimal place.",
     "SELECT round(avg(b.[block.elev_m]), 1) FROM [block] b JOIN [crop] c ON c.[crop.crop_id] = b.[block.crop_id] "
     "WHERE c.[crop.crop_label] = 'Apple'"),
    (S, "How many member growers does the Delta Orchard Collective have?",
     "SELECT count(*) FROM [grower] m JOIN [grower] co ON co.[grower.grower_id] = m.[grower.parent_grower_id] "
     "WHERE co.[grower.legal_name] = 'Delta Orchard Collective'"),
    (S, "How many inspections have been carried out by yard managers?",
     "SELECT count(*) FROM [inspection] i JOIN [staff] s ON s.[staff.staff_id] = i.[inspection.staff_id] "
     "WHERE s.[staff.role_cd] = 'M'"),
    (S, "How many hives are still out in the field?",
     "SELECT count(*) FROM [placement] WHERE [placement.out_dt] IS NULL"),
    (S, "What is the largest number of hives ordered on a single contract?",
     "SELECT max([contract.hives_ord]) FROM [contract]"),
    (S, "How many deposit invoices are still unpaid?",
     "SELECT count(*) FROM [invoice] WHERE [invoice.inv_type] = 'D' AND [invoice.void_flag] = 0 "
     "AND [invoice.paid_dt] IS NULL"),
    (S, "How many inspections were carried out in March 2025?",
     "SELECT count(*) FROM [inspection] WHERE [inspection.insp_ts] >= '2025-03-01' AND [inspection.insp_ts] < '2025-04-01'"),
    (S, "What percentage of inspections in 2024 included a mite test? Round to 1 decimal place.",
     "SELECT round(100.0 * count([inspection.mite_wash]) / count(*), 1) FROM [inspection] "
     "WHERE [inspection.insp_ts] >= '2024-01-01' AND [inspection.insp_ts] < '2025-01-01'"),
    (S, "How many hives in service have yard Y07 as their home yard?",
     "SELECT count(*) FROM [hive] h JOIN [yard] y ON y.[yard.yard_id] = h.[hive.yard_id] "
     "WHERE y.[yard.yard_code] = 'Y07' AND h.[hive.retired_dt] IS NULL"),
    (S, "What is the earliest bloom start date of any 2026-season contract?",
     "SELECT min([contract.bloom_start]) FROM [contract] WHERE [contract.season_yr] = 2026"),
    (S, "How many growers belong to a cooperative?",
     "SELECT count(*) FROM [grower] WHERE [grower.parent_grower_id] IS NOT NULL"),
    (S, "How many hives have been sold?", "SELECT count(*) FROM [hive] WHERE [hive.retire_cd] = 3"),
    (S, "How many hives in total are ordered on signed contracts for the 2026 season?",
     "SELECT sum([contract.hives_ord]) FROM [contract] WHERE [contract.season_yr] = 2026 AND [contract.status_cd] = 2"),
    (S, "How many kiwifruit blocks are there?",
     "SELECT count(*) FROM [block] b JOIN [crop] c ON c.[crop.crop_id] = b.[block.crop_id] "
     "WHERE c.[crop.crop_label] = 'Kiwifruit'"),
    (S, "How many contracts require grade A hives?", "SELECT count(*) FROM [contract] WHERE [contract.min_grade] = 'A'"),
    (S, "How many inspections found a drone-laying queen?",
     "SELECT count(*) FROM [inspection] WHERE [inspection.queen_cd] = 3"),
    (S, "What is the highest price per hive, in dollars, on any contract?",
     "SELECT max([contract.rate_c]) / 100.0 FROM [contract]"),
    # ---------------------------------------------------------------- moderate
    (M, "What was the net revenue, in dollars, for the 2024 season? Round to 2 decimal places.",
     f"SELECT {REV} FROM {VK} WHERE v.[invoice.void_flag] = 0 AND k.[contract.season_yr] = 2024"),
    (M, "What was the net revenue, in dollars, in fiscal year 2025? Round to 2 decimal places.",
     f"SELECT {REV} FROM [invoice] v WHERE v.[invoice.void_flag] = 0 "
     "AND v.[invoice.issued_dt] BETWEEN DATE '2024-07-01' AND DATE '2025-06-30'"),
    (M, "Which grower brought in the most net revenue for the 2025 season? Give the grower's name.",
     f"SELECT g.[grower.legal_name] FROM {VK} JOIN [grower] g ON g.[grower.grower_id] = k.[contract.grower_id] "
     f"WHERE v.[invoice.void_flag] = 0 AND k.[contract.season_yr] = 2025 GROUP BY g.[grower.grower_id], 1 "
     f"ORDER BY sum({NET}) DESC LIMIT 1"),
    (M, "How much money is outstanding, in dollars after discounts? Round to 2 decimal places.",
     f"SELECT {REV} FROM [invoice] v WHERE v.[invoice.void_flag] = 0 AND v.[invoice.inv_type] IN ('D', 'F') "
     "AND v.[invoice.paid_dt] IS NULL"),
    (M, "For the 2024 season, how many hives were delivered at each strength grade? List the grade and the number of hives.",
     f"SELECT p.[placement.grade_in], count(*) FROM {PK} WHERE k.[contract.season_yr] = 2024 GROUP BY 1"),
    (M, "How many hives were delivered late in the 2023 season?",
     f"SELECT count(*) FROM {PK} WHERE k.[contract.season_yr] = 2023 AND p.[placement.in_dt] > k.[contract.bloom_start]"),
    (M, "What percentage of the hives delivered for the 2025 season arrived on time? Round to 1 decimal place.",
     f"SELECT round(100.0 * count(*) FILTER (WHERE p.[placement.in_dt] <= k.[contract.bloom_start]) / count(*), 1) "
     f"FROM {PK} WHERE k.[contract.season_yr] = 2025"),
    (M, "Which driver delivered the most hives in calendar year 2025? Give the driver's full name.",
     "SELECT s.[staff.full_name] FROM [placement] p JOIN [staff] s ON s.[staff.staff_id] = p.[placement.staff_id] "
     "WHERE p.[placement.in_dt] BETWEEN DATE '2025-01-01' AND DATE '2025-12-31' GROUP BY s.[staff.staff_id], 1 "
     "ORDER BY count(*) DESC LIMIT 1"),
    (M, "What was the average number of frames of bees found in inspections in June 2025? Round to 2 decimal places.",
     "SELECT round(avg([inspection.fob_x10] / 10.0), 2) FROM [inspection] WHERE [inspection.insp_ts] >= '2025-06-01' "
     "AND [inspection.insp_ts] < '2025-07-01'"),
    (M, "Which yard has the most hives in service? Give the yard code.",
     "SELECT y.[yard.yard_code] FROM [hive] h JOIN [yard] y ON y.[yard.yard_id] = h.[hive.yard_id] "
     "WHERE h.[hive.retired_dt] IS NULL GROUP BY 1 ORDER BY count(*) DESC LIMIT 1"),
    (M, "How many hives in service were commissioned more than five years before 15 December 2025?",
     f"SELECT count(*) FROM [hive] h WHERE h.[hive.retired_dt] IS NULL AND {COMM} < DATE '2020-12-15'"),
    (M, "What was the total number of hive-days in the 2024 season?",
     f"SELECT sum(p.[placement.out_dt] - p.[placement.in_dt]) FROM {PK} WHERE k.[contract.season_yr] = 2024 "
     "AND p.[placement.out_dt] IS NOT NULL"),
    (M, "On average, how many days did a hive spend in the field on almond contracts? Count only hives that have been "
        "removed, and round to 1 decimal place.",
     f"SELECT round(avg(p.[placement.out_dt] - p.[placement.in_dt]), 1) FROM {PK} JOIN [block] b "
     "ON b.[block.block_id] = k.[contract.block_id] JOIN [crop] c ON c.[crop.crop_id] = b.[block.crop_id] "
     "WHERE c.[crop.crop_label] = 'Almond' AND p.[placement.out_dt] IS NOT NULL"),
    (M, "How many contracts in the 2024 and 2025 seasons received fewer hives than were ordered?",
     "SELECT count(*) FROM " + DELIV.format(w="AND k.[contract.season_yr] IN (2024, 2025)") + " d WHERE got < ord"),
    (M, "What was the total shortfall, in hives, for the 2025 season?",
     "SELECT sum(ord - got) FROM " + DELIV.format(w="AND k.[contract.season_yr] = 2025") + " d"),
    (M, "What is the total value, in dollars, of the signed contracts for the 2026 season?",
     "SELECT sum([contract.hives_ord] * [contract.rate_c]) / 100.0 FROM [contract] WHERE [contract.season_yr] = 2026 "
     "AND [contract.status_cd] = 2"),
    (M, "How many hives delivered in the 2024 season were below the contract's minimum grade?",
     f"SELECT count(*) FROM {PK} WHERE k.[contract.season_yr] = 2024 AND p.[placement.grade_in] > k.[contract.min_grade]"),
    (M, "Which crop received the most hives in the 2025 season? Give the crop name.",
     f"SELECT c.[crop.crop_label] FROM {PK} JOIN [block] b ON b.[block.block_id] = k.[contract.block_id] "
     "JOIN [crop] c ON c.[crop.crop_id] = b.[block.crop_id] WHERE k.[contract.season_yr] = 2025 GROUP BY 1 "
     "ORDER BY count(*) DESC LIMIT 1"),
    (M, "How many growers have at least one outstanding invoice?",
     f"SELECT count(DISTINCT k.[contract.grower_id]) FROM {VK} WHERE v.[invoice.void_flag] = 0 "
     "AND v.[invoice.inv_type] IN ('D', 'F') AND v.[invoice.paid_dt] IS NULL"),
    (M, "On average, how many days did growers take to pay deposit invoices? Use paid, valid deposits only and round to "
        "1 decimal place.",
     "SELECT round(avg([invoice.paid_dt] - [invoice.issued_dt]), 1) FROM [invoice] WHERE [invoice.inv_type] = 'D' "
     "AND [invoice.void_flag] = 0 AND [invoice.paid_dt] IS NOT NULL"),
    (M, "How many valid deposit and final invoices were paid late?",
     "SELECT count(*) FROM [invoice] WHERE [invoice.inv_type] IN ('D', 'F') AND [invoice.void_flag] = 0 "
     "AND [invoice.paid_dt] - [invoice.issued_dt] > 30"),
    (M, "For each cooperative that has members, how many member growers does it have? List the cooperative name and the count.",
     "SELECT co.[grower.legal_name], count(*) FROM [grower] m JOIN [grower] co "
     "ON co.[grower.grower_id] = m.[grower.parent_grower_id] GROUP BY 1"),
    (M, "What is the contract value, in dollars, of contract 9100?",
     "SELECT [contract.hives_ord] * [contract.rate_c] / 100.0 FROM [contract] WHERE [contract.contract_id] = 9100"),
    (M, "Which field inspector carried out the most inspections in 2025? Give the full name.",
     "SELECT s.[staff.full_name] FROM [inspection] i JOIN [staff] s ON s.[staff.staff_id] = i.[inspection.staff_id] "
     "WHERE s.[staff.role_cd] = 'I' AND i.[inspection.insp_ts] >= '2025-01-01' AND i.[inspection.insp_ts] < '2026-01-01' "
     "GROUP BY s.[staff.staff_id], 1 ORDER BY count(*) DESC LIMIT 1"),
    (M, "How many colony losses were there in 2024?",
     "SELECT count(*) FROM [hive] WHERE [hive.retire_cd] IN (1, 2) "
     "AND [hive.retired_dt] BETWEEN DATE '2024-01-01' AND DATE '2024-12-31'"),
    (M, "What percentage of retired hives were colony losses? Round to 1 decimal place.",
     "SELECT round(100.0 * count(*) FILTER (WHERE [hive.retire_cd] IN (1, 2)) / count(*), 1) FROM [hive] "
     "WHERE [hive.retired_dt] IS NOT NULL"),
    (M, "What was the average mite load, in percent, across tested inspections in September 2025? Round to 2 decimal places.",
     "SELECT round(avg([inspection.mite_wash] / 3.0), 2) FROM [inspection] WHERE [inspection.insp_ts] >= '2025-09-01' "
     "AND [inspection.insp_ts] < '2025-10-01' AND [inspection.mite_wash] IS NOT NULL"),
    (M, "How many hives in service had a queen problem at their latest inspection?",
     f"SELECT count(*) FROM {LATEST} l JOIN [hive] h ON h.[hive.hive_id] = l.[inspection.hive_id] "
     "WHERE h.[hive.retired_dt] IS NULL AND l.[inspection.queen_cd] IN (1, 2, 3)"),
    (M, "Which region's growers brought in the most net revenue for the 2025 season? Give the region name.",
     f"SELECT {REGION.format(c='g.[grower.region_cd]')} FROM {VK} JOIN [grower] g "
     "ON g.[grower.grower_id] = k.[contract.grower_id] WHERE v.[invoice.void_flag] = 0 AND k.[contract.season_yr] = 2025 "
     f"GROUP BY g.[grower.region_cd] ORDER BY sum({NET}) DESC LIMIT 1"),
    (M, "How many active growers, other than cooperatives, have no contract for the 2026 season?",
     f"SELECT count(*) FROM [grower] g WHERE g.[grower.status_cd] = 'A' AND g.[grower.grower_id] NOT IN {COOPS} "
     "AND NOT EXISTS (SELECT 1 FROM [contract] k WHERE k.[contract.grower_id] = g.[grower.grower_id] "
     "AND k.[contract.season_yr] = 2026)"),
    (M, "What was the average price per hive, in dollars, on almond contracts in the 2025 season? Exclude cancelled "
        "contracts and round to 2 decimal places.",
     "SELECT round(avg(k.[contract.rate_c]) / 100, 2) FROM [contract] k JOIN [block] b ON b.[block.block_id] = k.[contract.block_id] "
     "JOIN [crop] c ON c.[crop.crop_id] = b.[block.crop_id] WHERE c.[crop.crop_label] = 'Almond' "
     "AND k.[contract.season_yr] = 2025 AND k.[contract.status_cd] <> 5"),
    (M, "How many more hives were delivered in the 2025 season than in the 2023 season?",
     f"SELECT count(*) FILTER (WHERE k.[contract.season_yr] = 2025) - count(*) FILTER (WHERE k.[contract.season_yr] = 2023) "
     f"FROM {PK}"),
    (M, "Which grower has the largest total block area? Give the grower's name.",
     "SELECT g.[grower.legal_name] FROM [block] b JOIN [grower] g ON g.[grower.grower_id] = b.[block.grower_id] "
     "GROUP BY g.[grower.grower_id], 1 ORDER BY sum(b.[block.area_ca]) DESC LIMIT 1"),
    (M, "How many closed contracts in the 2025 season were understocked?",
     "SELECT count(*) FROM (SELECT k.[contract.contract_id], count(*) / (min(b.[block.area_ca]) / 100.0) AS rate, "
     "min(c.[crop.target_density]) AS target FROM " + PK + " JOIN [block] b ON b.[block.block_id] = k.[contract.block_id] "
     "JOIN [crop] c ON c.[crop.crop_id] = b.[block.crop_id] WHERE k.[contract.season_yr] = 2025 "
     "AND k.[contract.status_cd] = 4 GROUP BY 1) x WHERE rate < target"),
    (M, "How much was refunded through valid credit notes on 2024-season contracts, in dollars after discount? Give a "
        "positive amount rounded to 2 decimal places.",
     f"SELECT -{REV} FROM {VK} WHERE v.[invoice.void_flag] = 0 AND v.[invoice.inv_type] = 'C' "
     "AND k.[contract.season_yr] = 2024"),
    (M, "How many different hives were inspected at least once in November 2025?",
     "SELECT count(DISTINCT [inspection.hive_id]) FROM [inspection] WHERE [inspection.insp_ts] >= '2025-11-01' "
     "AND [inspection.insp_ts] < '2025-12-01'"),
    (M, "What was the average number of brood frames in Carniolan hives inspected in May 2025? Round to 2 decimal places.",
     "SELECT round(avg(i.[inspection.brood_fr]), 2) FROM [inspection] i JOIN [hive] h ON h.[hive.hive_id] = i.[inspection.hive_id] "
     "WHERE h.[hive.stock_cd] = 1 AND i.[inspection.insp_ts] >= '2025-05-01' AND i.[inspection.insp_ts] < '2025-06-01'"),
    (M, "What percentage of the hives delivered for the 2024 season were grade A? Round to 1 decimal place.",
     f"SELECT round(100.0 * count(*) FILTER (WHERE p.[placement.grade_in] = 'A') / count(*), 1) FROM {PK} "
     "WHERE k.[contract.season_yr] = 2024"),
    (M, "What were the first and last delivery dates for contract 9080? Give the first date, then the last.",
     "SELECT min([placement.in_dt]), max([placement.in_dt]) FROM [placement] WHERE [placement.contract_id] = 9080"),
    (M, "For each of the 2023, 2024 and 2025 seasons, how many contracts were closed? List the season and the count.",
     "SELECT [contract.season_yr], count(*) FROM [contract] WHERE [contract.status_cd] = 4 "
     "AND [contract.season_yr] BETWEEN 2023 AND 2025 GROUP BY 1"),
    (M, "How many hives commissioned in 2025 have already been retired?",
     f"SELECT count(*) FROM [hive] h WHERE {COMM} >= DATE '2025-01-01' AND h.[hive.retired_dt] IS NOT NULL"),
    (M, "What is the total area, in hectares, of the blocks covered by booked contracts for the 2025 season?",
     "SELECT sum(b.[block.area_ca]) / 100.0 FROM [contract] k JOIN [block] b ON b.[block.block_id] = k.[contract.block_id] "
     "WHERE k.[contract.season_yr] = 2025 AND k.[contract.status_cd] IN (2, 3, 4)"),
    (M, "How many different hives have been delivered to at least one contract?",
     "SELECT count(DISTINCT [placement.hive_id]) FROM [placement]"),
    (M, "How many contracts belong to growers who are currently suspended?",
     "SELECT count(*) FROM [contract] k JOIN [grower] g ON g.[grower.grower_id] = k.[contract.grower_id] "
     "WHERE g.[grower.status_cd] = 'S'"),
    (M, "How many inspections did each current yard manager carry out in 2025? List the full name and the count.",
     "SELECT s.[staff.full_name], count(*) FROM [inspection] i JOIN [staff] s ON s.[staff.staff_id] = i.[inspection.staff_id] "
     "WHERE s.[staff.role_cd] = 'M' AND s.[staff.end_dt] IS NULL AND i.[inspection.insp_ts] >= '2025-01-01' "
     "AND i.[inspection.insp_ts] < '2026-01-01' GROUP BY s.[staff.staff_id], 1"),
    (M, "What was the average number of frames of bees in inspections of Italian hives in 2024? Round to 2 decimal places.",
     "SELECT round(avg(i.[inspection.fob_x10] / 10.0), 2) FROM [inspection] i JOIN [hive] h "
     "ON h.[hive.hive_id] = i.[inspection.hive_id] WHERE h.[hive.stock_cd] = 2 AND i.[inspection.insp_ts] >= '2024-01-01' "
     "AND i.[inspection.insp_ts] < '2025-01-01'"),
    (M, "Which bee yard in the Delta region has the largest capacity? Give the yard code.",
     "SELECT [yard.yard_code] FROM [yard] WHERE [yard.region_cd] = 5 ORDER BY [yard.capacity] DESC LIMIT 1"),
    (M, "How many inspections were carried out by staff who have since left the company?",
     "SELECT count(*) FROM [inspection] p JOIN [staff] s ON s.[staff.staff_id] = p.[inspection.staff_id] "
     "WHERE s.[staff.end_dt] IS NOT NULL"),
    (M, "Which season had the highest average price per hive across closed contracts? Give the season.",
     "SELECT [contract.season_yr] FROM [contract] WHERE [contract.status_cd] = 4 GROUP BY 1 "
     "ORDER BY avg([contract.rate_c]) DESC LIMIT 1"),
    (M, "How many valid final invoices were issued in fiscal year 2024?",
     "SELECT count(*) FROM [invoice] WHERE [invoice.inv_type] = 'F' AND [invoice.void_flag] = 0 "
     "AND [invoice.issued_dt] BETWEEN DATE '2023-07-01' AND DATE '2024-06-30'"),
    # ---------------------------------------------------------------- challenging
    (H, "For each of the 2023, 2024 and 2025 seasons, what percentage of delivered hives arrived on time? List the season "
        "and the percentage rounded to 1 decimal place.",
     f"SELECT k.[contract.season_yr], round(100.0 * count(*) FILTER (WHERE p.[placement.in_dt] <= k.[contract.bloom_start]) "
     f"/ count(*), 1) FROM {PK} WHERE k.[contract.season_yr] BETWEEN 2023 AND 2025 GROUP BY 1"),
    (H, "Which grower had the largest total shortfall across the 2023 to 2025 seasons? Give the grower's name.",
     "SELECT g.[grower.legal_name] FROM " + DELIV.format(w="AND k.[contract.season_yr] BETWEEN 2023 AND 2025") +
     " d JOIN [contract] k ON k.[contract.contract_id] = d.cid JOIN [grower] g ON g.[grower.grower_id] = k.[contract.grower_id] "
     "GROUP BY g.[grower.grower_id], 1 ORDER BY sum(ord - got) DESC LIMIT 1"),
    (H, "How many hives were delivered to a contract in every season from 2023 to 2025?",
     f"SELECT count(*) FROM (SELECT p.[placement.hive_id] FROM {PK} WHERE k.[contract.season_yr] BETWEEN 2023 AND 2025 "
     "GROUP BY 1 HAVING count(DISTINCT k.[contract.season_yr]) = 3) x"),
    (H, "What percentage of the hives in service were strong at their latest inspection? Round to 1 decimal place.",
     f"SELECT round(100.0 * count(*) FILTER (WHERE l.[inspection.fob_x10] >= 80) / count(*), 1) FROM [hive] h "
     f"JOIN {LATEST} l ON l.[inspection.hive_id] = h.[hive.hive_id] WHERE h.[hive.retired_dt] IS NULL"),
    (H, "On average, how many days passed between consecutive inspections of the same hive in 2025? Use only pairs of "
        "inspections that both took place in 2025, count whole calendar days between the inspection dates, and round "
        "to 1 decimal place.",
     "SELECT round(avg(d), 1) FROM (SELECT [inspection.insp_ts]::date - lag([inspection.insp_ts]::date) OVER "
     "(PARTITION BY [inspection.hive_id] ORDER BY [inspection.insp_ts]) AS d FROM [inspection] "
     "WHERE [inspection.insp_ts] >= '2025-01-01' AND [inspection.insp_ts] < '2026-01-01') x WHERE d IS NOT NULL"),
    (H, "Which yard had the highest share of tested 2025 inspections over the mite treatment threshold? Count each "
        "inspection under the hive's home yard and give the yard code.",
     "SELECT y.[yard.yard_code] FROM [inspection] i JOIN [hive] h ON h.[hive.hive_id] = i.[inspection.hive_id] "
     "JOIN [yard] y ON y.[yard.yard_id] = h.[hive.yard_id] WHERE i.[inspection.mite_wash] IS NOT NULL "
     "AND i.[inspection.insp_ts] >= '2025-01-01' AND i.[inspection.insp_ts] < '2026-01-01' GROUP BY 1 "
     "ORDER BY avg(CASE WHEN i.[inspection.mite_wash] > 9 THEN 1.0 ELSE 0 END) DESC LIMIT 1"),
    (H, "What was the net revenue per hive delivered for the 2025 season, in dollars? Round to 2 decimal places.",
     f"SELECT round((SELECT sum({NET}) / 100 FROM {VK} WHERE v.[invoice.void_flag] = 0 AND k.[contract.season_yr] = 2025) "
     f"/ (SELECT count(*) FROM {PK} WHERE k.[contract.season_yr] = 2025), 2)"),
    (H, "For each cooperative whose members brought in net revenue for the 2024 season, how much did they bring in? List "
        "the cooperative name and the amount in dollars rounded to 2 decimal places.",
     f"SELECT co.[grower.legal_name], {REV} FROM {VK} JOIN [grower] m ON m.[grower.grower_id] = k.[contract.grower_id] "
     "JOIN [grower] co ON co.[grower.grower_id] = m.[grower.parent_grower_id] WHERE v.[invoice.void_flag] = 0 "
     "AND k.[contract.season_yr] = 2024 GROUP BY co.[grower.grower_id], 1"),
    (H, "Which crop had the highest average price per hive in the 2025 season, excluding cancelled contracts? Give the "
        "crop name.",
     "SELECT c.[crop.crop_label] FROM [contract] k JOIN [block] b ON b.[block.block_id] = k.[contract.block_id] "
     "JOIN [crop] c ON c.[crop.crop_id] = b.[block.crop_id] WHERE k.[contract.season_yr] = 2025 "
     "AND k.[contract.status_cd] <> 5 GROUP BY 1 ORDER BY avg(k.[contract.rate_c]) DESC LIMIT 1"),
    (H, "Among growers with net revenue in both the 2024 and 2025 seasons, how many brought in more in 2025 than in 2024?",
     f"SELECT count(*) FROM (SELECT k.[contract.grower_id], sum({NET}) FILTER (WHERE k.[contract.season_yr] = 2024) AS a, "
     f"sum({NET}) FILTER (WHERE k.[contract.season_yr] = 2025) AS b FROM {VK} WHERE v.[invoice.void_flag] = 0 "
     "GROUP BY 1) x WHERE a IS NOT NULL AND b IS NOT NULL AND b > a"),
    (H, "In which month of 2025 were the most tested inspections over the mite treatment threshold? Give the month number.",
     "SELECT extract(month FROM [inspection.insp_ts])::int FROM [inspection] WHERE [inspection.mite_wash] > 9 "
     "AND [inspection.insp_ts] >= '2025-01-01' AND [inspection.insp_ts] < '2026-01-01' GROUP BY 1 "
     "ORDER BY count(*) DESC LIMIT 1"),
    (H, "What is the median number of days growers took to pay final invoices? Use paid, valid final invoices and round "
        "to 1 decimal place.",
     "SELECT round(percentile_cont(0.5) WITHIN GROUP (ORDER BY [invoice.paid_dt] - [invoice.issued_dt])::numeric, 1) "
     "FROM [invoice] WHERE [invoice.inv_type] = 'F' AND [invoice.void_flag] = 0 AND [invoice.paid_dt] IS NOT NULL"),
    (H, "Which field inspector found the highest average mite load in 2025, among inspectors with at least 100 tested "
        "inspections that year? Give the full name.",
     "SELECT s.[staff.full_name] FROM [inspection] i JOIN [staff] s ON s.[staff.staff_id] = i.[inspection.staff_id] "
     "WHERE s.[staff.role_cd] = 'I' AND i.[inspection.mite_wash] IS NOT NULL AND i.[inspection.insp_ts] >= '2025-01-01' "
     "AND i.[inspection.insp_ts] < '2026-01-01' GROUP BY s.[staff.staff_id], 1 HAVING count(*) >= 100 "
     "ORDER BY avg(i.[inspection.mite_wash]) DESC LIMIT 1"),
    (H, "For hives retired as dead-outs in 2025, what was the average number of frames of bees at their last inspection? "
        "Round to 2 decimal places.",
     f"SELECT round(avg(l.[inspection.fob_x10] / 10.0), 2) FROM [hive] h JOIN {LATEST} l "
     "ON l.[inspection.hive_id] = h.[hive.hive_id] WHERE h.[hive.retire_cd] = 1 "
     "AND h.[hive.retired_dt] BETWEEN DATE '2025-01-01' AND DATE '2025-12-31'"),
    (H, "Which crop brought in the most net revenue per contracted hectare in the 2025 season? Use booked contracts only: "
        "the crop's net revenue on those contracts divided by the total area of their blocks. Give the crop name.",
     f"SELECT c.[crop.crop_label] FROM (SELECT k.[contract.contract_id] AS cid, sum({NET}) AS rev FROM {VK} "
     "WHERE v.[invoice.void_flag] = 0 GROUP BY 1) r JOIN [contract] k ON k.[contract.contract_id] = r.cid "
     "JOIN [block] b ON b.[block.block_id] = k.[contract.block_id] JOIN [crop] c ON c.[crop.crop_id] = b.[block.crop_id] "
     "WHERE k.[contract.season_yr] = 2025 AND k.[contract.status_cd] IN (2, 3, 4) GROUP BY 1 "
     "ORDER BY sum(r.rev) / sum(b.[block.area_ca]) DESC LIMIT 1"),
    (H, "How many hives in service have never been delivered to a contract?",
     "SELECT count(*) FROM [hive] h WHERE h.[hive.retired_dt] IS NULL AND NOT EXISTS (SELECT 1 FROM [placement] p "
     "WHERE p.[placement.hive_id] = h.[hive.hive_id])"),
    (H, "What is the average age, in days, of the hives in service on 15 December 2025? Round to the nearest whole day.",
     f"SELECT round(avg(DATE '2025-12-15' - {COMM})) FROM [hive] h WHERE h.[hive.retired_dt] IS NULL"),
    (H, "Which driver delivered the most late hives in the 2024 season? Give the full name.",
     f"SELECT s.[staff.full_name] FROM {PK} JOIN [staff] s ON s.[staff.staff_id] = p.[placement.staff_id] "
     "WHERE k.[contract.season_yr] = 2024 AND p.[placement.in_dt] > k.[contract.bloom_start] "
     "GROUP BY s.[staff.staff_id], 1 ORDER BY count(*) DESC LIMIT 1"),
    (H, "For the 2025 season, how many closed contracts were there for each minimum grade, and how many of them had at "
        "least one hive delivered below that grade? List the grade, the number of contracts and the number with a "
        "grade shortfall.",
     "SELECT k.[contract.min_grade], count(*), count(*) FILTER (WHERE EXISTS (SELECT 1 FROM [placement] p "
     "WHERE p.[placement.contract_id] = k.[contract.contract_id] AND p.[placement.grade_in] > k.[contract.min_grade])) "
     "FROM [contract] k WHERE k.[contract.season_yr] = 2025 AND k.[contract.status_cd] = 4 GROUP BY 1"),
    (H, "Which grower has the invoice that has been outstanding the longest as of 15 December 2025? Give the grower's name.",
     f"SELECT g.[grower.legal_name] FROM {VK} JOIN [grower] g ON g.[grower.grower_id] = k.[contract.grower_id] "
     "WHERE v.[invoice.void_flag] = 0 AND v.[invoice.inv_type] IN ('D', 'F') AND v.[invoice.paid_dt] IS NULL "
     "ORDER BY v.[invoice.issued_dt] LIMIT 1"),
    (H, "How much is outstanding for each credit tier, in dollars after discounts? List the tier and the amount rounded "
        "to 2 decimal places.",
     f"SELECT g.[grower.credit_tier], {REV} FROM {VK} JOIN [grower] g ON g.[grower.grower_id] = k.[contract.grower_id] "
     "WHERE v.[invoice.void_flag] = 0 AND v.[invoice.inv_type] IN ('D', 'F') AND v.[invoice.paid_dt] IS NULL GROUP BY 1"),
    (H, "For how many deliveries was the hive queenless at its last inspection before the delivery date?",
     "SELECT count(*) FROM [placement] p JOIN LATERAL (SELECT i.[inspection.queen_cd] AS q FROM [inspection] i "
     "WHERE i.[inspection.hive_id] = p.[placement.hive_id] AND i.[inspection.insp_ts] < p.[placement.in_dt] "
     "ORDER BY i.[inspection.insp_ts] DESC LIMIT 1) l ON true WHERE l.q = 1"),
    (H, "Among the Carniolan hives still in service, in which year were the most commissioned? Give the year.",
     f"SELECT extract(year FROM {COMM})::int FROM [hive] h WHERE h.[hive.retired_dt] IS NULL AND h.[hive.stock_cd] = 1 GROUP BY 1 "
     "ORDER BY count(*) DESC LIMIT 1"),
    (H, "Which cooperative's members own the largest total block area? Give the cooperative's name.",
     "SELECT co.[grower.legal_name] FROM [block] b JOIN [grower] m ON m.[grower.grower_id] = b.[block.grower_id] "
     "JOIN [grower] co ON co.[grower.grower_id] = m.[grower.parent_grower_id] GROUP BY co.[grower.grower_id], 1 "
     "ORDER BY sum(b.[block.area_ca]) DESC LIMIT 1"),
    (H, "What was the average stocking rate, in hives per hectare, of closed almond contracts in the 2025 season? Round "
        "to 2 decimal places.",
     f"SELECT round(avg(n / ha), 2) FROM (SELECT k.[contract.contract_id], count(*) AS n, min(b.[block.area_ca]) / 100.0 AS ha "
     f"FROM {PK} JOIN [block] b ON b.[block.block_id] = k.[contract.block_id] JOIN [crop] c "
     "ON c.[crop.crop_id] = b.[block.crop_id] WHERE c.[crop.crop_label] = 'Almond' AND k.[contract.season_yr] = 2025 "
     "AND k.[contract.status_cd] = 4 GROUP BY 1) x"),
    (H, "How many growers had booked contracts in each of the 2023, 2024 and 2025 seasons?",
     "SELECT count(*) FROM (SELECT [contract.grower_id] FROM [contract] WHERE [contract.status_cd] IN (2, 3, 4) "
     "AND [contract.season_yr] BETWEEN 2023 AND 2025 GROUP BY 1 HAVING count(DISTINCT [contract.season_yr]) = 3) x"),
    (H, "What percentage of the 2024 season's net revenue came from almond contracts? Round to 1 decimal place.",
     f"SELECT round(100 * sum({NET}) FILTER (WHERE c.[crop.crop_label] = 'Almond') / sum({NET}), 1) FROM {VK} "
     "JOIN [block] b ON b.[block.block_id] = k.[contract.block_id] JOIN [crop] c ON c.[crop.crop_id] = b.[block.crop_id] "
     "WHERE v.[invoice.void_flag] = 0 AND k.[contract.season_yr] = 2024"),
    (H, "For the 2025 season, how many hives were delivered to growers in each region? List the region name and the "
        "number of hives.",
     f"SELECT {REGION.format(c='g.[grower.region_cd]')}, count(*) FROM {PK} JOIN [grower] g "
     "ON g.[grower.grower_id] = k.[contract.grower_id] WHERE k.[contract.season_yr] = 2025 GROUP BY g.[grower.region_cd]"),
    (H, "On average, how many days before the bloom start were booked 2026-season contracts signed? Round to 1 decimal place.",
     "SELECT round(avg([contract.bloom_start] - [contract.signed_dt]), 1) FROM [contract] WHERE [contract.season_yr] = 2026 "
     "AND [contract.status_cd] IN (2, 3, 4)"),
    (H, "How many of the hives delivered for the 2025 season have since been retired?",
     f"SELECT count(DISTINCT p.[placement.hive_id]) FROM {PK} JOIN [hive] h ON h.[hive.hive_id] = p.[placement.hive_id] "
     "WHERE k.[contract.season_yr] = 2025 AND h.[hive.retired_dt] IS NOT NULL"),
]


def records():
    return [{"question_id": i + 1, "db_id": DB, "question": q, "evidence": "", "SQL": render(sql), "difficulty": d,
             "gold": "novel"} for i, (d, q, sql) in enumerate(Q)]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    recs = records()
    if cmd == "build":
        (OUT.parent / "questions.json").write_text(json.dumps(recs, indent=1))
        print(len(recs), "questions:", {d: sum(r["difficulty"] == d for r in recs) for d in (S, M, H)})
    else:
        import psycopg
        from common import dsn, execute
        with psycopg.connect(dsn(DB), autocommit=False) as c:
            for r in recs:
                rows, err = execute(c, r["SQL"])
                print(f"{r['question_id']:3d} {err or rows[:6]}{'' if err or len(rows) <= 6 else f' ...{len(rows)}'}")
