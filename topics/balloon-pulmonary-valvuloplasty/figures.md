# Figures: Opening a narrow heart valve to the lungs with a balloon (topic-balloon-pulmonary-valvuloplasty)

Painted later (painted base plus vector overlays, as for `pda-heart-front`). Audience: parents, figure level Class 10
(plain labels, Latin name in brackets at most). Each stage below is one picture state; the parts listed under a
stage are the ones the narration names and lights. Part ids follow the house pattern (`part-<thing>`); a stage's
parts become `part-<stage>-<thing>` in the sidecar, with a `part_map` back to these names.

Sources are cited as [n] and listed at the end.

---

## 1. `heart-chambers`: the heart from the front, cut open, showing the path of blood

A child's heart, front view, cut open so all four chambers show: right atrium and right ventricle on the viewer's
left, left atrium and left ventricle on the viewer's right. Pulmonary artery leaving the top of the right ventricle
and dividing into left and right branches to the lungs; aorta leaving the left ventricle and arching over. Blue
(oxygen-poor) and red (oxygen-rich) flow arrows. Keep the pulmonary valve visible at the exit of the right
ventricle; it is the part the whole film is about.

Stages, in order:

1. `stage-normal-flow`: the normal path [1]. Blue blood comes back from the body into the right atrium, goes down into
   the right ventricle, is pumped up through the pulmonary valve into the pulmonary artery to the lungs; red blood
   returns to the left atrium, goes into the left ventricle and out through the aortic valve into the aorta. The
   valves at the ventricle exits open forward only.
   Parts: `part-right-atrium`, `part-right-ventricle`, `part-pulmonary-valve`, `part-pulmonary-artery`,
   `part-left-atrium`, `part-left-ventricle`, `part-aorta`, `part-flow-to-lungs`, `part-flow-to-body`.
2. `stage-narrow-valve`: pulmonary stenosis [2][3][4][5]. The pulmonary valve has a small opening; a thin, fast jet of
   blood squirts through it into the pulmonary artery. The right ventricle wall is visibly thicker than in stage 1
   (the muscle thickens from working harder [2]). The main pulmonary artery just beyond the valve is widened
   (post-stenotic dilatation of the main and left pulmonary artery [4]; draw it gently, not as an aneurysm).
   Parts: `part-pulmonary-valve`, `part-right-ventricle-wall`, `part-jet`, `part-pulmonary-artery`.
