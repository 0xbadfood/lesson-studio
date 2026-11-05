# Figures for "Closing an open ductus with a tiny plug" (topic-pda-device-closure)

Audience: parents, no biology background. Labels plain first, the medical word second (as in pda-heart-front).
Every detail below is backed by a source the digest cites; block numbers refer to `digest.json`.

## 1. `pda-heart-front` (exists: ~/biology/svg/clinical/pda-heart-front.json)

A see-through front view of a newborn heart with the aorta, the pulmonary artery and the ductus between them.
Reuse its base and parts `part-aorta`, `part-pulmonary-artery`, `part-heart`, `part-lungs-right`. Its current
stages were drawn for the stenting film (keeping the duct open); this film needs its own stages, added beside them:

| Order | Stage (new id) | What it shows | Parts lit by narration |
|---|---|---|---|
| 1 | `stage-closure-before-birth` | The ductus wide open, joining the pulmonary artery to the aorta (B2). No flow arrow needed, or a soft one "bypassing the lungs". | `part-ductus` ("The ductus, from before birth"), `part-aorta`, `part-pulmonary-artery` |
| 2 | `stage-closure-normal` | The ductus closed after birth: a thin shut cord (B2). | `part-ductus` ("Closed after birth") |
| 3 | `stage-closure-pda` | The ductus still open; an arrow of extra blood **from the aorta into the pulmonary artery**, then on to the lungs (B3). Optional: lungs slightly flushed to read as "overloaded". | `part-ductus` ("The ductus, still open (PDA)"), `part-flow` ("Extra blood to the lungs") |
| 4 | `stage-closure-occluder` | The plug sitting inside the ductus, no arrow through it (B9, B11, B13). | `part-ductus`, `part-occluder` ("Tiny mesh plug (duct occluder)") |
| 5 (optional) | `stage-closure-coil` | Same as 4 with a small tangled coil inside a narrower ductus instead of the plug (B10). | `part-coil` ("Coil") |

Accuracy notes:
- Flow direction in a PDA is aorta to pulmonary artery (Cincinnati Children's, B3). This is the same direction
  the existing stent-film flow arrow uses, but the label must say "extra blood to the lungs", not "blood to the lungs".
- The plug lies **inside** the ductus (SCHN: "placed inside the PDA"; Baruteau 2023: entirely inside the ductus in
  babies under 2 kg). It must not bulge into the aorta or narrow the pulmonary artery: the team checks exactly that
  before release (Soweto 2018, B12).
- The device is a fine wire mesh (GOSH, B11). Over time the heart's lining grows over it (SCHN, B13): an optional
  final stage could show the plug softly covered.
- Draw the normal valves and chambers; this film has no blocked valve (do not reuse `stage-valve-blocked`).

## 2. `catheter-entry` (new; shared with the other catheter films)

The baby or child lying on their back, lower body and chest, with a see-through path from the groin to the heart.

| Order | Stage | What it shows | Parts lit |
|---|---|---|---|
| 1 | `stage-entry-groin` | A small entry point at the top of the leg (groin) with a short sheath, a little tube that stays in the vessel while catheters pass through it. | `part-groin-entry`, `part-sheath` |
| 2 | `stage-entry-vein` | A catheter in the **femoral vein**, running up the big vein below the heart (inferior vena cava) into the right side of the heart. | `part-femoral-vein`, `part-catheter-vein` |
| 3 | `stage-entry-artery` | A second catheter in the **femoral artery**, running up the aorta from below, stopping close to the ductus. | `part-femoral-artery`, `part-catheter-artery` |
| 4 (septostomy only) | `stage-entry-umbilical-vein` | Catheter entering through the belly button (umbilical vein) and up to the right atrium. See the septostomy topic's figures.md. | `part-belly-button`, `part-umbilical-vein` |

Accuracy notes for this film:
- The catheter goes in at the groin, at the top of the leg (SCHN B9; GOSH says "the vein at the top of the leg", B11).
- In older children both the femoral vein and the femoral artery may be used; plugs are usually brought from the
  lung-artery side (through the vein and the right heart), most coils from the aorta side (through the artery)
  (Soweto 2018, B12). Cincinnati's family page describes catheters from the groin threaded up the aorta to the
  ductus (B10). So stage 2 and stage 3 can both appear in the film.
- In very small premature babies **only the vein** is used, no artery (Baruteau 2023, B7): the narration for that
  case lights stage 2 only.
- The sheath is a small tube left in the femoral vein (Baruteau 2023: a 4-French sheath in the femoral vein).
- Venous path to the ductus (Baruteau 2023): femoral vein, inferior vena cava, right atrium, right ventricle,
  pulmonary artery, then across the ductus into the descending aorta. Draw the catheter following this path.
- Keep the child's proportions plain: the vessels run up the inside of the belly, not the back.

## 3. `pda-occluder-steps` (new)

A close-up of the aorta, the ductus and the pulmonary artery (same orientation as `pda-heart-front`), showing the
plug being placed. Stages in order:

| Order | Stage | What it shows | Parts lit |
|---|---|---|---|
| 1 | `stage-steps-picture` | The open ductus with a catheter tip near it; dye filling it, showing its shape and size (angiogram, B10). | `part-ductus`, `part-catheter` |
| 2 | `stage-steps-across` | The delivery catheter passed through the ductus (for a plug: coming from the pulmonary artery side, B12; in tiny babies across into the aorta, B7). | `part-catheter` |
| 3 | `stage-steps-plug-out` | The folded mesh plug pushed out of the catheter tip and opening inside the ductus, still attached to its delivery wire. | `part-occluder`, `part-delivery-wire` |
| 4 | `stage-steps-check` | Plug in place, still attached; a scan/X-ray "check" cue; the aorta shown clear and unnarrowed (B11, B12). | `part-occluder`, `part-aorta` ("Main artery kept clear") |
| 5 | `stage-steps-released` | Wire detached and catheter withdrawn; the plug stays; no flow through the ductus (B11). | `part-occluder` |

Accuracy notes:
- The device is released **only after** its position is confirmed by echocardiogram and X-ray (GOSH, B11), and
  after checking that it does not block the flow in the aorta (Soweto, B12). Stage 4 must come before stage 5.
- If it is not right, it can be taken back into the catheter (Soweto, B12): an optional "pulled back" frame is
  accurate, but the narration need not show it.
- A coil variant is optional (B10: coil for a small ductus, plug-shaped device for a larger one).
- Do not show device brand shapes in detail; a simple mesh plug with a slightly wider rim at each end is enough
  (Baruteau 2023 describes the premature-baby device as a mesh with low discs at both ends).

Sources: GOSH PDA family page; SCHN transcatheter closure factsheet; Cincinnati Children's PDA page;
Baruteau et al. 2023 (PMC10744056, CC BY); Adams Paul et al. 2018 (PMC6421553). URLs are in `digest.json`.
