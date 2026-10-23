"""Compatibility entry point for Scientific1900/locked-split readiness."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('check_final19_training_readiness.py')),run_name='__main__')
