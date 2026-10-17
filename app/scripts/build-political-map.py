"""Rebuild the bundled European political basemap (development only; needs Shapely).

python3 -m venv /tmp/atlas-map-build
/tmp/atlas-map-build/bin/pip install shapely
/tmp/atlas-map-build/bin/python app/scripts/build-political-map.py
The packaged app uses the generated JSON, with no Python GIS dependency or tile API.
"""
import argparse
import json
from pathlib import Path
import urllib.request
from shapely.geometry import box, mapping, shape

REVISION = 'ca96624a56bd078437bca8184e78163e5039ad19'
ROOT = Path(__file__).resolve().parents[1]
BOUNDS = [-25, 30, 50, 73]
CLIP = box(*BOUNDS)


def source(name, cache):
    path = cache / (name + '.geojson')
    if not path.exists():
        url = f'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{REVISION}/geojson/{name}.geojson'
        with urllib.request.urlopen(url, timeout=60) as response:
            path.write_bytes(response.read())
    return json.loads(path.read_text())['features']


def rounded(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, (list, tuple)):
        return [rounded(item) for item in value]
    if isinstance(value, dict):
        return {key: rounded(item) for key, item in value.items()}
    return value


def feature(geometry, properties):
    return {'type':'Feature', 'properties':properties, 'geometry':rounded(mapping(geometry))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, default=Path('/tmp/atlas-natural-earth'))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    countries, states, cities = [], [], []
    for row in source('ne_10m_admin_0_countries', args.cache):
        geometry = shape(row['geometry'])
        if not geometry.intersects(CLIP):
            continue
        # Keep complete country outlines: clipping would create false borders at the map edge.
        geometry = geometry.simplify(.006, preserve_topology=True)
        if geometry.is_empty or geometry.area < .001:
            continue
        props = row['properties']
        polygons = list(geometry.geoms) if geometry.geom_type == 'MultiPolygon' else [geometry]
        mainland = max(polygons, key=lambda polygon: polygon.area)
        label = mainland.representative_point()
        countries.append(feature(geometry, {'name':props.get('NAME_EN') or props['NAME'], 'code':props['ADM0_A3'], 'label':[round(label.y,4),round(label.x,4)]}))
    for row in source('ne_10m_admin_1_states_provinces', args.cache):
        if row['properties'].get('iso_a2') not in ('DE', 'AT', 'NL', 'CH', 'BE'):
            continue
        geometry = shape(row['geometry'])
        if not geometry.intersects(CLIP):
            continue
        geometry = geometry.intersection(CLIP).simplify(.003, preserve_topology=True)
        if geometry.is_empty or geometry.area < .001:
            continue
        props = row['properties']
        # Keep polygons for label placement; the renderer draws only their outlines.
        states.append(feature(geometry, {'name':props.get('name_en') or props['name'], 'country':props.get('iso_a2'), 'label':[props.get('latitude'),props.get('longitude')]}))
    for row in source('ne_50m_populated_places_simple', args.cache):
        props = row['properties']
        point = shape(row['geometry'])
        if CLIP.contains(point):
            cities.append({'name':props.get('nameascii') or props['name'], 'lat':round(point.y,4), 'lon':round(point.x,4), 'population':props.get('pop_max') or 0})
    result = {'source':'Natural Earth', 'revision':REVISION, 'license':'public domain', 'bounds':BOUNDS,
              'countries':{'type':'FeatureCollection','features':countries}, 'states':{'type':'FeatureCollection','features':states}, 'cities':cities}
    path = ROOT / 'content/political-map.json'
    path.write_text(json.dumps(result, ensure_ascii=False, separators=(',',':'))+'\n')
    print(f'{len(countries)} countries, {len(states)} state/regional outlines, {len(cities)} cities; {path.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
