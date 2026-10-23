"""Compatibility entry point for Final19 figure verification."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('verify_final19_publication_figures.py')),run_name='__main__')
