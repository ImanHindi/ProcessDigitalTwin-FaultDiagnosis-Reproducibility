"""Compatibility entry point for the original anomaly benchmark filename.
Runs the Final19 Isolation-Forest baselines followed by the healthy-only deep benchmark.
"""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--n-jobs',type=int,default=2);p.add_argument('--epochs',type=int,default=60);p.add_argument('--patience',type=int,default=9);p.add_argument('--bootstrap',type=int,default=1000);a=p.parse_args();here=Path(__file__).resolve().parent
commands=[
 [sys.executable,str(here/'train_final19_anomaly_baselines.py'),'--n-jobs',str(a.n_jobs)],
 [sys.executable,str(here/'train_final19_deep_anomaly.py'),'--n-jobs',str(a.n_jobs),'--epochs',str(a.epochs),'--patience',str(a.patience),'--bootstrap',str(a.bootstrap)],
]
for cmd in commands:
 print('\nRUNNING:',' '.join(cmd),flush=True);subprocess.run(cmd,check=True)
