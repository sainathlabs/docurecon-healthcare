import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from docurecon_v122j_confidence_audit import parse_calendar_day_first, summarise, selective_review

class TestConfidenceAudit(unittest.TestCase):
    def test_calendar_valid(self): self.assertEqual(parse_calendar_day_first('28.07.2026'),'2026-07-28')
    def test_day_first_assumption(self): self.assertEqual(parse_calendar_day_first('7/1/2024'),'2024-01-07')
    def test_calendar_invalid(self): self.assertIsNone(parse_calendar_day_first('31/11/2021'))
    def test_invalid_format(self): self.assertIsNone(parse_calendar_day_first('22-11'))
    def test_same_calendar_different_separator(self): self.assertEqual(parse_calendar_day_first('10.9.24'),parse_calendar_day_first('10.9-24'))
    def test_summary_and_selectivity(self):
        rows=[{'exact':1,'truth_calendar':'2024-01-01','prediction_calendar':'2024-01-01','disagreement':0,'mean_top_probability':.99},
              {'exact':0,'truth_calendar':'2024-01-01','prediction_calendar':'2024-01-02','disagreement':0,'mean_top_probability':.98},
              {'exact':0,'truth_calendar':'2024-01-01','prediction_calendar':'2024-01-01','disagreement':1,'mean_top_probability':.99}]
        s=summarise(rows)
        self.assertEqual(s['wrong_calendar_date'],1)
        self.assertEqual(s['transcription_wrong_but_calendar_same'],1)
        self.assertEqual(s['incorrect'],2)
        q=selective_review(rows,[.95])[0]
        self.assertEqual(q['accepted'],2)
        self.assertEqual(q['wrong_transcriptions_accepted'],1)

if __name__=='__main__':unittest.main()
