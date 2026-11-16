# Peru fire events API (MODIS + VIIRS)

NASA Space Apps Challenge 2026 · Peru. A FastAPI service for the fire events of Peru
(20 Jan 2012 – 31 Jul 2026), built by merging the MODIS (Terra, Aqua) and VIIRS (Suomi NPP,
NOAA-20, NOAA-21) detections of NASA FIRMS. The main query is
**region + period → events with their lat/lon**.

The database (Postgres, 795,540 events and 1,958,951 detections) is downloaded already built
from [Google Drive](https://drive.google.com/file/d/1k76VcDl7RQq5hpKhayTXl_3URC_kQIAl/view?usp=sharing)
(`fires.dump`, 132 MB). On start-up, `deploy/bootstrap.sh` downloads it, checks its sha256,
restores it into `DATABASE_URL` if the database is empty, and starts the API.

## Deploy on Railway

`railway.json` already sets the build to the `Dockerfile` and restarts the service on failure.

1. **New Project → Deploy from GitHub repo** → this repo.
2. In the same project: **Create → Database → PostgreSQL**.
3. In the API service, **Variables → New Variable**: name `DATABASE_URL`, value
   `${{Postgres.DATABASE_URL}}`. Apply the change (**Deploy**).
4. **Settings → Networking → Generate Domain** (port: the one in the `Uvicorn running` log line).
5. In **Deploy Logs**, wait for `Uvicorn running` (~3–5 min the first time: it downloads and
   restores the database). Later deploys download nothing.

The API uses ~1 GB of RAM and the database ~1 GB of disk (Railway's trial volume of 0.5 GB is
too small).

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
createdb fires
DATABASE_URL=postgresql:///fires PYTHON=.venv/bin/python bash deploy/bootstrap.sh
```

Or with Docker, against any Postgres: `docker build -t fires-api .` and
`docker run -e DATABASE_URL=... -p 8000:8000 fires-api`.

Interactive documentation at `/docs` (Swagger) and `/redoc`.

## Main query: region + period

```
GET /events?bbox=lon_min,lat_min,lon_max,lat_max&start=YYYY-MM-DD&end=YYYY-MM-DD
GET /events?region=ucayali&start=2024-09-20&end=2024-09-26
GET /events?department=Ucayali&start=2024-09-01&end=2024-09-30&min_confidence=alta
```

Returns the events active in the period (UTC, both days included) whose bounding box touches
the region, each with its centre (`lat`, `lon`), bounding box, start and end, detections and FRP
per sensor, type and confidence. Filters: `min_confidence` (`baja` low, `media` medium, `alta`
high), `min_det`, `event_type`, `limit`/`offset`, `format=geojson`, `engine=index`.

| Endpoint | Returns |
|---|---|
| `GET /events` | events by region + period |
| `GET /events/near?lat&lon&radius_km&start&end` | events with detections within the radius of the point |
| `GET /events/nearest?lat&lon&t&k` | the k nearest events in space-time |
| `GET /events/{id}`, `/events/{id}/detections` | one event and its detections |
| `GET /event-types`, `/regions`, `/departments` | allowed values of the filters |
| `GET /static-sources?bbox` | excluded static sources (volcanoes, gas plants, industry) |
| `GET /health`, `/meta`, `/index`, `POST /index/rebuild` | status and parameters |

## Event fields

| Field | Meaning |
|---|---|
| `event_id` | Event number, assigned in order of start (1 = the first one in 2012). |
| `t_start`, `t_end`, `duration_days` | First and last detection (UTC) and the time between them. |
| `lat`, `lon` | Centre of the event: mean of its detections. |
| `lat_min` … `lon_max` | Bounding box of all detections. |
| `department` | Department with most of the event's detections (geoBoundaries). |
| `n_det`, `n_modis`, `n_viirs` | Detections (fire pixels) in total and per instrument. |
| `passes_modis`, `passes_viirs` | Satellite passes (images) that saw the event. |
| `satellites` | Satellites that detected it. |
| `frp_total`, `frp_max`, `frp_modis`, `frp_viirs` | Fire radiative power (MW): sum, maximum and sum per instrument. Not harmonised across sensors. |
| `spread_km`, `bearing_deg` | How far and in which direction (0 = N, clockwise) the fire moved between its first and last day. |
| `active_days` | Distinct days with at least one detection. |
| `foci_per_day` | Median number of separate fronts (> 1.25 km apart) burning on the same day. |
| `n_cells_1km` | 1 × 1 km cells touched: approximate burnt area in km². |
| `reburn_frac` | Share of those cells that burnt again in another week. |
| `event_type` | `foco_aislado`, `incendio`, `incendio_prolongado`, `quema_persistente`, `foco_recurrente` (see `/event-types`). |
| `confidence` | `alta` (high) when seen by MODIS **and** VIIRS, in ≥ 2 passes, with ≥ 5 detections; `media` (medium) with two of those; `baja` (low) otherwise. |
| `may_split`, `may_merge` | Whether the event would split with a stricter link radius (0.83 km) or merge with a neighbour with a wider one (1.9 km). |
| `hits` | Only in `engine=index` and `/events/near`: detections of the event inside the query. |
| `distance_km` | Only in `/events/nearest`: space-time distance to the query point. |

## Environment variables

| Variable | Default | Use |
|---|---|---|
| `DATABASE_URL` | `postgresql:///fires` | Postgres holding (or receiving) the database |
| `PORT` | `8000` | API port (Railway sets it) |
| `INDEX_BACKEND` | `kdtree` | in-memory index: `kdtree`, `cuda` or `auto` |
| `DUMP_URL`, `DUMP_SHA256` | Drive and its sha256 | another copy of the database |

## References

Artés, T., Oom, D., de Rigo, D., Durrant, T. H., Maianti, P., Libertà, G., & San-Miguel-Ayanz, J.
(2019). A global wildfire dataset for the analysis of fire regimes and fire behaviour.
*Scientific Data, 6*, Article 296. https://doi.org/10.1038/s41597-019-0312-2

Artés Vivancos, T., & San-Miguel-Ayanz, J. (2018). *ESRI shapefiles in monthly resolution*
[Data set]. In *Global wildfire database for GWIS*. PANGAEA.
https://doi.org/10.1594/PANGAEA.895898

Giglio, L., Schroeder, W., & Justice, C. O. (2016). The collection 6 MODIS active fire detection
algorithm and fire products. *Remote Sensing of Environment, 178*, 31–41.
https://doi.org/10.1016/j.rse.2016.02.054

NASA FIRMS. (2026). *Fire Information for Resource Management System: MODIS C6.1 and VIIRS 375 m
active fire detections, standard product* [Data set]. NASA Earth Science Data and Information
System. Retrieved November 15, 2026, from https://firms.modaps.eosdis.nasa.gov/

Runfola, D., Anderson, A., Baier, H., Crittenden, M., Dowker, E., Fuhrig, S., Goodman, S.,
Grimsley, G., Layko, R., Melville, G., Mulder, M., Oberman, R., Panganiban, J., Peck, A., Seitz,
L., Shea, S., Slevin, H., Youngerman, R., & Hobbs, L. (2020). geoBoundaries: A global database of
political administrative boundaries. *PLOS ONE, 15*(4), Article e0231866.
https://doi.org/10.1371/journal.pone.0231866

Schroeder, W., Oliva, P., Giglio, L., & Csiszar, I. A. (2014). The new VIIRS 375 m active fire
detection data product: Algorithm description and initial assessment. *Remote Sensing of
Environment, 143*, 85–96. https://doi.org/10.1016/j.rse.2013.12.008
