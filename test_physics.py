"""Check the equations that drive release, rotating frames, and car contact."""
import unittest
import numpy as np

from centripetal_centrifugal import point, rotation, arrow, FORCE


class PhysicsTests(unittest.TestCase):
    def test_velocity_is_tangent(self):
        for theta in np.linspace(-np.pi,np.pi,17):
            self.assertAlmostEqual(float(point(theta) @ point(theta+np.pi/2)),0,places=12)
            # Δv for symmetric nearby angular samples is radially inward.
            delta=point(theta+0.32+np.pi/2,1.15)-point(theta-0.32+np.pi/2,1.15)
            np.testing.assert_allclose(delta,-2*1.15*np.sin(0.32)*point(theta,1),atol=1e-12)

    def test_release_keeps_velocity_and_has_no_acceleration(self):
        cases = [(2*np.pi/6,1.45,np.pi/4,None),
                 (2*np.pi/5,1.7,2*np.pi-np.pi/2,np.array([1,0,0])),
                 (1,1.05,2*np.pi,np.array([0,1,0]))]
        for omega,radius,theta,direction in cases:
            p0 = point(theta,radius)
            v0 = point(theta+np.pi/2,omega*radius) if direction is None else direction*omega*radius
            h = 0.0001
            derivative = (point(theta+omega*h,radius)-point(theta-omega*h,radius))/(2*h)
            np.testing.assert_allclose(derivative,v0,rtol=1e-7,atol=1e-7)
            position = lambda t:p0+t*v0
            np.testing.assert_allclose(position(2)-2*position(1)+position(0),np.zeros(3),atol=1e-12)

    def test_rotating_release_requires_both_pseudo_forces(self):
        # a_rel = centrifugal + Coriolis when the real horizontal force is zero.
        r,omega,h = 1.05,1.0,1e-4
        position = lambda t:rotation(-omega*t,np.array([r,r*omega*t,0]))
        for t in (0.2,0.8,1.8):
            p = position(t)
            v = (position(t+h)-position(t-h))/(2*h)
            a = (position(t+h)-2*p+position(t-h))/(h*h)
            expected = omega**2*p-2*np.cross([0,0,omega],v)
            np.testing.assert_allclose(a,expected,rtol=1e-6,atol=1e-6)

    def test_force_graph_values(self):
        self.assertEqual([v*v/2 for v in (2,4,6)],[2,8,18])

    def test_drawn_force_arrow_points_inward(self):
        for theta in np.linspace(-np.pi,np.pi,13):
            center=np.array([-3.7,0.15,0])
            radial=point(theta,0.7)
            for speed in (2,4,6):
                p=center+radial
                force=arrow(p,p-point(theta,0.055*speed**2/2),FORCE)
                self.assertLess(np.dot(force.get_end()-force.get_start(),radial),0)

    def test_drawn_car_contact_arrow_points_toward_turn_center(self):
        center=np.array([-3.4,0.7,0])
        for theta in np.linspace(-np.pi/2+0.5,0,8):
            car=center+point(theta,1.8)
            force=arrow(car,car-point(theta,0.9),FORCE)
            self.assertLess(np.dot(force.get_end()-force.get_start(),car-center),0)

    def test_passenger_contacts_right_side_inside_car(self):
        r,theta=1.8,0.5
        p0=point(-np.pi/2,r)
        passenger=p0+np.array([r*theta,0,0])
        car=point(-np.pi/2+theta,r)
        local=rotation(-theta,passenger-car)
        self.assertLess(local[1],0)  # Right side of a car facing +x is -y.
        self.assertLess(abs(local[1])+0.085,0.3)
        self.assertLess(abs(local[0])+0.085,0.475)


if __name__=="__main__": unittest.main()
