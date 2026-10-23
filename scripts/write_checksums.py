#!/usr/bin/env python3
"""Generate SHA256SUMS.txt for distributable files."""
import argparse,hashlib
from pathlib import Path
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('root',nargs='?',default=str(Path(__file__).resolve().parents[1]));r=Path(a.parse_args().root).resolve();out=r/'SHA256SUMS.txt'
 with out.open('w',encoding='utf-8') as dest:
  for p in sorted(r.rglob('*')):
   if not p.is_file() or p==out or set(p.parts)&{'.git','__pycache__','.venv'} or p.suffix=='.pyc':continue
   h=hashlib.sha256()
   with p.open('rb') as f:
    for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
   dest.write(f'{h.hexdigest()}  {p.relative_to(r).as_posix()}\n')
 print('SHA256 manifest written:',out)
