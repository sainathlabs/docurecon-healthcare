import unittest
import numpy as np
from docurecon_v122g_compare_beam import prefix_beam_search, metrics, logsum
from docurecon_v122d_train_crnn import ALPHABET


def probabilities(*frames):
    """Generate valid log probabilities from weighted per-step character choices."""
    items=[]
    for choices in frames:
        arr=np.full(len(ALPHABET)+1, 1e-7, dtype=np.float64)
        for char, weight in choices.items():
            idx=0 if char=='_' else ALPHABET.index(char)+1
            arr[idx]=weight
        arr/=arr.sum()
        items.append(np.log(arr))
    return np.stack(items)


class TestBeam(unittest.TestCase):
    def test_blank_only(self):
        self.assertEqual(prefix_beam_search(probabilities({'_':0.99},{'_':0.99})), '')

    def test_single_character(self):
        self.assertEqual(prefix_beam_search(probabilities({'5':0.9},{'_':0.9})), '5')

    def test_repeat_without_blank_collapses(self):
        self.assertEqual(prefix_beam_search(probabilities({'2':0.99},{'2':0.99})), '2')

    def test_repeat_with_blank_kept(self):
        self.assertEqual(prefix_beam_search(probabilities({'2':0.99},{'_':0.99},{'2':0.99})), '22')

    def test_bad_shape(self):
        with self.assertRaises(ValueError): prefix_beam_search(np.zeros((8,3)))

    def test_metrics(self):
        r=[{'truth':'2020','beam':'2020'},{'truth':'2019','beam':'20'}]
        result=metrics(r,'beam')
        self.assertEqual(result['exact'],1)
        self.assertAlmostEqual(result['cer'],2/8)

    def test_logsum(self):
        self.assertAlmostEqual(logsum(float('-inf'),-2.0),-2.0)


if __name__ == '__main__':
    unittest.main()
