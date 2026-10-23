"""Compatibility entry point for Final19 repeated grouped validation (locked TEST excluded)."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('repeated_grouped_validation_final19.py')),run_name='__main__')
