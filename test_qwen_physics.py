"""Numerical acceptance checks against Qwen's actual generated physics helpers."""
import json
import math
from pathlib import Path
import textwrap
import unittest

import numpy as np
import qwen_generated_forces as generated


class QwenPhysicsTests(unittest.TestCase):
    def test_velocity_is_tangent_at_all_release_angles(self):
        for angle in (0,math.pi/4,math.pi/2,3*math.pi/2,2*math.pi):
            p=generated.circle_point(angle,1.3)
            v=generated.tangent_velocity(angle,1.3,2*math.pi/5)
            self.assertAlmostEqual(float(p@v),0,places=11)
        np.testing.assert_allclose(generated.tangent_velocity(3*math.pi/2,1,1),[1,0,0],atol=1e-12)
        np.testing.assert_allclose(generated.tangent_velocity(0,1,1),[0,1,0],atol=1e-12)

    def test_release_matches_orbit_velocity(self):
        h=1e-4
        for angle,radius,omega in ((3*math.pi/2,1.35,2*math.pi/5),(0,1.3,2*math.pi/5),(0,.9,1)):
            orbit_v=(generated.circle_point(angle+omega*h,radius)-generated.circle_point(angle-omega*h,radius))/(2*h)
            flight_v=(generated.free_flight(h,angle,radius,omega)-generated.free_flight(-h,angle,radius,omega))/(2*h)
            np.testing.assert_allclose(flight_v,orbit_v,rtol=1e-7,atol=1e-7)

    def test_free_flight_is_straight_and_constant_speed(self):
        for angle in (0,math.pi/4,3*math.pi/2):
            positions=np.array([generated.free_flight(t,angle,1.3,1.2) for t in (0,.25,.5,.75)])
            steps=np.diff(positions,axis=0)
            np.testing.assert_allclose(steps,np.tile(steps[0],(3,1)),atol=1e-12)

    def test_rotating_transform_preserves_distance_from_center(self):
        for t in (0,.2,.8,1.5):
            p=generated.free_flight(t,0,.9,1)
            q=generated.rotating_flight(t,0,.9,1)
            self.assertAlmostEqual(float(np.linalg.norm(p)),float(np.linalg.norm(q)),places=12)
            c,s=math.cos(t),math.sin(t)
            matrix=np.array([[c,-s,0],[s,c,0],[0,0,1]])
            np.testing.assert_allclose(matrix@q,p,atol=1e-12)

    def test_rotating_acceleration_has_centrifugal_and_coriolis_terms(self):
        h=1e-4
        for t in (.2,.8,1.5):
            pos=lambda u:generated.rotating_flight(u,0,.9,1)
            p=pos(t)
            v=(pos(t+h)-pos(t-h))/(2*h)
            a=(pos(t+h)-2*p+pos(t-h))/h**2
            np.testing.assert_allclose(a,p-2*np.cross([0,0,1],v),rtol=1e-6,atol=1e-6)

    def test_force_graph_values(self):
        self.assertEqual([generated.force_magnitude(1,v,2) for v in (2,4,6)],[2,8,18])
        self.assertEqual(generated.force_magnitude(2,4,2),16)
        self.assertEqual(generated.force_magnitude(1,4,4),4)

    def test_actual_arrow_endpoints_have_inward_radial_projection(self):
        for angle in np.linspace(-math.pi,math.pi,13):
            radial=generated.circle_point(angle,1)
            center=np.array([-3,0,0])
            start=center+radial
            arrow=generated.vec(start,start-.5*radial,'#FF727C')
            self.assertLess(float((arrow.get_end()-arrow.get_start())@radial),0)

    def test_source_is_assembled_from_qwen_responses(self):
        root=Path(__file__).resolve().parent
        store=root/'artifacts/qwen-scenes'
        responses=[]
        for name in ('scaffold','hook','circular_motion','release','force_law','frames','car','summary'):
            meta=json.loads((store/(name+'.metadata.json')).read_text())
            response=json.loads(Path(meta['response']).read_text())['code']
            normalized=response.rstrip()+'\n' if name=='scaffold' else textwrap.dedent(response).strip()+'\n'
            self.assertEqual((store/(name+'.py')).read_text(),normalized)
            responses.append(normalized)
        assembled=responses[0].rstrip()+'\n\n'+'\n\n'.join(textwrap.indent(x.rstrip(),'    ') for x in responses[1:])+'\n'
        self.assertEqual((root/'qwen_generated_forces.py').read_text(),assembled)


if __name__=='__main__': unittest.main()
