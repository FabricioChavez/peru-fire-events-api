"""Caja de Perú y proyección LAEA (km) que usa el índice espacio-tiempo."""
import numpy as np

PERU_BBOX = (-81.5, -18.5, -68.5, 0.1)  # lon_min, lat_min, lon_max, lat_max

# Centro de la proyección acimutal de Lambert de áreas iguales.
LAT0, LON0 = -9.0, -75.0
EARTH_KM = 6371.0088


def laea_km(lat, lon, lat0=LAT0, lon0=LON0):
    """Proyección acimutal de Lambert de áreas iguales (esfera), en km.
    Centrada en Perú: distorsión < 1 % en todo el país."""
    phi, lam = np.radians(lat), np.radians(lon - lon0)
    phi0 = np.radians(lat0)
    k = np.sqrt(2 / (1 + np.sin(phi0) * np.sin(phi) + np.cos(phi0) * np.cos(phi) * np.cos(lam)))
    x = EARTH_KM * k * np.cos(phi) * np.sin(lam)
    y = EARTH_KM * k * (np.cos(phi0) * np.sin(phi) - np.sin(phi0) * np.cos(phi) * np.cos(lam))
    return x, y
