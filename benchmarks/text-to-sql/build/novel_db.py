#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["psycopg[binary]==3.3.6"]
# ///
"""The novel set: one invented database that no model can have seen, with random table and column names.

The business is a pollination contractor that leases bee hives to fruit growers for the bloom. Table
and column names are random tokens, codes are numeric or single letters, the database name is neutral,
and there are no foreign key constraints: the meaning lives only in the documentation, as in a real
legacy system. Data are generated from a fixed seed.

  ./novel_db.py build     create and load the database (drops it first if present)
  ./novel_db.py names     print the logical -> random name map
"""
import datetime as dt
import json
import math
import random
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import DATA, YB_HOST, YB_PORT  # noqa: E402

DB = "db_q4w7"
OUT = DATA / "novel" / DB
TODAY = dt.date(2025, 12, 15)
D = dt.date

# Logical schema: table -> [(column, type)]. Join keys keep one name across tables (a common
# convention even in cryptic schemas); every other name is random.
SCHEMA = {
    "crop": [("crop_id", "smallint"), ("crop_label", "text"), ("target_density", "numeric(4,1)")],
    "grower": [("grower_id", "integer"), ("legal_name", "text"), ("region_cd", "smallint"), ("status_cd", "char(1)"),
               ("onboard_dt", "date"), ("credit_tier", "smallint"), ("parent_grower_id", "integer")],
    "block": [("block_id", "integer"), ("grower_id", "integer"), ("crop_id", "smallint"), ("block_name", "text"),
              ("area_ca", "integer"), ("irrigated", "smallint"), ("elev_m", "integer")],
    "yard": [("yard_id", "integer"), ("yard_code", "text"), ("region_cd", "smallint"), ("capacity", "integer"),
             ("lease_end_dt", "date")],
    "hive": [("hive_id", "integer"), ("yard_id", "integer"), ("commission_jd", "integer"), ("stock_cd", "smallint"),
             ("retired_dt", "date"), ("retire_cd", "smallint")],
    "staff": [("staff_id", "integer"), ("full_name", "text"), ("role_cd", "char(1)"), ("hire_dt", "date"),
              ("end_dt", "date")],
    "inspection": [("insp_id", "integer"), ("hive_id", "integer"), ("staff_id", "integer"), ("insp_ts", "timestamp"),
                   ("fob_x10", "integer"), ("brood_fr", "smallint"), ("mite_wash", "integer"), ("queen_cd", "smallint")],
    "contract": [("contract_id", "integer"), ("grower_id", "integer"), ("block_id", "integer"), ("season_yr", "smallint"),
                 ("hives_ord", "integer"), ("rate_c", "integer"), ("min_grade", "char(1)"), ("status_cd", "smallint"),
                 ("bloom_start", "date"), ("bloom_end", "date"), ("signed_dt", "date")],
    "placement": [("plc_id", "integer"), ("contract_id", "integer"), ("hive_id", "integer"), ("in_dt", "date"),
                  ("out_dt", "date"), ("grade_in", "char(1)"), ("staff_id", "integer")],
    "invoice": [("inv_id", "integer"), ("contract_id", "integer"), ("inv_type", "char(1)"), ("issued_dt", "date"),
                ("gross_c", "bigint"), ("disc_bp", "integer"), ("paid_dt", "date"), ("void_flag", "smallint")],
}
PK = {t: cols[0][0] for t, cols in SCHEMA.items()}
SHARED = {"crop_id", "grower_id", "block_id", "yard_id", "hive_id", "staff_id", "contract_id"}

_nr = random.Random(90210)
_used = set()


def token(prefix):
    """A random name with no vowels and at least one digit, so it spells nothing."""
    alpha = "bcdfghjkmnpqrstvwxz"
    while True:
        s = "".join(_nr.choice(alpha + "23456789") for _ in range(4))
        if any(c.isdigit() for c in s) and any(c.isalpha() for c in s) and s not in _used:
            _used.add(s)
            return f"{prefix}{s}"


TABLES = {t: token("t_") for t in SCHEMA}
COLS = {}
for t, cols in SCHEMA.items():
    for c, _ in cols:
        if c in SHARED:
            COLS.setdefault(("*", c), token("k_"))
            COLS[(t, c)] = COLS[("*", c)]
        else:
            COLS[(t, c)] = token("c_")


def T(t):
    return TABLES[t]


def C(t, c):
    return COLS[(t, c)]


