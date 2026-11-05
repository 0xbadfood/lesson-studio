# Figures for "Closing a hole between the heart's lower chambers" (topic-vsd-device-closure)

Audience: parents, no biology background. Level: figure_class 10 (clear, labelled, not textbook-dense).
Style: see-through child's heart, front view (the child's right is the viewer's left), oxygen-poor blood blue,
oxygen-rich blood red, device metal grey. Every part named below is a separate, lightable group with the id given
(`part-...`), so the narration can light it.

Sources referred to (short names as in digest.json):
- NCERT = NCERT Class 11 Biology Ch 15 (kebo115.pdf)
- SCHN = Sydney Children's Hospitals Network, VSD transcatheter device closure factsheet
- BHF = British Heart Foundation, Ventricular septal defect
- CINCI = Cincinnati Children's, Ventricular Septal Defect
- AKH = SickKids AboutKidsHealth, VSD closure in the heart catheterization lab
- NICE = NICE HealthTech guidance 213 (ex IPG336), transcatheter closure of perimembranous VSD
- BERG = Bergmann et al., Pediatric Cardiology 2021 (PMC7864847)
- FR = Device closure of perimembranous VSD: choosing between Amplatzer occluders, Frontiers in Pediatrics 2019

---

## 1. `heart-chambers` (shared with other topics)

