"""Compatibility entry point. Final19 baseline script trains global and mode-conditioned IF together."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('train_final19_anomaly_baselines.py')),run_name='__main__')
