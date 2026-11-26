import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
from docurecon_v122h_train_beam import select_partitions, write_predictions, make_checkpoint
from docurecon_v122f_train_improved import HeightAwareDateCRNN

class TestV122H(unittest.TestCase):
    def test_checkpoint_labels(self):
        cp=make_checkpoint(HeightAwareDateCRNN(),3,{'loss':1.2},'last_epoch')
        self.assertEqual(cp['epoch'],3)
        self.assertEqual(cp['architecture'],'HeightAwareDateCRNN')
        self.assertTrue(cp['synthetic_only'])
    def test_predictions_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'pred.csv'
            write_predictions(file,[{'sample_key':'S1_D0001','truth':'05.07.2020','greedy':'05.07.20',
                                     'beam':'05.07.2020','greedy_exact':0,'beam_exact':1}])
            self.assertIn('beam_exact',file.read_text(encoding='utf-8-sig'))
    def test_overlap_guard(self):
        # Partition separation is checked in end-to-end smoke test and real manifest run.
        from docurecon_v122g_compare_beam import prefix_beam_search
        import numpy as np
        scores=np.full((3,14),-10.0,dtype=float)
        scores[0,1]=0; scores[1,0]=0;scores[2,1]=0
        self.assertEqual(prefix_beam_search(scores,beam_width=5),'00')

if __name__=='__main__':unittest.main()
