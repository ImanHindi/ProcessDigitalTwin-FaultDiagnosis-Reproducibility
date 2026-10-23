#!/usr/bin/env python3
"""Check retained Final19 files against the exact uploaded retraining package."""
from __future__ import annotations
import hashlib, json, argparse
from pathlib import Path

def verify(root):
 m=json.loads((root/'docs'/'FINAL19_SOURCE_AUDIT.json').read_text(encoding='utf8'))
 failed=[]
 for item in m['core_files']:
  path=root/item['path']
  if not path.is_file():failed.append({'path':item['path'],'error':'missing'});continue
  digest=hashlib.sha256(path.read_bytes()).hexdigest()
  if digest!=item['sha256']:failed.append({'path':item['path'],'error':'changed'})
 return {'checked':len(m['core_files']),'mismatches':failed,'result':'PASS' if not failed else 'FAIL'}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root',nargs='?',type=Path,default=Path(__file__).resolve().parents[1]);a=p.parse_args()
 r=verify(a.root.resolve());print(json.dumps(r,indent=2));raise SystemExit(0 if r['result']=='PASS' else 2)
