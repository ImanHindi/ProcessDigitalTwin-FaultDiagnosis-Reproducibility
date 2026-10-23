"""Check evidence consistency, not a fresh physical simulation or model retraining."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_results import validate
class ArchivedResultTest(unittest.TestCase):
 def test_final19_metrics(self):
  v=validate()
  self.assertEqual(v['runs'],1900)
  self.assertEqual(v['test_supervised_windows'],10596)
  self.assertAlmostEqual(v['supervised']['probability_ensemble']['accuracy'],0.888637221593054,places=8)
  self.assertAlmostEqual(v['anomaly']['lstm_ae']['balanced_accuracy'],0.707885,places=5)