3. `stage-newborn-critical`: a newborn with critical stenosis [6]. Right ventricle thick-walled with a smaller
   cavity; a blue arrow crossing from the right atrium to the left atrium through the small opening between the upper
   chambers (foramen ovale); the ductus arteriosus open between the pulmonary artery and the aorta, with flow from the
   aorta into the pulmonary artery towards the lungs (the baby's lungs depend on it). Skin-tone cue not needed here.
   Parts: `part-right-ventricle-wall`, `part-foramen-ovale`, `part-right-to-left-flow`, `part-ductus`,
   `part-pulmonary-valve`.

Accuracy notes for the illustrator:
- A normal pulmonary valve has three thin leaflets [3]; in stenosis two may be stuck together or too thick, or there
  may be fewer than three [3].
- Only the valve is narrowed in this film (valvar stenosis); do not narrow the muscle below the valve or the artery
  above it in stages 1 and 2.

## 2. `catheter-entry`: where the thin tube goes in (shared with topic-balloon-coarctoplasty)

A small child lying on their back, outline style, with the heart and the main vessels drawn faintly inside. The same
figure id is used by the coarctation film, so it needs all the stages below (the BPV film uses stages 1 and 2; the
coarctation film uses 3 and optionally 4).

Stages, in order:

1. `stage-groin-vein`: BPV, the usual route [7][8]. Entry point at the right (or left) groin, into the femoral vein [8].
   The catheter runs up the large vein in the belly (inferior vena cava) into the right atrium, turns down into the
   right ventricle, then turns up through the pulmonary valve into the pulmonary artery, its tip in a branch of the
   lung artery [8]. Two bends: vein-to-ventricle and ventricle-to-lung-artery [7].
   Parts: `part-entry-groin`, `part-femoral-vein`, `part-catheter`, `part-heart`, `part-pulmonary-valve`.
2. `stage-neck-vein`: BPV alternative in some newborns [7]. Entry at the right side of the neck into the internal
   jugular vein; the catheter runs straight down the upper large vein (superior vena cava) into the right atrium and
   right ventricle, then one turn up through the pulmonary valve. Visibly straighter than stage 1.
   Parts: `part-entry-neck`, `part-jugular-vein`, `part-catheter`, `part-heart`.
3. `stage-groin-artery`: coarctation route (see the coarctation figures.md): femoral artery in the groin, catheter up
   the aorta against the blood flow to the narrow part beyond the arch.
4. `stage-wrist-artery` (optional): coarctation, rare route used once in the New Delhi series (radial artery).

Accuracy notes: the BPV catheter is in a vein and travels with the blood flow to the right heart; do not show it in
an artery or crossing into the left heart. The child is asleep under general anaesthesia [7][8]; a sleeping face is
fine.

## 3. `pulmonary-valve-balloon`: close-up of the valve being opened

Close-up, long-axis section: the top of the right ventricle (its outflow) below, the pulmonary valve in the middle,
the main pulmonary artery above dividing into its two branches. Viewer sees the valve leaflets from the side. Keep
the same scale across stages so the balloon's waist reads clearly.

Stages, in order:

1. `stage-narrow-valve` [3][5][8][9][10]. The typical narrow valve is thickened and dome-shaped: the leaflets are
   thick and stuck together along their edges [3], so when the ventricle pumps they bulge up into the artery as a
   dome [8][10] with a small opening at its top (an illustrator's reading of the dome; the sources show the dome and
   the narrow jet, not the opening's exact size). A thin, fast jet leaves the top of the dome. Thick right
   ventricle wall; the artery beyond the valve slightly widened [4].
   Parts: `part-pulmonary-valve`, `part-jet`, `part-right-ventricle-wall`, `part-pulmonary-artery`.
2. `stage-wire-across` [8]. A thin catheter comes up from the right ventricle through the valve opening; its guide
   wire runs on into one branch of the lung artery (left or right), where its tip is parked.
   Parts: `part-pulmonary-valve`, `part-catheter`, `part-wire`.
3. `stage-balloon-in-place` [8]. A folded (empty) balloon on the wire, its middle exactly at the valve.
   Parts: `part-balloon`, `part-pulmonary-valve`, `part-wire`.
4. `stage-balloon-waist` [8]. Balloon partly filled: both ends round, the middle pinched in by the tight valve (a
   waist, like an hourglass).
   Parts: `part-balloon`, `part-balloon-waist`, `part-pulmonary-valve`.
5. `stage-balloon-full` [8][9]. Balloon fully filled, the waist gone, the valve stretched open around it. Balloon
   diameter a little larger than the valve ring (about 1.1 to 1.25 times the ring width [8][9]; draw it just
   noticeably wider than the ring, never dramatically wider). The narration says it is filled for a few seconds [8].
   Parts: `part-balloon`, `part-pulmonary-valve`.
6. `stage-valve-after` [9][11]. Balloon gone. The leaflets now open wider with less doming, and a broader stream of
   blood flows up into the artery [9]. Optional faint backward arrow below the valve for the leak the film mentions
   later (pulmonary regurgitation [9][11]); keep it small.
   Parts: `part-pulmonary-valve`, `part-wider-stream`, `part-leak`.

Accuracy notes:
- The dysplastic valve (thick, immobile leaflets, no dome) is a less common type [10][4]; do not draw it here.
- The balloon sits across the valve, not in the ventricle or the artery alone [8].

---

## Sources

1. NCERT Class 11 Biology, Chapter 15 Body Fluids and Circulation (chambers, valves, pulmonary and systemic
   circulation). https://ncert.nic.in/textbook/pdf/kebo115.pdf
2. Great Ormond Street Hospital, Pulmonary stenosis (narrow valve between right ventricle and pulmonary artery; right
   ventricle muscle thickens). https://www.gosh.nhs.uk/conditions-and-treatments/conditions-we-treat/pulmonary-stenosis/
3. CHOP, Pulmonary stenosis (three leaflets; leaflets stuck together, too thick, or fewer than three).
   https://www.chop.edu/conditions-diseases/pulmonary-stenosis
4. Saxena et al., Indian guidelines for indications and timing of intervention for common CHD, Ann Pediatr Cardiol
   2019 (post-stenotic dilatation of main and left pulmonary artery; dysplastic valves may not show it).
   https://pmc.ncbi.nlm.nih.gov/articles/PMC6716301/
5. Boston Children's Hospital, Pulmonary valve stenosis (right ventricle must work harder to push blood through the
   narrow opening). https://www.childrenshospital.org/conditions/pulmonary-valve-stenosis
6. Aggarwal et al., BPV in neonatal critical pulmonary stenosis, Ann Pediatr Cardiol 2025 (muscle-bound right
   ventricle, right-to-left atrial shunt, duct-dependent lung flow). https://pmc.ncbi.nlm.nih.gov/articles/PMC12063987/
7. Hoetama et al., BPV in neonates: jugular or femoral, Ann Pediatr Cardiol 2020 (femoral vein most common; jugular
   route straighter: one curve instead of two; general anaesthesia). https://pmc.ncbi.nlm.nih.gov/articles/PMC6979020/
8. Behjati-Ardakani et al., Long-term results of BPV in children, Iran J Pediatr 2013 (femoral vein; thickened domed
   valve with post-stenotic dilatation on angiogram; catheter tip in a distal branch pulmonary artery; balloon 10-20%
   larger than the annulus; middle of balloon across the valve; fully inflated within a few seconds; waist appears and
   disappears). https://pmc.ncbi.nlm.nih.gov/articles/PMC3574989/
9. Rao PS, Balloon pulmonary valvuloplasty: a systematic review, Indian Heart J 2024 (leaflets move more freely with
   less doming after BPV; balloon/annulus ratio 1.2-1.25 recommended; late pulmonary insufficiency).
   https://pmc.ncbi.nlm.nih.gov/articles/PMC11143516/
10. Nasir et al. (Cardiac Center of Ethiopia), Percutaneous BPV in children: 10-year follow-up, BMC Cardiovasc Disord
    2025 (most valves domed; dysplastic valve = significant leaflet thickness and immobility).
    https://pmc.ncbi.nlm.nih.gov/articles/PMC12105224/
    Supporting image description of systolic doming: Percutaneous balloon dilation of the pulmonary valve in a
    79-year-old, CASE (Cardiovascular Imaging Case Reports) 2024, Schwartz et al. ("thickened leaflets that dome in systole").
    https://pmc.ncbi.nlm.nih.gov/articles/PMC10954575/
11. Children's Health (Dallas), Pediatric balloon valvuloplasty (valve leakage is a risk).
    https://www.childrens.com/specialties-services/treatments/balloon-valvuloplasty
