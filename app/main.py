"""Peru fire events API (FastAPI + Postgres + space-time index).

    export DATABASE_URL=postgresql:///fires
    export INDEX_BACKEND=auto          # auto | kdtree | cuda
    uvicorn app.main:app --reload --port 8000

Interactive documentation at http://localhost:8000/docs
"""
import json
import os
import threading
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from pathlib import Path

from .geo import PERU_BBOX
from .index import SpaceTimeIndex

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql:///fires")
INDEX_BACKEND = os.environ.get("INDEX_BACKEND", "auto")
REGIONS_JSON = Path(__file__).with_name("regions.json")

EVENT_FIELDS = """event_id, t_start, t_end, duration_days, lat, lon,
    lat_min, lat_max, lon_min, lon_max, n_det, n_modis, n_viirs, passes_modis, passes_viirs,
    frp_total, frp_max, frp_modis, frp_viirs, satellites, department, spread_km, bearing_deg,
    may_split, may_merge, confidence, event_type, active_days, foci_per_day, n_cells_1km,
    reburn_frac"""
# Stored values (kept in Spanish, as in the database): event types and confidence levels.
EVENT_TYPES = ["foco_aislado", "incendio", "incendio_prolongado", "quema_persistente",
               "foco_recurrente"]
CONFIDENCE_LEVELS = {"baja": ["baja", "media", "alta"], "media": ["media", "alta"],
                     "alta": ["alta"]}

DESCRIPTION = """
Fire events in Peru (20 Jan 2012 – 31 Jul 2026) built by merging the MODIS (Terra, Aqua) and
VIIRS (Suomi NPP, NOAA-20, NOAA-21) active-fire detections of NASA FIRMS (standard product).

**Main query: region + period → events with lat/lon**

`GET /events?region=ucayali&start=2024-09-20&end=2024-09-26`

Stored values are in Spanish:
- `event_type`: `foco_aislado` (isolated hotspot), `incendio` (fire), `incendio_prolongado`
  (long-lasting fire), `quema_persistente` (persistent burning zone), `foco_recurrente`
  (recurrent hotspot). See `/event-types`.
- `confidence` / `min_confidence`: `baja` (low), `media` (medium), `alta` (high).

All times are UTC, as in FIRMS.
"""

state = {}


def load_regions():
    try:
        regs = json.loads(REGIONS_JSON.read_text(encoding="utf-8"))["regiones"]
    except Exception:
        regs = {}
    out = {"peru": PERU_BBOX}
    for name, r in regs.items():
        if r.get("tipo") != "pais":
            out[name] = tuple(float(v) for v in r["area"].split(","))
    return out


def build_index():
    with state["pool"].connection() as conn:
        state["index"] = SpaceTimeIndex.from_postgres(conn, backend=INDEX_BACKEND)


@asynccontextmanager
async def lifespan(app):
    # Every time in the API is UTC, as in FIRMS.
    state["pool"] = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, open=True,
                                   kwargs={"options": "-c TimeZone=UTC"})
    state["regions"] = load_regions()
    state["departments"] = [r["department"] for r in sql(
        "SELECT DISTINCT department FROM events WHERE department IS NOT NULL ORDER BY 1")]
    state["index_lock"] = threading.Lock()
    build_index()
    yield
    state["pool"].close()


app = FastAPI(title="Peru fire events · MODIS + VIIRS", version="0.1.0",
              description=DESCRIPTION, lifespan=lifespan)


def sql(query, params=()):
    with state["pool"].connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def resolve_bbox(bbox: Optional[str], region: Optional[str]):
    if region:
        if region not in state["regions"]:
            raise HTTPException(404, f"Unknown region. Use one of: {list(state['regions'])}")
        return state["regions"][region]
    if not bbox:
        raise HTTPException(422, "Give bbox=lon_min,lat_min,lon_max,lat_max or region=<name>")
    try:
        lon_min, lat_min, lon_max, lat_max = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be lon_min,lat_min,lon_max,lat_max")
    if lon_min > lon_max or lat_min > lat_max:
        raise HTTPException(422, "bbox: the minimum must be smaller than the maximum")
    return lon_min, lat_min, lon_max, lat_max


def day_after(d: date):
    """Exclusive upper bound: the next day at 00:00 UTC."""
    return datetime.combine(d, datetime.min.time()) + timedelta(days=1)


def as_geojson(rows):
    feats = [{"type": "Feature",
              "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
              "properties": {k: v for k, v in r.items() if k not in ("lat", "lon")}}
             for r in rows]
    return {"type": "FeatureCollection", "features": feats}


def events_by_ids(ids, extra=None, order=None):
    if not ids:
        return []
    rows = sql(f"SELECT {EVENT_FIELDS} FROM events WHERE event_id = ANY(%s)", (list(ids),))
    if extra is not None:
        for r in rows:
            r.update(extra.get(r["event_id"], {}))
    if order:
        pos = {e: i for i, e in enumerate(order)}
        rows.sort(key=lambda r: pos[r["event_id"]])
    return rows


