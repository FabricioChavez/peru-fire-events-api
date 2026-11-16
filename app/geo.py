"""Peru bounding box and the LAEA projection (km) used by the space-time index."""
import numpy as np

PERU_BBOX = (-81.5, -18.5, -68.5, 0.1)  # lon_min, lat_min, lon_max, lat_max

# Centre of the Lambert azimuthal equal-area projection.
LAT0, LON0 = -9.0, -75.0
EARTH_KM = 6371.0088


def laea_km(lat, lon, lat0=LAT0, lon0=LON0):
    """Lambert azimuthal equal-area projection (sphere), in km.
    Centred on Peru: distortion < 1 % across the whole country."""
    phi, lam = np.radians(lat), np.radians(lon - lon0)
    phi0 = np.radians(lat0)
    k = np.sqrt(2 / (1 + np.sin(phi0) * np.sin(phi) + np.cos(phi0) * np.cos(phi) * np.cos(lam)))
    x = EARTH_KM * k * np.cos(phi) * np.sin(lam)
    y = EARTH_KM * k * (np.cos(phi0) * np.sin(phi) - np.sin(phi0) * np.cos(phi) * np.cos(lam))
    return x, y
