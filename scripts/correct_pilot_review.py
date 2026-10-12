"""Record the observed pilot label defect and resume Qwen's correction loop."""
import json
from pathlib import Path
import sqlite3
import time

ROOT=Path(__file__).resolve().parents[1]
JOB='f809a309194c4736967cd1513eca10ce'
directory=ROOT/'api-data/runs'/JOB
scene=directory/'scenes/s02'
feedback=('Content review correction: the white axes are drawn with vectors @ rot, '
          'where rot=[[cos(a),-sin(a)],[sin(a),cos(a)]]. With row vectors this '
          'rotates the drawn axes by -a, the same as the inertial background tick. '
          'They are inertial reference axes as seen by the rotating camera, not '
          'the rotating frame own axes. The stationary ball/string and opposed '
          'equal-length force arrows are already correct. Correct only the '
          'white axes label: replace its wording "rotating frame axes" with '
          '"inertial reference axes". Keep all other physics, geometry, label '
          'positions and timing unchanged. Return the full complete module.')

if (scene/'accepted.json').exists():
    (scene/'pre-correction-accepted.json').write_bytes((scene/'accepted.json').read_bytes())
    (scene/'accepted.json').unlink()
(directory/'pre-correction-report.json').write_bytes((directory/'report.json').read_bytes())
(scene/'feedback.txt').write_text(feedback)
(directory/'manual-content-review.json').write_text(json.dumps(
    {'scene':'s02','reason':feedback,'reviewer':'Codex content spot check','time':time.time()},indent=2)+'\n')
with sqlite3.connect(ROOT/'api-data/jobs.sqlite3') as db:
    db.execute("UPDATE jobs SET status='failed',error=?,updated=? WHERE id=? AND status='succeeded'",
               ('Pilot label correction requested by content review',time.time(),JOB))
print('Saved the label correction for Qwen; generated scene source was not edited.')