# ---------------------------------------------------------------------------- endpoints
@app.get("/health")
def health():
    """Database totals and in-memory index status."""
    n = sql("SELECT (SELECT count(*) FROM events) AS events, "
            "(SELECT count(*) FROM detections) AS detections")[0]
    return {"status": "ok", **n, "index": state["index"].info()}


@app.get("/meta")
def meta():
    """Parameters and dates used to build the event tables."""
    rows = sql("SELECT key, value FROM meta ORDER BY key")
    return {r["key"]: r["value"] for r in rows}


@app.get("/regions")
def regions():
    """Named regions accepted by the `region` parameter, with their bounding box."""
    return {k: {"bbox": list(v)} for k, v in state["regions"].items()}


@app.get("/departments")
def departments_list():
    """Departments with events (for the `department` parameter of /events)."""
    return {"departments": state["departments"]}


TYPE_HELP = {
    "foco_aislado": "isolated hotspot: lasts less than a day and covers 1–2 km²",
    "incendio": "fire: up to 22 days (the longest GlobFire fire in Peru)",
    "incendio_prolongado": "long-lasting fire: more than 22 days with a single front per day "
                           "that keeps burning",
    "quema_persistente": "persistent burning zone: more than 22 days with several fronts at "
                         "once (land clearing or agricultural burning)",
    "foco_recurrente": "recurrent hotspot: more than 22 days always within ≤ 5 km²; likely an "
                       "industrial or fixed source the mask missed",
}


@app.get("/event-types")
def event_types():
    """Event types, what they mean and how many there are."""
    counts = {r["event_type"]: r for r in sql(
        """SELECT event_type, count(*) AS events, sum(n_det) AS detections,
                  max(duration_days) AS max_duration_days
           FROM events GROUP BY event_type""")}
    return [{"event_type": t, "description": TYPE_HELP[t],
             **{k: v for k, v in counts.get(t, {}).items() if k != "event_type"}}
            for t in EVENT_TYPES]


@app.get("/static-sources")
def static_sources(bbox: Optional[str] = Query(None, examples=["-81.5,-18.5,-68.5,0.1"]),
                   region: Optional[str] = None,
                   format: Literal["json", "geojson"] = "json"):
    """Cells excluded as static sources (volcanoes, gas plants, industry), not vegetation fire."""
    lon_min, lat_min, lon_max, lat_max = resolve_bbox(bbox, region) if (bbox or region) \
        else PERU_BBOX
    rows = sql("""SELECT cell, lat, lon, reason, n_det, years, months, months_per_year,
                         n_type1, n_type2, n_type3, frp_median, first, last
                  FROM static_sources WHERE pt <@ box(point(%s,%s), point(%s,%s))
                  ORDER BY n_det DESC""", (lon_min, lat_min, lon_max, lat_max))
    if format == "geojson":
        return as_geojson(rows)
    return {"count": len(rows), "static_sources": rows}


