"""Compatibility entry point for Final19 SHAP reporting."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('generate_final19_shap_report.py')),run_name='__main__')
