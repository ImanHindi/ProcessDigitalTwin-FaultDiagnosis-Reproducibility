#!/usr/bin/env python3
"""Conservative non-exhaustive pre-publication privacy and large-file scanner."""
from __future__ import annotations
import re, json, argparse, zipfile
from pathlib import Path

PATTERNS={
 'personal_windows_path':re.compile(rb'(?i)[A-Z]:[\\/]+Users[\\/]+(?!Public[\\/])[^\\/\s"\x00]+'),
 'personal_unix_path':re.compile(rb'(?i)/(?:Users|home)/[A-Za-z0-9_.-]+/'),
 'email':re.compile(rb'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
 'github_token':re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),
 'api_token':re.compile(rb'sk-[A-Za-z0-9_-]{20,}'),
 'secret_assignment':re.compile(rb'(?i)\b(?:password|secret_key|api_key|access_token)\s*[:=]\s*["\x27][^"\x27\s]{8,}["\x27]'),
}
TEXT_EXT={'.py','.m','.txt','.md','.yml','.yaml','.json','.toml','.ini','.cfg','.csv','.js','.ts','.html','.css','.xml','.cff','.bat','.sh'}
NO_PUBLIC_EXT={'.rar','.7z','.zip','.exe','.dll','.mp4','.mov','.avi','.pkl','.joblib','.pth','.pt','.ckpt','.safetensors','.onnx','.h5','.hdf5','.sqlite','.mat'}
SKIP_PARTS={'.git','__pycache__','.venv','.pytest_cache'}

def sensitive(data:bytes):
 return [key for key,pattern in PATTERNS.items() if pattern.search(data)]

def inspect_file(file:Path):
 issues=[]
 if file.stat().st_size>24*1024*1024:issues.append('oversized (>24 MiB)')
 if file.suffix.lower() in NO_PUBLIC_EXT:issues.append('excluded binary/archive type')
 if file.name=='.env' or file.name.endswith(('.pem','.key')):issues.append('credentials/config risk')
 if file.suffix.lower() in TEXT_EXT or file.name in {'.gitignore','LICENSE','CITATION.cff'}:
  if file.stat().st_size<=8*1024*1024:issues+=sensitive(file.read_bytes())
 if file.suffix.lower()=='.slx':
  try:
   with zipfile.ZipFile(file) as z:
    for info in z.infolist():
     if info.filename.lower().endswith(('.xml','.txt','.json','.m')) and info.file_size<2*1024*1024:
      issues+=['embedded '+name for name in sensitive(z.read(info))]
  except Exception:issues.append('unreadable Simulink package')
 return sorted(set(issues))

def audit(root:Path):
 issues=[];checked=0
 for f in sorted(root.rglob('*')):
  if not f.is_file() or any(x in SKIP_PARTS for x in f.relative_to(root).parts):continue
  checked+=1
  for issue in inspect_file(f):issues.append({'path':f.relative_to(root).as_posix(),'issue':issue})
 return {'status':'PASS' if not issues else 'REVIEW_REQUIRED','files_checked':checked,'issues':issues}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root',nargs='?',default=str(Path(__file__).resolve().parents[1]));a=p.parse_args()
 result=audit(Path(a.root).resolve());print(json.dumps(result,indent=2))
 if result['issues']:raise SystemExit(2)
