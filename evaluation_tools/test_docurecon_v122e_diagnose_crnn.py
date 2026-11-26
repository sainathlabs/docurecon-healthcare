import sys
import unittest
from pathlib import Path
import torch
sys.path.insert(0,str(Path(__file__).parent))
from docurecon_v122e_diagnose_crnn import edit_distance, evaluate
from docurecon_v122d_train_crnn import DateCRNN, decode_greedy

class TestDiagnostics(unittest.TestCase):
    def test_edit_distance(self):
        self.assertEqual(edit_distance('05.07.2020','05.07.2020'),0)
        self.assertEqual(edit_distance('05.07.2020','05.07.202'),1)
        self.assertEqual(edit_distance('','123'),3)
    def test_empty_prediction_cer(self):
        self.assertEqual(edit_distance('12/4/2020','')/len('12/4/2020'),1)
    def test_unchanged_network_output(self):
        with torch.no_grad():
            m=DateCRNN();out=m(torch.rand(1,1,48,320))
        self.assertEqual(out.shape[0],80)
        self.assertEqual(len(decode_greedy(out)),1)
    def test_ctc_repeat_minimum(self):
        label='11/11/2022'
        min_steps=len(label)+sum(label[i]==label[i-1] for i in range(1,len(label)))
        self.assertEqual(min_steps,13)

if __name__=='__main__':unittest.main()
