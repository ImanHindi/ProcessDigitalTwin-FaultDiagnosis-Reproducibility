"""Compatibility entry point for Final19 anomaly operating-point sensitivity."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('enhance_anomaly_operating_points_final19.py')),run_name='__main__')
