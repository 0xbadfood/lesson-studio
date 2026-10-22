import shapefile
from shapely.geometry import shape, box
r = shapefile.Reader(__import__('sys').argv[1])
names = [f[0] for f in r.fields[1:]]
W, H, (x0, y0, x1, y1) = 1000, 1100, (66, 5, 100, 38)
sx = lambda x: (x - x0) / (x1 - x0) * W
sy = lambda y: (y1 - y) / (y1 - y0) * H
def path(g):
    polys = [g] if g.geom_type == 'Polygon' else list(g.geoms)
    out = ''
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            out += 'M' + ' L'.join(f'{sx(x):.1f},{sy(y):.1f}' for x, y in ring.coords) + 'Z '
    return out
view = box(x0, y0, x1, y1)
parts = []
for rec, shp in zip(r.records(), r.shapes()):
    d = dict(zip(names, rec)); g = shape(shp.__geo_interface__).intersection(view)
    if g.is_empty or g.geom_type not in ('Polygon', 'MultiPolygon'): continue
    india = d['ADM0_A3'] == 'IND'
    parts.append(f"<path d='{path(g)}' fill='{'#f3b85e' if india else '#2c5a60'}' stroke='#0d2b30' stroke-width='1.2'/>")
pts = {'Gilgit': (74.31, 35.92), 'Muzaffarabad': (73.47, 34.37), 'Aksai Chin': (79.3, 35.2), 'Tawang': (91.86, 27.59), 'Itanagar': (93.62, 27.08)}
for n, (x, y) in pts.items():
    parts.append(f"<circle cx='{sx(x):.1f}' cy='{sy(y):.1f}' r='5' fill='#c0392b'/><text x='{sx(x)+8:.1f}' y='{sy(y)+5:.1f}' font-size='20' font-family='DejaVu Sans' fill='#fff'>{n}</text>")
open('india.svg', 'w').write(f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}'><rect width='100%' height='100%' fill='#103e46'/>{''.join(parts)}</svg>")
