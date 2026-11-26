import csv
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).parent))
from docurecon_v122c_make_manifest import make_partitions, ROLE_BY_SET_CLASS

class TestDevelopmentPartitions(unittest.TestCase):
    def test_expected_roles(self):
        self.assertEqual(ROLE_BY_SET_CLASS['S1','CLEAN_RECOGNITION_CANDIDATE'],'TRAIN')
        self.assertEqual(ROLE_BY_SET_CLASS['S4','DEVELOPMENT_HOLDOUT_CANDIDATE'],'DEV_EVAL_NOT_INDEPENDENT')
        self.assertEqual(ROLE_BY_SET_CLASS['S2','OVERSIZE_CHALLENGE'],'CHALLENGE_OVERSIZE')
    def test_role_mapping_complete(self):
        self.assertEqual(len(ROLE_BY_SET_CLASS),13)
    def test_rejects_missing_rows(self):
        with self.assertRaises(ValueError):make_partitions([],Path('.'),False)
    def test_rejects_duplicates(self):
        with self.assertRaises(ValueError):make_partitions([{'sample_key':'D1'}]*8000,Path('.'),False)
    def test_rejects_invalid_paths(self):
        rows=[{'sample_key':f'S1_D{i:04}', 'dataset':'S1', 'label_class':'CLEAN_RECOGNITION_CANDIDATE','image':'../escape.png','label_text_exact':'01/02/2026'} for i in range(8000)]
        with self.assertRaises(ValueError):make_partitions(rows,Path('.'),False)
    def test_rejects_unrecognized_class(self):
        rows=[{'sample_key':f'S1_D{i:04}', 'dataset':'S1', 'label_class':'UNKNOWN','image':f'images/S1/{i}.png','label_text_exact':'01/02/2026'} for i in range(8000)]
        with self.assertRaises(ValueError):make_partitions(rows,Path('.'),False)
    def test_rejects_missing_training_label(self):
        rows=[{'sample_key':f'S1_D{i:04}', 'dataset':'S1', 'label_class':'CLEAN_RECOGNITION_CANDIDATE','image':f'images/S1/{i}.png','label_text_exact':''} for i in range(8000)]
        with self.assertRaises(ValueError):make_partitions(rows,Path('.'),False)

if __name__ == '__main__':unittest.main()
