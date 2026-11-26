import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).with_name('docurecon_v122b_audit_labels.py')
spec = importlib.util.spec_from_file_location('v122b_audit', PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TestDateLabelAudit(unittest.TestCase):
    def test_valid_day_first(self):
        self.assertEqual(mod.calendar_check('29-02-2024'),'VALID_DAY_FIRST_DATE')
    def test_invalid_date(self):
        self.assertEqual(mod.calendar_check('31/11/2021'),'IMPOSSIBLE_CALENDAR_DATE')
    def test_reject_nonsensical(self):
        self.assertEqual(mod.calendar_check('03/2025'),'NOT_A_COMPLETE_DATE')
    def test_blank(self):
        self.assertEqual(mod.class_for({'dataset':'S3','label_text_exact':'','category':'blank'},{'category':'blank','is_blank':'1'})[0], 'BLANK_FIELD')
    def test_corrected_not_clean(self):
        self.assertEqual(mod.class_for({'dataset':'S3','label_text_exact':'14.05.2024','category':'corrected'},{'category':'corrected','is_complete':'1'})[0], 'CORRECTION_CHALLENGE')
    def test_s2_is_not_train(self):
        self.assertEqual(mod.class_for({'dataset':'S2','label_text_exact':'14.05.2024','category':'large_overlap_challenge'}, {})[0], 'OVERSIZE_CHALLENGE')
    def test_s4_holdout(self):
        self.assertEqual(mod.class_for({'dataset':'S4','label_text_exact':'14.05.2024','category':'normal'}, {'category':'normal'})[0], 'DEVELOPMENT_HOLDOUT_CANDIDATE')
    def test_blank_mismatch_flagged(self):
        self.assertIn('SOURCE_BLANK_FLAG_MISMATCH',mod.class_for({'dataset':'S3','label_text_exact':'','category':'blank'},{'category':'blank','is_blank':'0'})[2])

if __name__=='__main__': unittest.main()
