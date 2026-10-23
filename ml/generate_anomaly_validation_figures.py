"""Compatibility entry point. Final19 publication generator includes anomaly benchmark figures."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('generate_final19_publication_figures.py')),run_name='__main__')
