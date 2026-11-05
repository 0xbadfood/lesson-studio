# Figures: Widening a narrow main artery with a balloon (topic-balloon-coarctoplasty)

Painted later (painted base plus vector overlays). Audience: parents, figure level Class 10. Each stage is one
picture state; the parts listed under a stage are the ones the narration names and lights. Part ids follow the house
pattern (`part-<thing>`); a stage's parts become `part-<stage>-<thing>` in the sidecar, with a `part_map` back to
these names. Sources are cited as [n] and listed at the end.

---

## 1. `pda-heart-front` (exists; needs new coarctation stages)

The existing figure (`~/biology/svg/clinical/pda-heart-front.json`) is a see-through front view of a newborn heart
with the aorta, the pulmonary artery and the ductus, and has stages for the PDA-stent film (`stage-duct-open`,
`stage-valve-blocked`, `stage-duct-closing`, `stage-stent-in-place`). Its parts today are `part-aorta`,
`part-pulmonary-artery`, `part-lungs-right`, `part-heart`, and per-stage ductus/flow/stent parts. **It has no
coarctation, no arch branches and no descending aorta part**, so the coarctation film needs these added (new stages
on the same base painting, or a sibling figure if the base does not show the arch and the start of the descending
aorta clearly).

Where the narrowing sits [1][2][3][4][5]: on the aorta just after it has given off the arteries to the head and arms
(brachiocephalic, left common carotid, left subclavian, in that order along the arch: standard anatomy, not from the
cited pages), i.e. **just beyond (downstream
of) the left subclavian artery**, at the short segment called the isthmus, **opposite the place where the ductus joins
the aorta** (juxtaductal). The narrowing is mainly a shelf of tissue projecting from the **back** wall of the aorta
[2][4]. In some babies the arch before the narrowing is also small (arch hypoplasia) [1]; draw a normal-calibre arch
here.

**Flow direction warning.** In the PDA-stent film the ductus flow arrow runs from the aorta into the pulmonary
artery (to the lungs). In a newborn with critical coarctation kept on prostaglandin, the open ductus carries blood the
other way: from the pulmonary artery into the aorta beyond the narrowing, to reach the lower body [1]. Do not reuse the
PDA flow parts for the coarctation stages.

New stages, in order:

1. `stage-coarctation`: the narrowing [1][2][3]. Aorta from the left ventricle up into the arch, three branches to head
   and arms, then the waist-like narrowing just past the left subclavian artery, then the descending aorta running down
   behind the heart. A thin, fast jet through the narrowing; the flow beyond it reduced (thinner arrow to the lower
   body). The left ventricle shown working harder (a subtle thick-wall cue is enough) [1][2].
   Parts: `part-coarctation`, `part-aortic-arch`, `part-left-subclavian`, `part-head-arm-arteries`,
   `part-descending-aorta`, `part-left-ventricle`, `part-ductus`.
2. `stage-ductus-open-on-medicine` [1][2]. The ductus held open by prostaglandin; blue-purple arrow from the
   pulmonary artery through the ductus into the descending aorta, below the narrowing, towards the lower body.
   Parts: `part-ductus`, `part-ductal-flow-to-body`, `part-coarctation`.
3. `stage-ductus-closed` [1][2][4]. The ductus closed (thin cord); the narrowing tighter as the ductal tissue in the
   aortic wall contracts; very little flow to the lower body; the left ventricle under strain (it may weaken in severe
   cases [2]).
   Parts: `part-ductus-closed`, `part-coarctation`, `part-left-ventricle`, `part-lower-body-flow`.

## 2. `catheter-entry`: where the thin tube goes in (shared with topic-balloon-pulmonary-valvuloplasty)

Same figure as in the BPV figures.md (a small child on their back, heart and main vessels faint inside). The
coarctation film uses:

3. `stage-groin-artery` [6][7]. Entry at the groin into the femoral artery (an artery, not the vein). The catheter
   runs up the leg artery into the aorta in the belly, then up the descending aorta in the chest, **against the flow of
   blood**, to the narrowing just beyond the arch [7]. The wire is passed on through the narrowing and its tip parked
   in the ascending aorta, close to the heart [7].
   Parts: `part-entry-groin`, `part-femoral-artery`, `part-catheter`, `part-aorta`, `part-coarctation`.
4. `stage-wrist-artery` (optional) [7]. In one infant in the New Delhi series the narrowing was crossed from the radial
   artery at the wrist, going with the flow; show only if the narration uses it.

The BPV film uses `stage-groin-vein` and `stage-neck-vein` from the same figure (see the BPV figures.md); the vein
and artery stages must not be confused.

## 3. `coarctation-balloon`: close-up of the narrow part being widened

Close-up side view of the arch, as if seen from the front-left: ascending aorta, arch with its
three branches, the isthmus with the shelf on its back wall, the ductus (or its closed cord) attached opposite the
shelf, and the descending aorta. Keep the same scale across stages.