# ---------------------------------------------------------------- data
rng = random.Random(41177)

CROPS = [  # id, label, target hives per hectare, bloom (month, day) start and length, base rate in cents
    (11, "Almond", 5.0, (2, 12), 32, 21000), (12, "Sweet cherry", 2.5, (3, 22), 28, 9500),
    (13, "Apple", 2.0, (4, 12), 28, 8000), (14, "Highbush blueberry", 7.5, (4, 6), 42, 11000),
    (15, "Kiwifruit", 8.0, (11, 8), 40, 12500), (16, "Pear", 2.0, (3, 26), 28, 8000),
    (17, "European plum", 2.5, (3, 16), 25, 8500), (18, "Canola seed", 3.0, (5, 2), 38, 7000),
]
CROP_W = [30, 14, 12, 10, 8, 9, 8, 9]

WORDS1 = ["Harlow", "Bramwell", "Tennant", "Okafor", "Linden", "Quarry Hill", "Sable", "Marrowby", "Ashgrove", "Fennick",
          "Corrigan", "Vossler", "Whitlock", "Amberley", "Duskwater", "Pellow", "Ruddock", "Stannard", "Tolliver", "Yarrowby",
          "Garnock", "Hesketh", "Ingleby", "Jessop", "Kittering", "Lamorna", "Mattock", "Northolt", "Ottery", "Pendrell",
          "Quenby", "Rosling", "Saltash", "Thwaite", "Ullswick", "Varga", "Wendell", "Brackley", "Cawdor", "Dunmore",
          "Elsworth", "Farrant", "Gilmour", "Hollins", "Ivory Creek", "Juniper Flat", "Kestle", "Larkspur", "Morrow Bend",
          "Nethercott"]
SUFF = ["Farms", "Orchards", "Growers", "Holdings", "Estate", "& Sons", "Partners", "Fruit Co"]
COOPS = ["Upper Basin Fruit Cooperative", "Foothill Growers Cooperative", "Delta Orchard Collective",
         "Terrace Producers Union", "Highland Stonefruit Cooperative"]
FIRST = ["Aino", "Bastien", "Cerys", "Dariusz", "Eamon", "Freya", "Gideon", "Halima", "Ivo", "Jolene", "Kasimir", "Leocadia",
         "Mateus", "Nerys", "Orrin", "Priya", "Quillon", "Rosalind", "Soren", "Tamsin", "Ulrich", "Vesna", "Wilf", "Ximena",
         "Yusuf", "Zelda", "Anouk", "Bram", "Clio", "Dov"]
LAST = ["Abernethy", "Brannigan", "Castellano", "Dworak", "Eklund", "Fairweather", "Gruber", "Hallorann", "Iwasaki",
        "Jablonski", "Kowalczyk", "Lindqvist", "Moreau", "Nakamura", "Oyelaran", "Pirelli", "Quintero", "Rasmussen",
        "Szabo", "Thorne", "Underhill", "Valdivia", "Whitcombe", "Yilmaz", "Zielinski", "Achterberg", "Bellweather",
        "Crowhurst", "Dimitrov", "Esterhazy"]
PLACES = ["North", "South", "Creek", "Ridge", "Flat", "Terrace", "Hollow", "Bend", "Top", "River", "Old", "New", "Long",
          "Mill", "Gate"]


def rdate(a, b):
    return a + dt.timedelta(days=rng.randint(0, (b - a).days))


def poisson(lam):
    if lam > 30:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def grade(fob10):
    return "A" if fob10 >= 80 else "B" if fob10 >= 60 else "C" if fob10 >= 40 else "R"


