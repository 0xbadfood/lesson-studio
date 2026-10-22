import sys, shapefile
from shapely.geometry import shape, Point
r = shapefile.Reader(sys.argv[1])
names = [f[0] for f in r.fields[1:]]
countries = {}
for rec, shp in zip(r.records(), r.shapes()):
    d = dict(zip(names, rec))
    countries[d.get('ADM0_A3') or d.get('NAME')] = (d.get('NAME'), shape(shp.__geo_interface__))
# (lon, lat)
PLACES = {'Muzaffarabad (PoK)': (73.47, 34.37), 'Mirpur (PoK)': (73.75, 33.15), 'Gilgit': (74.31, 35.92),
          'Skardu': (75.63, 35.30), 'Shaksgam valley': (76.6, 36.0), 'Aksai Chin (centre)': (79.3, 35.2),
          'Siachen glacier': (77.1, 35.4), 'Leh': (77.58, 34.16), 'Srinagar': (74.80, 34.08),
          'Tawang': (91.86, 27.59), 'Itanagar': (93.62, 27.08), 'Kibithu': (96.98, 28.28)}
for place, (lon, lat) in PLACES.items():
    inside = [n for k, (n, g) in countries.items() if g.contains(Point(lon, lat))]
    print(f'{place:22s} -> {inside}')
print(r.records()[0][:3], len(countries), 'IND' in countries)
