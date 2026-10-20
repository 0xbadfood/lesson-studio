"""The coder's instructions for each subject kit. Kept apart from the kits, which import manim: a film worker reads
these without manim installed."""

CHEM = '''CHEMISTRY KIT (exact numbers and shapes; use it instead of computing or drawing these yourself):
from chem_kit import bohr_atom, orbiting, electron, nucleus, photon, energy_ladder, transition_arrow, line_label, \
spectrum_bar, wavelength_nm, wavelength_colour, energy_joule, radius_pm, series_name, region
- bohr_atom(levels=4, center=(x,y,0), scale=.45, law='n', electrons={1:1}) -> VGroup; .orbits[n], .radius(n),
  .center, .electrons. law='n' is not to scale (say so); law='n2' is to scale (r ~ n^2) but needs a small scale.
- orbiting(dot, center, radius, period=4): keeps a dot circling (updater); dot.clear_updaters() before a jump.
- photon(start, direction, nm, length=1.6): wave packet coloured by wavelength; m.Create it or shift it.
- energy_ladder(levels=(1..6), x0, x1, bottom, top) -> VGroup with .y(n), .lines[n]: heights proportional to E_n,
  labels n and E_n in 10^-19 J. transition_arrow(ladder, upper, lower): arrow coloured by the emitted line.
- wavelength_nm(upper, lower) (NCERT R_H = 109677 cm^-1), line_label(upper, lower) -> '656 nm',
  energy_joule(n) = -2.18e-18/n^2 J, radius_pm(n) = 52.9 n^2, series_name(lower) ('Balmer'), region(nm).
- spectrum_bar([(3,2),(4,2),...], x0, x1, y): line spectrum strip with lines at the computed wavelengths.
Every number on screen must come from these functions (format it to the precision the narration speaks).'''
