from __future__ import annotations

import sqlite3
from pathlib import Path

from .domain import Predicate, Vehicle

SCHEMA='''CREATE TABLE IF NOT EXISTS vehicles(id TEXT PRIMARY KEY, make TEXT, model TEXT, variant TEXT, year INTEGER, price_inr INTEGER, odometer_km INTEGER, condition TEXT, body_type TEXT, fuel_type TEXT, transmission TEXT, seats INTEGER, city TEXT, adult_safety_stars INTEGER, child_safety_stars INTEGER, description TEXT, safety_test_year INTEGER, safety_applicability TEXT); CREATE TABLE IF NOT EXISTS vehicle_features(vehicle_id TEXT, feature TEXT, PRIMARY KEY(vehicle_id,feature)); CREATE TABLE IF NOT EXISTS catalogue_metadata(key TEXT PRIMARY KEY,value TEXT);'''
def connect(path: str, read_only=False):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    if read_only:
        if not Path(path).exists():
            raise FileNotFoundError(path)
        return sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro",uri=True)
    c=sqlite3.connect(path); c.executescript(SCHEMA); return c
def insert_vehicle(c, v: Vehicle):
    c.execute("INSERT INTO vehicles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(v.id,v.make,v.model,v.variant,v.year,v.price_inr,v.odometer_km,v.condition,v.body_type,v.fuel_type,v.transmission,v.seats,v.city,v.adult_safety_stars,v.child_safety_stars,v.description,v.safety_test_year,v.safety_applicability))
    c.executemany("INSERT INTO vehicle_features VALUES (?,?)",[(v.id,f) for f in v.features])
def row_vehicle(row, features):
    return Vehicle(*row[:13],features,row[13],row[14],row[15],True,"synthetic_demo_v1","demo_v1",row[16],None,row[17])
def search(c, predicates: list[Predicate]):
    wh=[]; args=[]; feature=[]
    cols={"price_inr":"price_inr","odometer_km":"odometer_km","year":"year","seats":"seats","adult_safety_stars":"adult_safety_stars","child_safety_stars":"child_safety_stars","body_type":"body_type","fuel_type":"fuel_type","transmission":"transmission","make":"lower(make)","model":"lower(model)","city":"lower(city)","condition":"condition"}
    ops={"eq":"=","lt":"<","lte":"<=","gt":">","gte":">=","in":"IN","not_in":"NOT IN"}
    for p in predicates:
        if p.field=="features": feature.extend(p.values); continue
        if p.field not in cols or p.op not in ops: raise ValueError("unsupported predicate")
        col=cols[p.field]; vals=p.values
        if p.op in {"in","not_in"}:
            if not vals: raise ValueError("empty predicate")
            wh.append(f"{col} {ops[p.op]} ({','.join('?' for _ in vals)})"); args.extend([str(v).lower() if p.field in {"make","model","city"} else v for v in vals])
        else:
            wh.append(f"{col} {ops[p.op]} ?"); args.append(p.values[0])
    for f in feature: wh.append("EXISTS (SELECT 1 FROM vehicle_features vf WHERE vf.vehicle_id=v.id AND vf.feature=? )"); args.append(f)
    sql="SELECT v.id,v.make,v.model,v.variant,v.year,v.price_inr,v.odometer_km,v.condition,v.body_type,v.fuel_type,v.transmission,v.seats,v.city,v.adult_safety_stars,v.child_safety_stars,v.description,v.safety_test_year,v.safety_applicability FROM vehicles v"+(" WHERE "+" AND ".join(wh) if wh else "")+" ORDER BY v.id"
    rows=c.execute(sql,args).fetchall(); ids=[r[0] for r in rows]
    fs={k:[] for k in ids}
    if ids:
        for k,f in c.execute(f"SELECT vehicle_id,feature FROM vehicle_features WHERE vehicle_id IN ({','.join('?' for _ in ids)})",ids): fs[k].append(f)
    return [row_vehicle(r,fs[r[0]]) for r in rows]
def get(c, vid):
    rows=search(c,[Predicate("make","in",["__never__"])]) if False else c.execute("SELECT id,make,model,variant,year,price_inr,odometer_km,condition,body_type,fuel_type,transmission,seats,city,adult_safety_stars,child_safety_stars,description,safety_test_year,safety_applicability FROM vehicles WHERE id=?",(vid,)).fetchall()
    if not rows:return None
    feats=[x[0] for x in c.execute("SELECT feature FROM vehicle_features WHERE vehicle_id=?",(vid,))]
    return row_vehicle(rows[0],feats)