Stages, in order:

1. `stage-narrow` [2][3][4][5]. The shelf on the back wall just beyond the left subclavian artery; a thin jet through
   the narrowing.
   Parts: `part-coarctation`, `part-left-subclavian`, `part-ductus`, `part-descending-aorta`, `part-jet`.
2. `stage-wire-across` [6][7][8]. Catheter coming up the descending aorta from below; the wire through the narrowing,
   its tip curled in the ascending aorta. A small pressure-gauge icon above and below the narrowing for "pressure
   difference measured" [7].
   Parts: `part-catheter`, `part-wire`, `part-coarctation`, `part-pressure-check`.
3. `stage-balloon-in-place` [6][7]. Empty balloon on the wire, centred in the narrowing.
   Parts: `part-balloon`, `part-coarctation`.
4. `stage-balloon-full` [6][7][8]. Balloon filled, the narrow part stretched to the balloon's width. **Balloon no wider
   than the descending aorta lower down, at the level of the diaphragm** [7][8] (draw it about the width of the
   normal descending aorta, not wider). Filled for only 10 to 15 seconds each time [7].
   Parts: `part-balloon`, `part-coarctation`.
5. `stage-after` [6][7]. Balloon gone; the segment wider; a broader stream into the descending aorta; pressures
   checked again.
   Parts: `part-widened-aorta`, `part-wider-stream`, `part-pressure-check`.
6. `stage-stent` (older child) [6][9][10]. A metal mesh tube (stent) holding the widened part open, opened by a
   balloon inside it. Draw a larger, older child's aorta proportion if possible; label that this is for older
   children.
   Parts: `part-stent`, `part-widened-aorta`.

Accuracy notes:
- The narrowing is beyond the left subclavian artery, never between the carotid and subclavian branches in this
  film [3][4][5].
- The balloon catheter goes up from below (retrograde) in the usual groin-artery route [7].
- Do not draw a bulge or tear; the film mentions them only as risks in words.

---

## Sources

1. Cincinnati Children's, Coarctation of the aorta (short piece just beyond the arteries to head and arms, where the
   ductus inserts; extra ductal tissue; PGE-1 reopens the ductus to supply the body beyond the coarctation; arch may
   be small; stents in older children cannot grow). https://www.cincinnatichildrens.org/health/c/coarctation
2. Boston Children's Hospital, Coarctation of the aorta (usually just past the aortic arch whose branches go to head
   and arms; aortic wall forms a shelf at the back; flow further constricted when the ductus closes; left ventricle
   may weaken). https://www.childrenshospital.org/conditions/coarctation-aorta
3. Saxena et al., Indian guidelines for indications and timing of intervention for common CHD, Ann Pediatr Cardiol
   2019 ("typical coarctation distal to the left subclavian artery"). https://pmc.ncbi.nlm.nih.gov/articles/PMC6716301/
4. Raza et al., Coarctation of the aorta: diagnosis and management, Diagnostics 2023, CC BY 4.0 ("discrete shelf-like
   lesion located posteriorly"; echo image of "narrowing of the thoracic aorta distal to the origin of the left
   subclavian artery"; balloon rather than stent in infants because a stent needs a larger sheath).
   https://pmc.ncbi.nlm.nih.gov/articles/PMC10340190/
5. Hysko et al., Neonatal coarctation, JACC: Advances 2023, CC BY 4.0 (coarctation defined as "a juxtaductal narrowing
   of the aortic isthmus"). https://pmc.ncbi.nlm.nih.gov/articles/PMC11198406/
6. Children's Health (Dallas), Pediatric coarctation of the aorta repair (groin puncture, wire, balloon-tipped catheter
   threaded to the aorta, balloon inflated in the narrowed part, stent in some cases).
   https://www.childrens.com/specialties-services/treatments/repair-of-coarctation-of-the-aorta
7. Arora et al., Balloon angioplasty of native coarctation in neonates and young infants, Ann Pediatr Cardiol 2022
   (femoral artery access; crossed retrogradely; wire parked in the ascending aorta; pressure gradient before and
   after; balloon 80-100% of the descending aorta at the diaphragm; 2-4 inflations of 10-15 s; one radial-artery case).
   https://pmc.ncbi.nlm.nih.gov/articles/PMC9564400/
8. Sen et al., Native aortic coarctation in neonates and infants, Ann Pediatr Cardiol 2018 (balloon must not exceed the
   descending thoracic aorta at the diaphragm; guidewire kept across the dilated segment).
   https://pmc.ncbi.nlm.nih.gov/articles/PMC6146845/
9. Cincinnati Children's (as [1]): balloon or stent in older children close to adult size.
10. Saxena et al. (as [3]): stent reasonable in children over 25 kg; planned stent not advised under 10 years.
