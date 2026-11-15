# API de eventos de fuego de Perú (MODIS + VIIRS)

NASA Space Apps Challenge 2026 · Perú. API FastAPI que sirve los eventos de fuego de Perú
(20 ene 2012 – 31 jul 2026), armados uniendo las detecciones de MODIS (Terra, Aqua) y VIIRS
(Suomi NPP, NOAA-20, NOAA-21) de NASA FIRMS. La consulta principal es
**región + periodo → eventos con su lat/lon**.

La base (Postgres, 795 540 eventos y 1 958 951 detecciones) se baja ya construida de
[Google Drive](https://drive.google.com/file/d/1k76VcDl7RQq5hpKhayTXl_3URC_kQIAl/view?usp=sharing)
(`fires.dump`, 132 MB). Al arrancar, `deploy/bootstrap.sh` la baja, verifica su sha256, la
restaura en `DATABASE_URL` si la base está vacía y lanza la API.

## Deploy en Railway

1. **New Project → Deploy from GitHub repo** → este repo. Railway detecta el `Dockerfile`.
2. En el mismo proyecto: **New → Database → PostgreSQL**.
3. En el servicio de la API, **Variables**: `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`.
4. **Settings → Networking → Generate Domain**.
5. En **Deploy Logs** espera `Uvicorn running` (~3–5 min la primera vez). La API necesita
   ~1 GB de RAM.

## Correr en local

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
createdb fires
DATABASE_URL=postgresql:///fires PYTHON=.venv/bin/python bash deploy/bootstrap.sh
```

O con Docker, contra cualquier Postgres: `docker build -t fires-api .` y
`docker run -e DATABASE_URL=... -p 8000:8000 fires-api`.

Documentación interactiva en `/docs`.

## Consulta principal: región + periodo

```
GET /events?bbox=lon_min,lat_min,lon_max,lat_max&start=AAAA-MM-DD&end=AAAA-MM-DD
GET /events?region=ucayali&start=2024-09-20&end=2024-09-26
GET /events?department=Ucayali&start=2024-09-01&end=2024-09-30&min_confidence=alta
```

Devuelve los eventos activos en el periodo (UTC, ambos días incluidos) cuya caja toca la
región, cada uno con su centro (`lat`, `lon`), su caja, inicio y fin, detecciones y FRP por
sensor, tipo y confianza. Filtros: `min_confidence` (baja, media, alta), `min_det`,
`event_type`, `limit`/`offset`, `format=geojson`, `engine=index`.

| Endpoint | Devuelve |
|---|---|
| `GET /events` | eventos por región + periodo |
| `GET /events/near?lat&lon&radius_km&start&end` | eventos con detecciones a ≤ radio del punto |
| `GET /events/nearest?lat&lon&t&k` | k eventos más cercanos en espacio-tiempo |
| `GET /events/{id}`, `/events/{id}/detections` | ficha y detecciones de un evento |
| `GET /event-types`, `/regions`, `/departments` | valores posibles de los filtros |
| `GET /static-sources?bbox` | fuentes fijas excluidas (volcanes, gas, industria) |
| `GET /health`, `/meta`, `/index`, `POST /index/rebuild` | estado y parámetros |

## Variables

| Variable | Por defecto | Uso |
|---|---|---|
| `DATABASE_URL` | `postgresql:///fires` | Postgres donde está (o se restaura) la base |
| `PORT` | `8000` | puerto de la API (Railway lo pone solo) |
| `INDEX_BACKEND` | `kdtree` | índice en memoria: `kdtree`, `cuda` o `auto` |
| `DUMP_URL`, `DUMP_SHA256` | Drive y su sha256 | otra copia de la base |

## Referencias

Artés, T., Oom, D., de Rigo, D., Durrant, T. H., Maianti, P., Libertà, G., & San-Miguel-Ayanz, J.
(2019). A global wildfire dataset for the analysis of fire regimes and fire behaviour.
*Scientific Data, 6*, Artículo 296. https://doi.org/10.1038/s41597-019-0312-2

Artés Vivancos, T., & San-Miguel-Ayanz, J. (2018). *ESRI shapefiles in monthly resolution*
[Conjunto de datos]. En *Global wildfire database for GWIS*. PANGAEA.
https://doi.org/10.1594/PANGAEA.895898

Giglio, L., Schroeder, W., & Justice, C. O. (2016). The collection 6 MODIS active fire detection
algorithm and fire products. *Remote Sensing of Environment, 178*, 31–41.
https://doi.org/10.1016/j.rse.2016.02.054

NASA FIRMS. (2026). *Fire Information for Resource Management System: Detecciones MODIS C6.1 y
VIIRS 375 m, producto estándar* [Conjunto de datos]. NASA Earth Science Data and Information
System. Recuperado el 15 de noviembre de 2026, de https://firms.modaps.eosdis.nasa.gov/

Runfola, D., Anderson, A., Baier, H., Crittenden, M., Dowker, E., Fuhrig, S., Goodman, S.,
Grimsley, G., Layko, R., Melville, G., Mulder, M., Oberman, R., Panganiban, J., Peck, A., Seitz,
L., Shea, S., Slevin, H., Youngerman, R., & Hobbs, L. (2020). geoBoundaries: A global database of
political administrative boundaries. *PLOS ONE, 15*(4), Artículo e0231866.
https://doi.org/10.1371/journal.pone.0231866

Schroeder, W., Oliva, P., Giglio, L., & Csiszar, I. A. (2014). The new VIIRS 375 m active fire
detection data product: Algorithm description and initial assessment. *Remote Sensing of
Environment, 143*, 85–96. https://doi.org/10.1016/j.rse.2013.12.008
