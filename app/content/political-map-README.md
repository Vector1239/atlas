# Political basemap

`political-map.json` is a bundled, simplified European basemap. It does not use remote map tiles, imagery, vegetation or road detail.

Source: [Natural Earth](https://www.naturalearthdata.com/), [public domain](https://www.naturalearthdata.com/about/terms-of-use/). Source revision: `ca96624a56bd078437bca8184e78163e5039ad19` from the [maintainer’s vector repository](https://github.com/nvkelso/natural-earth-vector).

Datasets:

- `ne_10m_admin_0_countries`: countries intersecting the European viewing area. Complete country geometry is retained so clipping does not create false borders at the view’s edge.
- `ne_10m_admin_1_states_provinces`: state/regional outlines in Germany, Austria, Switzerland, the Netherlands and Belgium. All 16 German states are included. German state names are shown where space permits.
- `ne_50m_populated_places_simple`: major city labels in the viewing area. Job and event city coordinates continue to use the separately verified `places.json` data.

Coordinates are rounded to four decimal places. Country polygons are simplified by 0.006 degrees, and state polygons by 0.003 degrees with topology preservation. These are generalised boundaries for browsing at regional scales, not address or navigation geometry. Labels avoid pins and each other; country/state labels are placed within their own polygons.

Rebuild with the developer-only `app/scripts/build-political-map.py` script (requires Shapely in a separate build environment). Ordinary app builds and the packaged application require no GIS packages or online map service.
