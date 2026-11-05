# Figures for "A balloon to help a newborn's blood mix" (topic-balloon-atrial-septostomy)

Audience: parents, no biology background. Labels plain first, the medical word second.
Every detail below is backed by a source the digest cites; block numbers refer to `digest.json`.
Colour code: oxygen-rich blood red, oxygen-poor blood blue (the families' pages use "red" and "blue" blood:
SickKids B4, Alder Hey).

## 1. `heart-chambers` (new; shared see-through four-chamber heart, stages added per topic)

A see-through front view of a newborn heart cut open to show all four chambers, with the big veins coming in and
the two big arteries going out. Base parts (shared by every topic that uses it):
`part-right-atrium`, `part-left-atrium`, `part-right-ventricle`, `part-left-ventricle`, `part-interatrial-septum`
("Wall between the upper chambers"), `part-interventricular-septum`, `part-aorta`, `part-pulmonary-artery`,
`part-superior-vena-cava`, `part-inferior-vena-cava`, `part-pulmonary-veins`, `part-tricuspid-valve`, `part-mitral-valve`.
Viewer's left = the baby's right side (standard front view).

Stages for this topic, in order:

| Order | Stage | What it shows | Parts lit by narration |
|---|---|---|---|
| 1 | `stage-bas-normal-loops` | Normal heart: blue blood into the right atrium, right ventricle, out the pulmonary artery to the lungs; red blood back from the lungs into the left atrium, left ventricle, out the aorta to the body (B1). | `part-right-atrium`, `part-left-atrium`, `part-right-ventricle`, `part-left-ventricle`, `part-aorta`, `part-pulmonary-artery`, `part-interatrial-septum` |
| 2 | `stage-bas-before-birth` | The foramen ovale open in the wall between the atria, with an arrow from the right atrium across into the left atrium (B2). | `part-foramen-ovale` ("Opening from before birth (foramen ovale)"), `part-flow-across` |
| 3 | `stage-bas-after-birth` | The foramen ovale closed to a slit (flap shut) after birth (B2). | `part-foramen-ovale` ("Closes after birth") |

Accuracy notes:
- The interatrial septum is a thin muscular wall between the two atria (NCERT, B1).
- Before birth most of the blood entering the right atrium crosses to the left atrium through the foramen ovale
  (Stanford, B2): the arrow goes right atrium to left atrium.
- The foramen ovale sits in the middle of the wall between the atria; draw it as a small oval flap-door.

## 2. `transposition-heart` (new)

The same four-chamber heart (reuse the `heart-chambers` base) with the two great arteries swapped.

| Order | Stage | What it shows | Parts lit |
|---|---|---|---|
| 1 | `stage-tga-swapped` | Aorta rising from the **right** ventricle, pulmonary artery from the **left** ventricle (B3). | `part-aorta` ("Main artery to the body (aorta)"), `part-pulmonary-artery` ("Artery to the lungs") |
| 2 | `stage-tga-two-circles` | Two separate loops: blue blood body to right heart to aorta and back to the body; red blood lungs to left heart to pulmonary artery and back to the lungs (B3, B4). Two closed circular arrows, one blue, one red, not touching. | `part-loop-body` ("Blue blood goes round the body"), `part-loop-lungs` ("Red blood goes round the lungs") |
| 3 | `stage-tga-mixing-small` | A small foramen ovale and an open ductus arteriosus, with a thin purple mixing arrow at each (B4, B5). | `part-foramen-ovale` ("Small opening"), `part-ductus` ("Ductus, kept open by medicine") |
| 4 | `stage-tga-mixing-big` | After the septostomy: a large opening in the wall between the atria, with a wide arrow of red blood from the left atrium into the right atrium, and the aorta's blood a more mixed colour (B6). | `part-septostomy-opening` ("Bigger opening"), `part-flow-mixing` ("Blood mixes") |

Accuracy notes:
- In TGA the aorta comes from the right ventricle and the pulmonary artery from the left (SickKids TGA, B3; also
  the WA guideline).
