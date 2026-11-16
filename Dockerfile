FROM python:3.12-slim

# pg_restore and psql to restore the database; curl to download the dump.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY deploy ./deploy

ENV PYTHON=python PORT=8000 INDEX_BACKEND=kdtree
EXPOSE 8000
CMD ["bash", "deploy/bootstrap.sh"]