@app.get("/events")
def events(
    start: date = Query(..., description="Start date (UTC), inclusive", examples=["2024-09-01"]),
    end: date = Query(..., description="End date (UTC), inclusive", examples=["2024-09-30"]),
    bbox: Optional[str] = Query(None, description="lon_min,lat_min,lon_max,lat_max",
                                examples=["-75.7,-11.5,-70.4,-7.2"]),
    region: Optional[str] = Query(None, description="Name from /regions, e.g. ucayali"),
    department: Optional[str] = Query(None, description="Department, e.g. Ucayali "
                                      "(see /departments). Can be combined with bbox."),
    min_confidence: Literal["baja", "media", "alta"] = Query(
        "baja", description="Minimum confidence: baja (low), media (medium), alta (high)"),
    min_det: int = Query(1, ge=1, description="Minimum number of detections in the event"),
    event_type: Optional[str] = Query(
        None, description="One or more comma-separated types: foco_aislado, incendio, "
                          "incendio_prolongado, quema_persistente, foco_recurrente"),
    engine: Literal["postgres", "index"] = Query(
        "postgres", description="postgres: GiST indexes; index: in-memory KD-tree/GPU"),
    format: Literal["json", "geojson"] = "json",
    limit: int = Query(1000, ge=1, le=50000),
    offset: int = Query(0, ge=0),
):
    """Events active in the region and date range, with their centre (lat, lon) and bounding box."""
    if department and not (bbox or region):
        lon_min, lat_min, lon_max, lat_max = PERU_BBOX
    else:
        lon_min, lat_min, lon_max, lat_max = resolve_bbox(bbox, region)
    if department and department not in state["departments"]:
        raise HTTPException(404, f"Unknown department. Use one of: {state['departments']}")
    types = [t.strip() for t in event_type.split(",")] if event_type else EVENT_TYPES
    if set(types) - set(EVENT_TYPES):
        raise HTTPException(422, f"event_type must be one of {EVENT_TYPES}")
    t0 = datetime.combine(start, datetime.min.time())
    t1 = datetime.combine(end, datetime.min.time()).replace(hour=23, minute=59, second=59)
    levels = CONFIDENCE_LEVELS[min_confidence]
    if engine == "postgres":
        where = """bbox && box(point(%s,%s), point(%s,%s))
                   AND period && tstzrange(%s::timestamp AT TIME ZONE 'UTC',
                                           %s::timestamp AT TIME ZONE 'UTC', '[]')
                   AND confidence = ANY(%s) AND n_det >= %s
                   AND (%s::text IS NULL OR department = %s::text)
                   AND event_type = ANY(%s)"""
        args = (lon_min, lat_min, lon_max, lat_max, t0, t1, levels, min_det, department,
                department, types)
        total = sql(f"SELECT count(*) AS n FROM events WHERE {where}", args)[0]["n"]
        rows = sql(f"""SELECT {EVENT_FIELDS} FROM events WHERE {where}
                       ORDER BY t_start, event_id LIMIT %s OFFSET %s""",
                   args + (limit, offset))
    else:
        # The index finds the events with at least one detection inside the region and the
        # dates (stricter than intersecting boxes). Postgres then returns their records.
        hits = state["index"].box(lon_min, lat_min, lon_max, lat_max, t0, day_after(end))
        rows = events_by_ids(hits["event_id"].tolist(),
                             extra={e: {"hits": int(h)} for e, h in
                                    zip(hits["event_id"], hits["hits"])})
        rows = [r for r in rows if r["confidence"] in levels and r["n_det"] >= min_det
                and (department is None or r["department"] == department)
                and r["event_type"] in types]
        rows.sort(key=lambda r: (r["t_start"], r["event_id"]))
        total = len(rows)
        rows = rows[offset:offset + limit]
    if format == "geojson":
        return {**as_geojson(rows), "total": total}
    return {"total": total, "count": len(rows), "offset": offset,
            "query": {"bbox": [lon_min, lat_min, lon_max, lat_max], "department": department,
                      "event_type": types, "start": start, "end": end, "engine": engine},
            "events": rows}


@app.get("/events/near")
def events_near(lat: float, lon: float, start: date, end: date,
                radius_km: float = Query(10, gt=0, le=500), limit: int = 500):
    """Events with detections within radius_km of the point in the date range (KD-tree)."""
    hits = state["index"].near(lat, lon, radius_km, start, day_after(end)).nlargest(limit, "hits")
    rows = events_by_ids(hits["event_id"].tolist(),
                         extra={e: {"hits": int(h)} for e, h in
                                zip(hits["event_id"], hits["hits"])})
    rows.sort(key=lambda r: r["t_start"])
    return {"count": len(rows), "events": rows}


@app.get("/events/nearest")
def events_nearest(lat: float, lon: float, t: datetime, k: int = Query(10, ge=1, le=200)):
    """The k nearest events in space-time (1 day counts as km_per_day km)."""
    near = state["index"].nearest(lat, lon, t, k)
    rows = events_by_ids(near["event_id"].tolist(),
                         extra={e: {"distance_km": float(d)} for e, d in
                                zip(near["event_id"], near["distance_km"])},
                         order=near["event_id"].tolist())
    return {"count": len(rows), "km_per_day": state["index"].km_per_day, "events": rows}


@app.get("/events/{event_id}")
def event(event_id: int):
    """One event record."""
    rows = events_by_ids([event_id])
    if not rows:
        raise HTTPException(404, "Event not found")
    return rows[0]


@app.get("/events/{event_id}/detections")
def event_detections(event_id: int, format: Literal["json", "geojson"] = "json"):
    """Every detection of the event: where, when, which satellite and its FRP."""
    rows = sql("""SELECT det_id, t_utc, lat, lon, instrument, satellite, processing, overpass,
                         frp, scan_km, track_km, confidence, daynight
                  FROM detections WHERE event_id = %s ORDER BY t_utc""", (event_id,))
    if not rows:
        raise HTTPException(404, "Event not found")
    if format == "geojson":
        return as_geojson(rows)
    return {"event_id": event_id, "count": len(rows), "detections": rows}


@app.get("/index")
def index_info():
    """In-memory index status: backend, number of points, load and build time."""
    return state["index"].info()


@app.post("/index/rebuild")
def index_rebuild(backend: Optional[Literal["auto", "kdtree", "cuda"]] = None):
    """Re-read the detections from Postgres and rebuild the index."""
    global INDEX_BACKEND
    with state["index_lock"]:
        if backend:
            INDEX_BACKEND = backend
        build_index()
    return state["index"].info()