- After the septostomy the mixing at atrial level is described as blood high in oxygen in the left atrium mixing
  with blood low in oxygen in the right atrium, so blood higher in oxygen goes out the aorta (SickKids TGA, B6):
  draw the main mixing arrow left atrium to right atrium.
- Keep the ventricles in their normal places; only the arteries are swapped. Do not add a ventricular septal
  defect (this film's babies are described without one, B7), but a later variant could add it.
- The ductus in TGA runs between the aorta and the pulmonary artery like in the PDA films; position it the same
  way as in `pda-heart-front`.

## 3. `septostomy-steps` (new)

A close-up of the two atria and the wall between them (same orientation as `heart-chambers`), with the
inferior vena cava entering the right atrium from below. Stages in order:

| Order | Stage | What it shows | Parts lit |
|---|---|---|---|
| 1 | `stage-bas-entry` | Catheter coming up the inferior vena cava into the right atrium (B10). | `part-catheter`, `part-inferior-vena-cava` |
| 2 | `stage-bas-across` | Catheter tip passed through the small foramen ovale into the left atrium, balloon still empty (B10, B11). | `part-catheter`, `part-foramen-ovale`, `part-balloon` ("Balloon, empty") |
| 3 | `stage-bas-inflate` | Balloon filled in the middle of the left atrium, clear of the mitral valve and the pulmonary veins (B12). | `part-balloon` ("Balloon, filled") |
| 4 | `stage-bas-pull` | Balloon pulled back against the wall, then through it into the right atrium, the edge of the opening torn (B11, B12). Motion arrow points **from the left atrium to the right atrium** (towards the inferior vena cava, but stopping in the right atrium). | `part-balloon`, `part-interatrial-septum`, `part-pull-arrow` ("Pulled back across") |
| 5 | `stage-bas-bigger` | Balloon emptied and catheter withdrawn; a much larger opening left in the wall, with blood crossing (B11, B12). | `part-septostomy-opening` ("Bigger opening") |

Accuracy notes:
- The balloon is filled in the **left** atrium and pulled back into the **right** atrium (SickKids BAS B11;
  Alder Hey; WA guideline B12). Never draw it pushed from right to left.
- The team keeps the filled balloon away from the valve between the upper and lower chambers and the pulmonary
  veins before pulling, and takes care not to pull it on into the inferior vena cava (WA guideline, B12): in
  stage 4, the balloon stops in the right atrium.
- The pull is described as gentle onto the wall, then a quick controlled tug (WA guideline, B12). An optional
  repeat of stages 3 to 5 is accurate (the pull can be repeated if the flow is not enough).
- The whole procedure is watched on an ultrasound screen (SickKids BAS B8; WA guideline B10, B12): a small
  ultrasound-probe inset is accurate; an X-ray machine should not be the main picture (bedside procedure).

## `catheter-entry` notes for this topic (figure shared with the device-closure films)

This film uses two entry stages of the shared `catheter-entry` figure:
- `stage-entry-umbilical-vein`: the catheter goes in through the belly button (umbilical vein) and up to the
  right atrium (WA guideline B10; Alder Hey, SickKids BAS: "groin or belly button"). Show the newborn's umbilical
  stump and the catheter running up inside the belly to the inferior vena cava and into the right atrium. (The
  exact course of the umbilical vein through the liver region is not described by our sources: keep it
  schematic, and ask the cardiologist reviewer before drawing it in anatomical detail.)
- `stage-entry-vein`: the femoral vein at the groin, up the inferior vena cava into the right atrium (WA guideline B10).
No artery is used for a septostomy: both routes are veins (WA guideline B10). This film does not list
`catheter-entry` in its figures; if the planner wants an entry picture, these are the stages to add.

Sources: NCERT Class 11 Biology Ch 15; Stanford Medicine Children's Health (fetal circulation); SickKids
AboutKidsHealth (TGA; balloon atrial septostomy); Alder Hey PIAG 275; CAHS Western Australia BAS guideline.
URLs are in `digest.json`.
