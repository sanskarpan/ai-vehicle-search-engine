from __future__ import annotations

import argparse
import hashlib
import json
import random

from .domain import Vehicle
from .storage import connect, insert_vehicle

ANCHORS=[
("Aster","Trail","D AT",2023,1499999,79999,"used","suv","diesel","automatic",5,"pune",5,4,["isofix","esc","rear_ac"]),
("Aster","Trail","D AT Edge",2023,1500000,80000,"used","suv","diesel","automatic",5,"pune",5,4,["isofix","esc","rear_ac"]),
("Aster","Trail","D AT Plus",2023,1500001,80001,"used","suv","diesel","automatic",5,"pune",5,4,["isofix","esc","rear_ac"]),
("Meridian","City","P MT",2023,900000,40000,"used","sedan","petrol","manual",5,"pune",4,4,["isofix","esc"]),
("Meridian","Vista","D AT",2023,1200000,50000,"used","suv","diesel","automatic",5,"pune",None,None,["rear_ac"]),
("Cedar","People","D AT",2023,1400000,70000,"used","mpv","diesel","automatic",7,"pune",5,5,["isofix","esc","rear_ac"]),
("Cedar","Mini","P MT",2023,600000,20000,"used","hatchback","petrol","manual",4,"pune",3,2,[]),
("Aster","Volt","EV",2025,1300000,100,"new","suv","electric","automatic",5,"bengaluru",4,3,["isofix","esc"]),]
TEMPLATES=[("Aster","Trail","suv",("diesel","petrol")),("Meridian","City","sedan",("petrol","diesel")),("Cedar","People","mpv",("diesel","petrol")),("Nova","Swift","hatchback",("petrol","cng")),("Aster","Volt","suv",("electric",))]
def build(count=300, seed=42):
    if count<8: raise ValueError("count must be >= 8")
    rng=random.Random(seed); out=[]
    for n,a in enumerate(ANCHORS,1):
        make,model,var,year,price,odo,cond,body,fuel,trans,seats,city,adult,child,features=a
        out.append(Vehicle(f"veh_{n:06d}",make,model,var,year,price,odo,cond,body,fuel,trans,seats,city,features,adult,child,f"Synthetic {seats}-seat {fuel} {body}.",True,"synthetic_demo_v1","demo_v1",year if adult is not None else None,None,f"{make} {model} {var} {year}"))
    while len(out)<count:
        idx=len(out)+1; make,model,body,fuels=rng.choice(TEMPLATES); fuel=rng.choice(fuels); trans="automatic" if fuel=="electric" or rng.random()<.45 else "manual"; seats=7 if body=="mpv" else (rng.choice([5,7]) if body=="suv" else 5 if rng.random()<.8 else 4); year=rng.randint(2018,2026); cond="new" if year>=2025 and rng.random()<.5 else "used"; odo=0 if cond=="new" else rng.randint(1000,160000); price=rng.randint(650000,3200000); adult=None if rng.random()<.12 else rng.randint(2,5); child=None if rng.random()<.12 else rng.randint(2,5); city=rng.choice(["pune","mumbai","delhi","hyderabad","chennai","bengaluru"]); features=rng.sample(["isofix","esc","rear_ac","parking_camera","cruise_control"],rng.randint(0,3)); out.append(Vehicle(f"veh_{idx:06d}",make,model,f"V{idx%4+1}",year,price,odo,cond,body,fuel,trans,seats,city,features,adult,child,f"Synthetic {seats}-seat {fuel} {body} listing.",True,"synthetic_demo_v1","demo_v1",year if adult is not None else None,None,f"{make} {model} V{idx%4+1} {year}"))
    return out
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--count",type=int,default=300); ap.add_argument("--seed",type=int,default=42); ap.add_argument("--db",default="./data/catalogue.db"); ap.add_argument("--reset",action="store_true"); a=ap.parse_args(); c=connect(a.db)
    if a.reset: c.executescript("DROP TABLE IF EXISTS vehicle_features; DROP TABLE IF EXISTS vehicles; DROP TABLE IF EXISTS catalogue_metadata;"); c.executescript(__import__('vehicle_search.storage',fromlist=['SCHEMA']).SCHEMA)
    if c.execute("SELECT count(*) FROM vehicles").fetchone()[0] and not a.reset: print("catalogue already seeded; use --reset"); return
    rows=build(a.count,a.seed); c.execute("BEGIN"); [insert_vehicle(c,v) for v in rows]; payload=json.dumps([v.__dict__ for v in rows],sort_keys=True); digest=hashlib.sha256(payload.encode()).hexdigest(); c.execute("INSERT OR REPLACE INTO catalogue_metadata VALUES ('catalogue_version',?)",(f"seed-{a.seed}-{digest[:12]}",)); c.commit(); print(f"seeded {len(rows)} vehicles; version seed-{a.seed}-{digest[:12]}")
if __name__=="__main__": main()
