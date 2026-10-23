"""Compatibility entry point for the original project filename.
FinalScientific v4.6.3 / Scientific1900 uses train_final19_supervised.py.
"""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('train_final19_supervised.py')),run_name='__main__')
