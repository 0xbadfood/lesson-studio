# Geography: maps research and next steps (2026-10-22)

## Decisions (user, 2026-10-22)

- **Its own studio.** Geography is the exception among the humanities because of maps. It gets its own studio,
  separate from History Studio's social-science subjects.
- **India as the textbooks show it.** Maps show only what NCERT shows as Indian territory:
  - all of Jammu & Kashmir and Ladakh, including PoK, Gilgit-Baltistan, Shaksgam and Aksai Chin;
  - all of Arunachal Pradesh.
- **A key-location check.** Disputed places must fall inside India, and inside no neighbour, on every map that shows
  India. A wrong boundary must not be able to reach a film.
- **Drawn by code, with a kit where it helps.** The image model never draws a map. Image briefs carry no maps, and
  generated pictures containing a map are rejected.
- **Licences.**
  - Usual: Apache/MIT/BSD/CC0/CC BY/public domain.
  - CC BY-SA is acceptable for a map case by case, when an online map is very good and hard or expensive to
    recreate. It is credited on screen.
  - Even a good online SVG must pass the disputed-place check before use. Most Wikimedia maps of India show the
    international (split Kashmir) view.

## Country boundaries: solved (public domain)

- **Source.** Natural Earth publishes its admin-0 countries in about 30 national points of view, India among them
  (country code `ind`). It is public domain.
  - File: `https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries_ind.zip` (v5.1.1).
  - The default Natural Earth layer follows de facto control. The point-of-view files follow each country's legal
    (de jure) claims.
- **Check result (2026-10-22).** Every test place lies inside India's polygon and in no other country:

  | Area | Places tested |
  |---|---|
  | PoK | Muzaffarabad, Mirpur |
  | Gilgit-Baltistan | Gilgit, Skardu |
  | Other disputed areas | Shaksgam valley, Aksai Chin (centre), Siachen glacier |
  | J&K and Ladakh | Leh, Srinagar |
  | Arunachal Pradesh | Tawang, Itanagar, Kibithu |
  | Gujarat | Sir Creek area |

- **By eye.** Drawn, the outline matches the NCERT and Survey of India political map: the full northern crown with
  Gilgit-Baltistan and Aksai Chin, and all of Arunachal.
- **The neighbours.** The same file gives the neighbours from India's point of view, so world and South Asia maps
  are consistent.
- **Islands.** Port Blair is inside. Kavaratti, Minicoy and Indira Point fall 0.001–0.009° (≈100 m–1 km) outside,
  because the 1:10m coastline is coarse at that scale. The check should accept island points within about 2 km of
  the coast.

## State and UT boundaries: open

| Source | Licence | Problem |
|---|---|---|
| [DataMeet states](https://projects.datameet.org/maps/states) | CC BY 2.5 India (credit) | Built from Election Commission data, not the Survey of India. DataMeet warns that J&K is pre-2019 and that some names are wrong or missing. Telangana may still be merged with Andhra Pradesh. |
| Survey of India external boundaries ([2018 release](https://thejeshgn.com/2018/11/15/download-official-external-boundaries-of-india-by-survey-of-india/)) and its 1:1M administrative data ([portal](https://en.vikaspedia.in/viewcontent/education/interactive-resources/online-maps-portal-of-survey-of-india)) | Never clearly stated | One old SoI-credited dataset is [non-commercial only](https://geo.btaa.org/catalog/stanford-fs571ym1942/metadata). |
| [SoI-based shapefile, updated Jan 2020](https://github.com/AnujTiwari/India-State-and-Country-Shapefile-Updated-Jan-2020) | Not confirmed | Has the 2019 J&K/Ladakh split. |

**Proposed approach:** DataMeet's states, clipped to the Natural Earth India outline, with the post-2019 fix made in
code.
- Clip DataMeet's states to India's point-of-view outline. The land no state covers is exactly the disputed area.
- Assign that land as the official 2019 map does:
  - Gilgit-Baltistan, Shaksgam and Aksai Chin go to **Ladakh**;
  - Muzaffarabad and Mirpur (PoK) go to the **UT of Jammu & Kashmir**.
- Split Andhra Pradesh and Telangana if the current DataMeet files still merge them.
- Extend the check to states: Gilgit in Ladakh, Muzaffarabad in J&K, Tawang in Arunachal Pradesh, Hyderabad in
  Telangana.
- **Credit line:** "State boundaries: DataMeet (CC BY 2.5 IN); country boundaries: Natural Earth (public domain)."

## Other map data (public domain)

- Natural Earth rivers, lakes, coastline, graticules, populated places and physical labels: mountain ranges,
  plateaus, seas.
- Natural Earth shaded relief and cross-blended hypsometric rasters for physical maps.
- **Thematic maps** (soils, crops, rainfall, minerals, vegetation, industries): the facts come from the book's text
  ("black soil: Maharashtra, Gujarat, Madhya Pradesh…") and code draws them. We do not trace NCERT's own maps.

## Next steps

1. **Boundary data.** Natural Earth outline plus DataMeet states with the 2019 split, checked by the disputed-place
   and per-state tests.
2. **Comparison.** Put our political map of India side by side with the NCERT Class 10 political map.
3. **Map inventory.** List every map the geography books use, as was done for biology
   (`~/biology/diagram-requirements.md`):
   - Contemporary India (Class 9 iess1, Class 10 jess1);
   - Fundamentals of Physical Geography and India: Physical Environment (Class 11);
   - Human Geography and India: People and Economy (Class 12);
   - the geography chapters of the Class 6–8 social-science books.
4. **Map kit** (`figure_library/geo.py`), checked like the chemistry and biology figures:
   - political maps (highlight states);
   - physical maps (relief, rivers, ranges);
   - choropleths by state or region;
   - points (cities, ports, dams, parks);
   - arrows (monsoon winds, currents);
   - world maps (continents, plates, latitudes and longitudes, time zones);
   - labels placed by code.
5. **Image guard.** No maps in image briefs, and the image check rejects generated pictures containing a map.
6. **Geography Studio.** A profile like History, Chemistry and Biology, with the map kit as its figures.

## Working files

`geography/research/` holds:
- `check.py`: the disputed-place test (`python check.py <ne_10m_admin_0_countries_ind.shp>`);
- `draw.py`, `india.png`: the drawn outline.

They need shapely and pyshp, and the Natural Earth file above. The kit will need shapely and pyshp in the film's
Python environment.