def build_data():
    data = {t: [] for t in SCHEMA}
    data["crop"] = [(c[0], c[1], c[2]) for c in CROPS]
    crop = {c[0]: c for c in CROPS}

    # growers: cooperatives first (no blocks of their own), then farms
    gid = 1001
    coop_ids = []
    for name in COOPS:
        reg = {"Upper": 1, "Footh": 3, "Delta": 5, "Terra": 4, "Highl": 6}[name[:5]]
        data["grower"].append([gid, name, reg, "A", rdate(D(2012, 1, 1), D(2016, 12, 31)), 1, None])
        coop_ids.append((gid, reg))
        gid += rng.randint(1, 3)
    names = rng.sample(WORDS1, 48)
    for i, w in enumerate(names):
        status = rng.choices("ASX", [80, 12, 8])[0]
        member = rng.random() < 0.45
        parent, reg = (rng.choice(coop_ids) if member else (None, rng.choices(range(1, 7), [20, 18, 16, 16, 17, 13])[0]))
        if member and rng.random() < 0.2:
            reg = rng.randint(1, 6)
        data["grower"].append([gid, f"{w} {rng.choice(SUFF)}", reg, status, rdate(D(2015, 1, 1), D(2024, 9, 30)),
                               rng.choices([1, 2, 3], [35, 45, 20])[0], parent])
        gid += rng.randint(1, 4)
    growers = {g[0]: g for g in data["grower"]}
    farms = [g for g in data["grower"] if g[0] not in {c for c, _ in coop_ids}]

    # blocks
    bid = 5001
    for g in farms:
        for _ in range(rng.choices([1, 2, 3, 4, 5], [25, 30, 22, 13, 10])[0]):
            cid = rng.choices([c[0] for c in CROPS], CROP_W)[0]
            area = rng.randint(80, 1800) if cid != 18 else rng.randint(900, 4200)
            data["block"].append([bid, g[0], cid, f"{rng.choice(PLACES)} {rng.randint(1, 12)}", area,
                                  1 if rng.random() < 0.7 else 0, rng.randint(40, 900)])
            bid += 1

    # yards
    for i in range(1, 15):
        data["yard"].append([300 + i, f"Y{i:02d}", rng.choices(range(1, 7), [3, 3, 2, 2, 2, 2])[0],
                             rng.randrange(80, 260, 10), None if rng.random() < 0.5 else rdate(D(2026, 3, 1), D(2031, 12, 31))])
    yards = [y[0] for y in data["yard"]]

    # staff
    names = set()
    sid = 71
    roles = ["I"] * 13 + ["D"] * 9 + ["M"] * 4 + ["O"] * 4
    for r in roles:
        while True:
            n = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if n not in names:
                names.add(n)
                break
        hire = rdate(D(2013, 1, 1), D(2024, 6, 30))
        end = rdate(max(hire + dt.timedelta(days=200), D(2023, 6, 1)), D(2025, 10, 31)) if rng.random() < 0.2 else None
        data["staff"].append([sid, n, r, hire, end])
        sid += 1
    staff = data["staff"]

    def on_duty(role, day):
        pool = [s for s in staff if s[2] in role and s[3] <= day and (s[4] is None or s[4] >= day)]
        return rng.choice(pool)[0]

    # hives
    hives = {}
    for i in range(2000):
        hid = 20001 + i
        comm = rdate(D(2018, 3, 1), D(2025, 4, 30))
        retired = rcd = None
        if rng.random() < 0.2:
            retired = rdate(max(comm + dt.timedelta(days=60), D(2022, 6, 1)), D(2025, 12, 1))
            rcd = rng.choices([1, 2, 3, 4], [55, 15, 10, 20])[0]
        stock = rng.choices([1, 2, 3, 4], [35, 30, 20, 15])[0]
        hives[hid] = {"comm": comm, "ret": retired, "mult": math.exp(rng.gauss(0, 0.45)),
                      "s": {y: min(14, max(2.5, rng.gauss(8.3 + (0.6 if stock == 3 else 0), 2.0))) for y in range(2022, 2027)}}
        data["hive"].append([hid, rng.choice(yards), int(comm.strftime("%Y%j")), stock, retired, rcd])

    season_f = {1: .72, 2: .75, 3: .86, 4: 1.0, 5: 1.08, 6: 1.15, 7: 1.1, 8: 1.0, 9: .9, 10: .82, 11: .76, 12: .72}

    def fob(hid, day):
        return max(10, min(150, round(hives[hid]["s"][day.year] * season_f[day.month] * rng.gauss(1, .09) * 10)))

    def mite(hid, day):
        lam = (0.4 + 0.85 * max(0, day.month - 2)) * hives[hid]["mult"]
        return poisson(lam)

    def live(hid, a, b):
        h = hives[hid]
        return h["comm"] <= a and (h["ret"] is None or h["ret"] > b)

    insp = []  # (hive, staff, ts, fob, brood, mite, queen)

    def inspect(hid, day, pre=False):
        f = fob(hid, day)
        ts = dt.datetime.combine(day, dt.time(rng.randint(7, 16), rng.choice([0, 10, 15, 20, 30, 40, 45, 50])))
        tested = rng.random() < (0.92 if pre else 0.62)
        q = rng.choices([0, 1, 2, 3, 9], [88, 4, 3, 1, 4])[0]
        brood = max(0, min(12, round(f / 10 * rng.uniform(.45, .8))))
        insp.append((hid, on_duty("I" if rng.random() < 0.9 else "M", day), ts, f, brood,
                     mite(hid, day) if tested else None, q))
        return f

    # routine inspections
    for hid, h in hives.items():
        day = max(h["comm"] + dt.timedelta(days=rng.randint(5, 30)), D(2023, 1, 20) + dt.timedelta(days=rng.randint(0, 25)))
        while day <= TODAY and (h["ret"] is None or day < h["ret"]):
            if 2 <= day.month <= 11:
                inspect(hid, day)
                day += dt.timedelta(days=max(14, min(60, round(rng.gauss(33, 9)))))
            else:
                day = D(day.year + (1 if day.month == 12 else 0), 2, rng.randint(1, 20))

    # contracts and placements
    cid = 9001
    contracts, placements, used = [], [], {}
    blocks = data["block"]
    for season in (2023, 2024, 2025, 2026):
        for b in blocks:
            g = growers[b[1]]
            if g[3] == "X" and season >= 2025:
                continue
            if g[4].year > season or rng.random() > 0.36:
                continue
            c = crop[b[2]]
            start = D(season, *c[3]) + dt.timedelta(days=rng.randint(-7, 7))
            end = start + dt.timedelta(days=c[4] + rng.randint(-5, 5))
            ha = b[4] / 100
            ordered = max(4, min(90, round(ha * c[2] * rng.uniform(.35, 1.0))))
            mg = rng.choices("ABC", [45, 45, 10])[0]
            rate = round(c[5] * (1 + 0.045 * (season - 2023)) * rng.uniform(.95, 1.06) / 25) * 25 + (1500 if mg == "A" else 0)
            if season == 2026:
                status = rng.choices([1, 2], [55, 45])[0]
            elif season == 2025 and b[2] == 15:
                status = 3
            else:
                status = rng.choices([4, 5], [90, 10])[0]
            signed = None if status == 1 else start - dt.timedelta(days=rng.randint(25, 160))
            contracts.append([cid, g[0], b[0], season, ordered, rate, mg, status, start, end, signed])
            cid += 1
    rng.shuffle(contracts)
    contracts.sort(key=lambda r: (r[3], r[10] or D(2030, 1, 1)))
    for i, r in enumerate(contracts):
        r[0] = 9001 + i
    for r in contracts:
        cid_, gid_, bid_, season, ordered, rate, mg, status, start, end, signed = r
        if status not in (3, 4):
            continue
        want = ordered if rng.random() < 0.7 else max(1, ordered - rng.randint(1, max(1, ordered // 6)))
        cands = [h for h in hives if live(h, start - dt.timedelta(days=10), end + dt.timedelta(days=10))
                 and used.get((h, season, end >= D(season, 9, 1))) is None]
        rng.shuffle(cands)
        got = 0
        need = {"A": 80, "B": 60, "C": 40}[mg]
        for h in cands:
            if got >= want:
                break
            in_dt = start + dt.timedelta(days=rng.choices([-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 5, 8],
                                                           [6, 8, 10, 12, 12, 10, 12, 9, 8, 6, 4, 3])[0])
            f = inspect(h, in_dt - dt.timedelta(days=rng.randint(1, 4)), pre=True)
            if f < need and rng.random() > 0.05:
                continue
            out = None if status == 3 and rng.random() < 0.85 else end + dt.timedelta(days=rng.randint(0, 6))
            if out is not None and out > TODAY:
                out = None
            placements.append([None, cid_, h, in_dt, out, grade(f), on_duty("D", in_dt)])
            used[(h, season, end >= D(season, 9, 1))] = cid_
            got += 1
    placements.sort(key=lambda p: (p[3], p[1], p[2]))
    for i, p in enumerate(placements):
        p[0] = 400001 + i
    data["contract"], data["placement"] = contracts, placements

    insp.sort(key=lambda r: r[2])
    data["inspection"] = [[700001 + i, *r] for i, r in enumerate(insp)]

    # invoices: deposit (D) 25% at signing, final (F) after the bloom, credit notes (C) for grade shortfalls
    # and cancellations; some voided and reissued
    inv = []
    plc_by = {}
    for p in placements:
        plc_by.setdefault(p[1], []).append(p)
    for r in contracts:
        cid_, gid_, bid_, season, ordered, rate, mg, status, start, end, signed = r
        g = growers[gid_]
        if status == 1:
            continue
        disc = 0 if g[5] != 1 else rng.choice([0, 250, 250, 500])
        if rng.random() < 0.08:
            disc = rng.choice([100, 300, 750])

        def add(kind, day, gross):
            if day > TODAY:
                return
            late = g[3] == "S"
            paid = None
            if rng.random() > (0.55 if late else 0.93) or day > TODAY - dt.timedelta(days=20):
                paid = None
            else:
                paid = day + dt.timedelta(days=rng.choices([rng.randint(3, 30), rng.randint(31, 95)], [78, 22])[0])
                if paid > TODAY:
                    paid = None
            if rng.random() < 0.035:
                inv.append([None, cid_, kind, day, gross, disc, None, 1])
                day = day + dt.timedelta(days=rng.randint(1, 6))
                if paid and paid < day:
                    paid = day + dt.timedelta(days=5)
            inv.append([None, cid_, kind, day, gross, disc, paid, 0])

        deposit = round(ordered * rate * 0.25)
        add("D", signed + dt.timedelta(days=rng.randint(0, 6)), deposit)
        if status == 5:
            add("C", signed + dt.timedelta(days=rng.randint(20, 90)), -round(deposit * 0.5))
            continue
        ps = plc_by.get(cid_, [])
        if status == 4 and ps:
            last = max(p[4] for p in ps if p[4])
            add("F", last + dt.timedelta(days=rng.randint(3, 15)), len(ps) * rate - deposit)
            need = {"A": "A", "B": "AB", "C": "ABC"}[mg]
            bad = sum(1 for p in ps if p[5] not in need)
            if bad:
                add("C", last + dt.timedelta(days=rng.randint(16, 40)), -round(bad * rate * 0.5))
    inv.sort(key=lambda r: (r[3], r[1], r[2]))
    for i, r in enumerate(inv):
        r[0] = 88001 + i
    data["invoice"] = inv
    return data


def build():
    data = build_data()
    admin = f"host={YB_HOST} port={YB_PORT} dbname=yugabyte user=yugabyte"
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute("DO $$BEGIN CREATE ROLE t2s_agent LOGIN PASSWORD 't2s_agent'; "
                  "EXCEPTION WHEN duplicate_object THEN NULL; END$$")
        c.execute(f"DROP DATABASE IF EXISTS {DB}")
        c.execute(f"CREATE DATABASE {DB} WITH COLOCATION = true")
    with psycopg.connect(admin.replace("dbname=yugabyte", f"dbname={DB}"), autocommit=True) as c:
        for t, cols in SCHEMA.items():
            body = ", ".join(f"{C(t, n)} {typ}" for n, typ in cols)
            c.execute(f"CREATE TABLE {T(t)} ({body}, PRIMARY KEY ({C(t, PK[t])} ASC))")
            with c.cursor().copy(f"COPY {T(t)} ({', '.join(C(t, n) for n, _ in cols)}) FROM STDIN") as cp:
                for row in data[t]:
                    cp.write_row(row)
        # the indexes a production system would have for its usual lookups
        c.execute(f"CREATE INDEX ON {T('inspection')} ({C('inspection', 'hive_id')}, {C('inspection', 'insp_ts')} DESC)")
        c.execute(f"CREATE INDEX ON {T('placement')} ({C('placement', 'contract_id')})")
        c.execute(f"CREATE INDEX ON {T('invoice')} ({C('invoice', 'contract_id')})")
        for t in SCHEMA:
            c.execute(f"ANALYZE {T(t)}")
        c.execute("GRANT USAGE ON SCHEMA public TO t2s_agent")
        c.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO t2s_agent")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "names.json").write_text(json.dumps({"tables": TABLES, "columns": {f"{t}.{c}": v for (t, c), v in COLS.items()
                                                                              if t != "*"}}, indent=1))
    for t in SCHEMA:
        print(f"{t:11s} {T(t)}  {len(data[t]):6d} rows")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "names"
    if cmd == "build":
        build()
    else:
        for t, cols in SCHEMA.items():
            print(t, T(t), " ".join(f"{c}={C(t, c)}" for c, _ in cols))
