import unittest
import torch
from docurecon_v122d_train_crnn import DateCRNN, decode_greedy, encode, ALPHABET

class TestTrainingCode(unittest.TestCase):
    def test_encode(self):
        self.assertEqual(len(encode('05.07.2020')),10)
    def test_bad_char(self):
        with self.assertRaises(ValueError): encode('NOV 2026')
    def test_network_shape(self):
        with torch.no_grad():
            x=DateCRNN()(torch.zeros(1,1,48,320))
        self.assertEqual(tuple(x.shape),(80,1,len(ALPHABET)+1))
    def test_decode_ctc(self):
        seq=[1,1,0,2,2,0,3]
        z=torch.full((len(seq),1,len(ALPHABET)+1),-10.)
        for i,c in enumerate(seq): z[i,0,c]=10.
        self.assertEqual(decode_greedy(z),['012'])

if __name__=='__main__': unittest.main()
