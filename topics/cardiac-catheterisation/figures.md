# Figures for "Looking inside your child's heart: the cath test" (topic-cardiac-catheterisation)

Four figures, ids as in `source.figures`. Audience: parents with no biology background, so keep each
picture calm and diagrammatic (medical-illustration style, no blood, no distressed child, no real
patient). Every part the narration names gets its own id (`part-...`) so the film can light it.
Sources are the ones cited in `digest.json`; a detail with no source here should not be drawn.

Colour convention for all four: oxygen-poor blood blue, oxygen-rich blood red (as in NCERT Fig. 15.2
style); catheter and sheath a neutral off-white or pale yellow so they read against both.

---

## 1. `heart-chambers` - a see-through four-chamber heart (shared)

**What it shows:** a front view of the heart, as if the front wall were glass, all four chambers
and the great vessels visible, labelled. Used for B1 and as the base for `cath-pressures`.

Parts (ids) - the viewer's left is the child's right, as in every textbook front view:
- `part-right-atrium` (upper chamber, viewer's left), `part-right-ventricle` (lower, viewer's left)
- `part-left-atrium` (upper, viewer's right, sits towards the back), `part-left-ventricle`
  (lower, viewer's right; thickest wall)
- `part-superior-vena-cava` (enters the right atrium from above) and `part-inferior-vena-cava`
  (enters the right atrium from below) - together "the big veins, the venae cavae"
- `part-pulmonary-artery` (leaves the right ventricle, splits into left and right branches,
  `part-pulmonary-branches`, going to the lungs)
- `part-pulmonary-veins` (bring blood from the lungs into the left atrium)
- `part-aorta` (leaves the left ventricle, arches over the top)
- `part-septum` (the wall between left and right sides: interatrial septum above, thicker
  interventricular septum below)
- `part-tricuspid-valve`, `part-mitral-valve` (between atria and ventricles; NCERT calls the left
  one bicuspid), `part-pulmonary-valve`, `part-aortic-valve` (the semilunar valves at the exits)

Stages (in order):
1. Plain heart, chambers labelled.
2. Blue path lights: venae cavae -> right atrium -> right ventricle -> pulmonary artery -> lungs
   (the lung journey).
3. Red path lights: pulmonary veins -> left atrium -> left ventricle -> aorta -> body
   (the body journey).
4. Valves pulse once to show one-way flow.

Source: NCERT Class 11 Biology Ch 15 (four chambers, septa, valves, pulmonary and systemic
circulation, venae cavae into the right atrium, pulmonary veins into the left atrium),
https://ncert.nic.in/textbook/pdf/kebo115.pdf

---

## 2. `catheter-entry` - the way in at the groin, and the route up to the heart

**What it shows:** a child's body outline lying on its back (simple, sleeping, covered with a sheet
except the groin), with the main blood vessels drawn see-through from the top of the leg up to the
heart. Used for B6, B7, B8.

Parts (ids):
- `part-groin` - the crease at the top of the leg, where the needle hole is made
- `part-femoral-vein` (blue) and `part-femoral-artery` (red), side by side in the groin. **The vein
  lies on the inner side of the artery** (towards the middle of the body), about 0.3-1 cm apart in a
  child; the puncture is about 1-3 cm below the groin crease.
- `part-sheath` - a short plastic tube sitting in the vessel at the skin, with a cap/valve outside.
  KidsHealth describes it as "about the size of a coffee straw" (but in a baby it is smaller -
  see uncertainty note). Draw one sheath in the vein and, optionally, a second in the artery.
- `part-catheter` - the thin, flexible tube passing through the sheath; `part-catheter-tip` - its end
- `part-inferior-vena-cava` (the big vein running up the belly to the heart) and `part-aorta`
  (the big artery running alongside it, down from the heart)
- `part-neck-vein` - a faint alternative entry point on the side of the neck (sometimes used),
  shown only as a small dotted marker, not a second full route
- `part-heart` - the heart outline at the top (can reuse `heart-chambers`, simplified)

Stages (in order):
1. The groin area: vein and artery side by side, labelled.
2. A small needle hole, then the sheath sits in the vein.
3. The catheter slides through the sheath and travels **up the femoral vein -> inferior vena cava
   -> right atrium** (venous route, to the right side of the heart).
4. (Optional, for B8) A second catheter in the artery travels **up the femoral artery -> the aorta,
   against the flow, round to the heart -> through the aortic valve into the left ventricle**
   (arterial route, to the left side).
5. Dotted marker: "sometimes a vein in the neck is used instead".

Sources:
- Groin puncture with a needle, neck vessel sometimes used, plastic sheath that lets the catheter in
  safely and stops bleeding: Seattle Children's,
  https://www.seattlechildrens.org/clinics/heart/what-to-expect/cardiac-cath/
- Sheath "about the size of a coffee straw", usually in the groin: Nemours KidsHealth,
  https://kidshealth.org/en/parents/cardiac-catheter.html
- Femoral vein lies medial to the femoral artery (0.3-1 cm), puncture 1-3 cm below the groin, a
  femoral catheter's tip lies in the inferior vena cava or the right atrium: Trieschmann et al.,
  Central venous catheters in children and neonates (Part 3) - Access via the femoral vein,
  Images Paediatr Cardiol 2008 (CC BY-NC-SA 3.0), https://pmc.ncbi.nlm.nih.gov/articles/PMC3232590/
- Vein route up to the right atrium: Boston Children's,
  https://www.childrenshospital.org/treatments/cardiac-catheterization
- Artery route through the aortic valve into the left side: MedlinePlus,
  https://medlineplus.gov/ency/article/003871.htm

---

## 3. `cath-pressures` - the catheter visits each chamber: pressures and oxygen samples

**What it shows:** the see-through heart from `heart-chambers`, with the catheter inside and a
simple bedside monitor beside it. At each stop the tip glows, a small "pressure wave" trace appears
on the monitor and a tiny sample tube with an oxygen reading symbol (e.g. a drop with "O2") appears.
**Do not print real numbers** - no source gives child values for the film to quote.

Parts (ids):
- `part-catheter`, `part-catheter-tip`
- `part-superior-vena-cava`, `part-inferior-vena-cava`, `part-right-atrium`, `part-right-ventricle`,
  `part-pulmonary-artery`, `part-pulmonary-branches`
- `part-aorta`, `part-aortic-valve`, `part-left-ventricle`
- `part-monitor` - a screen showing the pressure trace (a repeating wave) and the ECG
- `part-sample` - small blood-sample syringe/tube; `part-oxygen-reading` - an icon, not a number

Stops, in the order a catheter usually visits them:
- **Via the vein (right side):** right atrium -> right ventricle -> pulmonary artery -> pulmonary
  artery branches. (Boston Children's: "up the vein toward the right atrium", then the right
  ventricle, the pulmonary artery, and possibly its branches; samples from several vessels and
  chambers; pressures measured.)
- **Via the artery (left side):** up the aorta -> across the aortic valve -> left ventricle
  (MedlinePlus: through the aortic valve into the left side; pressures measured).

Stages: (1) tip in right atrium, trace + sample; (2) right ventricle; (3) pulmonary artery;
(4) branches; (5) second catheter in aorta; (6) left ventricle. A final frame shows all stops lit
together: "pressures and oxygen in each part of the heart".

Sources:
- Oxygen levels and pressures in each of the parts of the heart: Stanford Children's FAQ,
  https://www.stanfordchildrens.org/en/services/cardiac-catheterization-angiography/faq.html
- Small blood samples to measure oxygen levels in the different chambers; ECG and pressure traces:
  Alder Hey PIAG 106,
  https://www.alderhey.nhs.uk/wp-content/uploads/2023/06/Cardiac-Catheterisation-Radiology-Leaflet-PIAG-106.pdf
- Right-side order: Boston Children's (above). Left-side route: MedlinePlus (above).

---

## 4. `angiogram-view` - what an angiogram looks like

**What it shows:** what a parent would see on the cath-lab screen. Two panels, side by side,
because the X-ray machine takes pictures from the front and from the side at the same time.

Look: a **grey, black-and-white X-ray** image - soft grey shadows of the chest, the ribs and spine
faintly visible, the heart a pale grey shape. The catheter is a thin dark line. When the dye is
injected, the chamber or vessel it fills turns **dark (near black) and sharply outlined**, and the
dye can be seen moving on along the blood's path, then fading as it washes out. No colour on the
X-ray itself (labels may be coloured).

Parts (ids): `part-xray-front`, `part-xray-side`, `part-catheter` (dark line), `part-dye`
(the dark filled region), `part-ribs`, `part-spine`, `part-screen` (the monitor frame).

Stages (in order):
1. Empty grey X-ray, catheter line visible (fluoroscopy, the moving X-ray used throughout).
2. Dye puff: one chamber fills dark (e.g. right ventricle).
3. The dark dye flows on into the pulmonary artery and its branches (shows the blood's path).
4. Dye fades. Caption idea: "several pictures, from different angles".

Sources:
- Moving X-ray pictures, dye (contrast agent) shows up on X-ray, image intensifier takes pictures
  from above and from the side at the same time: Alder Hey PIAG 106 (above)
- Fluoroscopy on an X-ray monitor, X-ray pictures called angiograms, several injections with the
  catheter moved for different views: UCSF Benioff Children's,
  https://www.ucsfbenioffchildrens.org/education/cardiac-catheterization
- Low-dose X-ray shown on a TV monitor; dye makes the arteries show up more clearly: Royal Brompton,
  https://www.rbht.nhs.uk/sites/nhs/files/Leaflets/Cardiac%20catherisation%20for%20children-web.pdf
- X-ray shows the anatomy and the path the dye takes through the heart: Stanford Children's FAQ (above)

Note for the illustrator: dye is radio-opaque, so on a standard (non-inverted) X-ray it appears as
the **darkest** part of the image on most cath-lab displays, not white. This is the usual cath-lab
display convention; it is not stated in a cited source (see uncertainty note), so if in doubt
ask the reviewer before painting.

---

## Uncertain points for the reviewer

- **Left side from the vein.** In many children the left side is reached from the vein, crossing a
  hole between the atria (or a planned puncture of the septum), not only from the artery; SCAI notes
  a "prograde approach from the femoral vein" as an alternative to arterial access in infants under
  4 kg. No parent source describes this, so it is not in the digest or the figures.
- **Sheath size.** "About the size of a coffee straw" (KidsHealth) suits an older child; sheaths in
  babies are smaller (SCAI mentions 3.3 Fr for infants under 4 kg). Draw it modest.
- **Dye dark vs white.** The display convention is not stated in a cited source.
