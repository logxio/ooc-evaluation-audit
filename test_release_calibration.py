"""Check evidence separation, deploy invariance and finite-sample risk behavior."""
import copy
import itertools
import unittest
from release_calibration import fit, calibrate, apply, measure


class CalibrationTests(unittest.TestCase):
    def setUp(self):
        self.training = [{'patient':str(i),'x':[float(i),float(i)],'y':int(i<3)} for i in range(6)]
        self.model = fit(self.training)

    def test_calibration_labels_never_refit_model(self):
        cal=[dict(r,patient='c'+r['patient']) for r in self.training]
        before=copy.deepcopy(self.model)
        a=calibrate(self.model,cal,.2)
        b=calibrate(self.model,[dict(r,y=1-r['y']) for r in cal],.2)
        self.assertEqual(a['model'],before)
        self.assertEqual(b['model'],before)
        future=[{'patient':'new','x':[0.,0.]}]
        self.assertEqual(apply(a,future)[0]['calls'], apply(b,future)[0]['calls'])

    def test_new_labels_and_batch_do_not_change_calls(self):
        c=calibrate(self.model,[dict(r,patient='c'+r['patient']) for r in self.training],.2)
        p={'patient':'new','x':[1.,1.]}
        expected=apply(c,[p])[0]
        self.assertEqual(expected,apply(c,[dict(p,y=1)])[0])
        self.assertEqual(expected,apply(c,[p,{'patient':'extreme','x':[1e20,-1e20]}])[0])

    def test_small_sample_fallback_rejects_entire_domain(self):
        c=calibrate(self.model,[{'patient':'c','x':[0.,0.],'y':1}],.1)
        future=[{'patient':str(i),'x':[x,y]} for i,(x,y) in enumerate(itertools.product([-1e20,0.,2.5,5.,1e20],repeat=2))]
        self.assertEqual(c['fallback'],'all_retest')
        self.assertFalse(any(r['released'] for r in apply(c,future)))

    def test_reuse_and_tampering_are_rejected(self):
        with self.assertRaises(ValueError): calibrate(self.model,self.training,.1)
        model=copy.deepcopy(self.model); model['cutoffs'][0]+=1
        with self.assertRaises(ValueError): calibrate(model,[{'patient':'c','x':[0.,0.],'y':0}],.2)

    def test_expected_risk_by_exhaustive_iid_calibrations(self):
        # Enumerate 4^3 equally likely calibration samples, then all four future
        # cases. This tests the expectation over calibration and a fresh patient.
        population=[{'x':[0.,0.],'y':1},{'x':[1.,1.],'y':0},
                    {'x':[4.,4.],'y':1},{'x':[5.,5.],'y':0}]
        risks=[]
        for draw in itertools.product(range(4),repeat=3):
            cal=[dict(population[j],patient='c'+str(i)) for i,j in enumerate(draw)]
            c=calibrate(self.model,cal,.5)
            future=[dict(r,patient='n'+str(i)) for i,r in enumerate(population)]
            risks.append(measure(c,future)['overall_wrong_release'])
        self.assertLessEqual(sum(risks)/len(risks),.5)


if __name__=='__main__': unittest.main()
