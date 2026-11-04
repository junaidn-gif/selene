import unittest
from simulation import Simulation, compare, MODES
class SimulationTests(unittest.TestCase):
    def test_accounting_bounds_and_determinism(self):
        for events in (None,[],[{'time':0,'type':'eclipse','duration':720}],[{'time':1,'type':'thermal_route_failure'},{'time':2,'type':'solar_damage'}]):
            for mode in MODES:
                a=Simulation(mode,events);b=Simulation(mode,events)
                for _ in range(720):
                    a.step();b.step()
                    self.assertGreaterEqual(a.energy,-1e-8);self.assertLessEqual(a.energy,a.c['battery_capacity_wh']+1e-8)
                    self.assertGreaterEqual(a.storage,-1e-8);self.assertLessEqual(a.storage,a.c['storage_capacity_wh']+1e-8)
                self.assertEqual(a.state(),b.state())
                self.assertLess(a.metrics['max_electrical_residual_wh'],1e-7)
                self.assertLess(a.metrics['max_thermal_residual_wh'],1e-7)
    def test_controller_outcomes(self):
        r=compare();b=r['baseline']['metrics'];l=r['lunagrid']['metrics'];s=r['full']['metrics']
        self.assertEqual(s['critical_availability'],100)
        self.assertEqual(s['flexible_tasks_completed'],2)
        self.assertGreater(l['minimum_soc'],b['minimum_soc'])
        self.assertLess(s['electric_heater_wh'],b['electric_heater_wh'])
        self.assertGreater(s['recovered_heat_wh'],0)
    def test_forecast_route_failure_and_storage(self):
        s=Simulation();stored=False;deferred=False;resumed=False
        for _ in range(720):
            x=s.step()
            stored|=any(r['target']=='Thermal storage' for r in x['heat_routes'])
            for l in x['loads']:
                if l['id']=='rover':
                    deferred|=l['status']=='Postponed'
                    resumed|=deferred and l['status']=='Active'
            if x['time_min']>420:
                self.assertFalse(any(r['source']=='Computer / science' and r['target']=='Battery' for r in x['heat_routes']))
        self.assertTrue(stored);self.assertTrue(deferred);self.assertTrue(resumed)
    def test_manual_fault_and_completion(self):
        s=Simulation(events=[]);s.inject('eclipse');s.step();self.assertEqual(s.live['solar_w'],0)
        for _ in range(720):s.step()
        self.assertEqual(s.time,720)
        with self.assertRaises(ValueError):s.inject('unknown')
if __name__=='__main__':unittest.main()