A see-through four-chamber child's heart. Shared figure: stages `normal`, `asd`, `vsd` (and others added by
other topics). This film uses `normal`, `wiring` and `vsd`. Parts common to all stages are as in the ASD topic's
figures.md (`part-right-atrium`, `part-left-atrium`, `part-right-ventricle`, `part-left-ventricle`,
`part-atrial-septum`, `part-ventricular-septum`, `part-vena-cava`, `part-pulmonary-veins`,
`part-pulmonary-artery`, `part-aorta`, the four valves), all from NCERT. The ventricular septum is THICK and
muscular (NCERT: "a thick-walled, the inter-ventricular septum"); its upper part, just under the aortic valve, is
a small thin membranous patch (the reason "perimembranous" holes sit near the valves - BHF "near your heart
valves").

Stage `wiring` (new, used by this film for heart block):
- `part-sa-node`: small patch in the upper right corner of the right atrium. NCERT ("sino-atrial node (SAN) ... in
  the right upper corner of the right atrium").
- `part-av-node`: in the lower left corner of the right atrium, near the septum between atria and ventricles.
  NCERT ("atrio-ventricular node (AVN) ... lower left corner of the right atrium close to the atrio-ventricular
  septum").
- `part-av-bundle` (His bundle): runs from the AV node down to the TOP of the ventricular septum, then divides into
  `part-bundle-right` and `part-bundle-left` running down each side of the septum. NCERT ("emerge on the top of the
  interventricular septum and immediately divides into a right and left bundle"). Draw as a thin yellow line.

Stage `vsd`:
- `part-defect-perimembranous`: a hole in the upper part of the ventricular septum, just below the aortic valve and
  next to the tricuspid valve (BHF "near your heart valves"; BERG: suitability depends on "the distance to the
  aortic and tricuspid valve"). With `wiring` shown, the AV bundle passes along its LOWER BACK edge (FR: "the His
  bundle passes at the postero-inferior margin of pmVSD").
- `part-defect-muscular`: (alternative, separate group, lit on its own) a hole in the lower, muscular part of the
  septum, towards the tip of the heart (BHF: "Muscular VSD, in the lower part of the wall").
- `part-shunt-flow`: red arrow from the left ventricle through the hole into the right ventricle and up the
  pulmonary artery, thicker than normal (extra blood to the lungs). SCHN: "oxygen-rich blood from the left
  ventricle to flow into the right ventricle and back to the lungs".

## 2. `catheter-entry` (shared with other topics)

As in the ASD topic's figures.md (groin close-up, `part-femoral-vein`, `part-femoral-artery`, `part-sheath`,
`part-catheter`). This film uses BOTH routes:
- `route-vein`: femoral vein -> inferior vena cava -> right atrium -> through the tricuspid valve -> right
  ventricle (SCHN: catheter "placed in a blood vessel in the leg (groin)" and moved "up to the heart and across the
  hole"; BHF: "a vein at the top of your leg").
- `route-artery`: femoral artery -> up the aorta -> back through the aortic valve -> left ventricle. (BERG: "via a
  vein or artery".)
- Stage `wire-loop`: a single guidewire going in through the femoral vein, through the heart and the hole, and out
  through the femoral artery (or the reverse), forming a loop: `part-wire-loop`. NICE: "a guidewire is introduced
  into the femoral artery and vein in the groin, to establish an arteriovenous wire loop. A delivery sheath is
  advanced over the wire across the VSD, via the right or left side of the heart." `part-delivery-sheath` follows
  the wire across the hole.
- `part-toe-probe` (ultrasound probe in the food pipe, child asleep) and `part-xray` arc. SCHN, AKH.

## 3. `vsd-occluder-steps`

Close-up of the upper ventricular septum, cut through, right ventricle on the viewer's left, left ventricle on the
right, aortic valve just above the hole on the left-ventricle side, tricuspid valve leaflet near it on the
right-ventricle side, and the AV bundle (thin yellow line) along the lower back edge of the hole. Steps (stages):

1. `measure`: dye picture of the left ventricle and TOE outline of the hole (calipers across it). FR: "Left
   ventriculography ... combined to intraoperative TEE to accurately determine the pmVSD location, shape, depth,
   size and its relationship with adjacent aortic and tricuspid valves."
2. `sheath-across`: `part-delivery-sheath` across the hole, its tip in the LEFT ventricle (vein route), the device
   folded inside. AKH ("discs are folded so the device will fit in the catheter"); FR (antegrade route from the
   femoral vein).
3. `left-disc-opens`: `part-occluder-left-disc` opened in the left ventricle and pulled back flat against the left
   side of the septum. FR: "the distal disc was completely deployed at the LV side of the VSD".
4. `waist-in-hole`: `part-occluder-waist` filling the hole. FR: "deploy the waist of the device in the VSD"; AKH
   "The tube portion plugs the hole".
5. `right-disc-opens`: `part-occluder-right-disc` opened on the right ventricle side; septum held between the discs.
   FR ("retracted to deploy the proximal disc"); AKH ("the other disc opens up on the opposite side of the hole";
   discs of different sizes). Keep the left disc clear of the aortic valve leaflets.
6. `check`: device still on `part-delivery-cable`; TOE and dye-picture icons; highlight the aortic valve
   (`part-aortic-valve`) to show it is untouched, and the AV bundle (`part-av-bundle`). FR: "verify the position and
   the shape of the device, RS and the absence of interference with the AoV cusps" before release.
7. `release`: cable unscrewed and withdrawn (FR: "released by turning the cable counterclockwise"); no shunt arrow.
8. `healed`: thin pink tissue grown over the device; it is part of the wall. SCHN: "heart tissue gradually grows
   over it ... becomes part of the heart wall over time". No time label (the VSD sources give none).

Note for the illustrator: with the artery route (FR's retrograde approach for one device type) the order is
reversed - the first disc opens in the RIGHT ventricle and the second against the left side. The film's text says
only "first disc on one side, second on the other", so draw the vein route above as the main sequence.

Device appearance: a double disc (or plug) of fine metal mesh with a short waist (SCHN: "a small plug or double
disc made of fine mesh"; AKH "metal and mesh material", "short tube with different-sized discs"). Generic, no brand
or logo. For a muscular hole the same double-disc device sits lower in the thick muscular septum.

Not to draw: a heart-block ECG trace or a pacemaker (the film states this risk in words; keep imagery calm).
