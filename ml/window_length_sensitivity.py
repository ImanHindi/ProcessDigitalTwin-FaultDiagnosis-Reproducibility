"""Compatibility entry point for validation-only Final19 window sensitivity."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('window_length_sensitivity_final19.py')),run_name='__main__')
