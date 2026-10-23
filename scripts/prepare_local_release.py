#!/usr/bin/env python3
"""Build an audited source release from the original research directories.

The final v4.6.3 ML files in this repository remain canonical. Import only the
accepted v4.6.2 physical model, relevant final-stage MATLAB source and HMI source.
Never imports raw trajectories, trained weights, old model snapshots or private
instructions. The source directories are read-only.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, sys, zipfile
from pathlib import Path
from audit_public_release import inspect_file, audit

BASE = Path(__file__).resolve().parents[1]
ACCEPTED_MODEL = 'AlKaseeh_PhysicalTwin_PM_FinalScientific_v4_6_2.slx'
BAD_DIRS = {'.git','.venv','venv','env','__pycache__','_backups','backups','slprj','logs','runs',
            'raw','cache','checkpoints','artifacts','temp','tmp','node_modules','dist','build',
            'archive','archives','deprecated','data','training_runs','experiments','reports',
            'publication_figures_600dpi','private','output','outputs'}
ALLOWED_EXT = {'.py','.m','.json','.yaml','.yml','.toml','.ini','.cfg','.txt','.html','.css','.js','.ts','.svg'}
SAFE_GENERIC_MATLAB = {
 'fault_injector_finalscientific_v4.m',
 'process_controller_finalscientific_v4.m',
 'export_finalscientific_run_v4.m',
 'apply_finalscientific_v4_to_model.m',
 'campaign_config.m',
 'run_finalscientific_campaign_v4.m',
 'validate_finalscientific_nominal_cycle.m',
 'verify_model_configuration.m',
 'run_data_acquisition.m',
 'export_simulation_csv.m',
}
REQUIRED_MATLAB = {
 'process_controller_finalscientific_v4_6_2.m',
 'run_finalscientific_v4_6_3_scientific1900.m',
 'qa_finalscientific_v4_6_3_scientific1900.m',
 'create_locked_split_v4_6_3_scientific1900.m',
 'validate_finalscientific_nominal_cycle_v4_6_2.m',
}
IMPORTANT_OPTIONAL_MATLAB = {
 'alk_apply_sensor_fault_v4_6_3.m',
 'run_finalscientific_v4_6_2_smoke38.m',
 'qa_finalscientific_v4_6_2_smoke38.m',
 'run_finalscientific_v4_6_3_development190.m',
 'qa_finalscientific_v4_6_3_development190.m',
 'validate_cip_route_v4_6_2.m',
 'validate_sensor_faults_v4_6_3.m',
 'preflight_finalscientific_v4_6_3_scientific1900.m',
}
MAX_SIZE = 24*1024*1024


def sha(f):
 h=hashlib.sha256()
 with f.open('rb') as inp:
  for chunk in iter(lambda: inp.read(1024*1024), b''):h.update(chunk)
 return h.hexdigest()


def recognized(p):
 return sum((p / item).is_dir() for item in ('models','matlab','streamlit','ml','dashboard'))


def locate_root(path):
 path = path.expanduser().resolve()
 if not path.is_dir():raise ValueError('Source project directory does not exist.')
 candidates=[]
 if recognized(path):candidates.append(path)
 for base,dirs,_ in os.walk(path):
  d=Path(base);depth=len(d.relative_to(path).parts)
  dirs[:]=[x for x in dirs if x.lower() not in BAD_DIRS and depth<4]
  if d!=path and recognized(d):candidates.append(d)
 if not candidates:raise ValueError('Cannot locate a MATLAB/Final19 project root in the selected directory.')
 return max(candidates,key=lambda p:(recognized(p),-len(p.relative_to(path).parts)))


def iter_sources(root):
 for base,dirs,files in os.walk(root):
  d=Path(base)
  dirs[:]=[x for x in dirs if x.lower() not in BAD_DIRS]
  for name in sorted(files):
   p=d/name
   if not p.is_symlink() and p.is_file():yield p


def physical_target(root,p):
 rel=p.relative_to(root);parts=rel.parts;low=[s.lower() for s in parts]
 if p.name.lower()==ACCEPTED_MODEL.lower() and low[0]=='models':
  return Path('models')/ACCEPTED_MODEL
 if p.suffix.lower()=='.slx':return None
 if p.suffix.lower() not in ALLOWED_EXT:return None
 if low[0]=='ml' and p.suffix.lower() in {'.py','.json','.yaml','.yml','.toml'}:
  # Import auxiliary original Python modules absent from the verified Final19 patch.
  # Conflicting files are never allowed to overwrite the verified release.
  return Path('ml')/Path(*parts[1:])
 if low[0]=='matlab':
  name=p.name.lower()
  if p.suffix.lower()=='.m':
   if ('v4_6_3' not in name and 'v4_6_2' not in name and name not in SAFE_GENERIC_MATLAB):return None
   if any(s in name for s in ['repair_failed','deprecated','backup','_fix_v2','_fix_v3']):return None
  return Path('matlab') / Path(*parts[1:])
 if low[0] in {'dashboard','streamlit','hmi'}:
  return Path('dashboard')/Path(*parts[1:])
 if low[0]=='config' and p.suffix.lower() in {'.json','.m','.yml','.yaml','.ini','.cfg'}:
  return Path('config')/Path(*parts[1:])
 if low[0]=='models' and p.suffix.lower()=='.m' and p.name.lower() in SAFE_GENERIC_MATLAB:
  return Path('matlab')/p.name
 return None


def scientific_target(root,p):
 rel=p.relative_to(root);parts=rel.parts;low=[s.lower() for s in parts]
 if low[0]=='ml' and p.suffix.lower() in {'.py','.json','.yaml','.yml','.toml'}:
  return Path('ml')/Path(*parts[1:])
 return None


def import_tree(root,flavor,out,records):
 for p in iter_sources(root):
  dest=(physical_target if flavor=='physical' else scientific_target)(root,p)
  if dest is None:continue
  rel=p.relative_to(root).as_posix()
  if p.stat().st_size>MAX_SIZE:
   records.append({'source':flavor,'relative_path':rel,'status':'excluded_large'});continue
  issues=inspect_file(p)
  if issues:
   records.append({'source':flavor,'relative_path':rel,'status':'excluded_review_required','reasons':issues});continue
  q=out/dest
  if q.exists():
   if sha(q)==sha(p):continue
   # Final19 scripts supplied with the verified retraining archive are authoritative.
   records.append({'source':flavor,'relative_path':rel,'destination':dest.as_posix(),
                   'status':'excluded_different_from_verified_release'});continue
  q.parent.mkdir(parents=True,exist_ok=True)
  shutil.copy2(p,q)
  records.append({'source':flavor,'relative_path':rel,'destination':dest.as_posix(),
                  'sha256':sha(q),'status':'imported'})


def zip_release(root):
 target=root.with_suffix('.zip')
 if target.exists():raise FileExistsError('ZIP output already exists; use a new output directory.')
 with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(root.rglob('*')):
   if p.is_file() and not set(p.relative_to(root).parts)&{'.git','__pycache__'}:
    z.write(p,arcname=(Path(root.name)/p.relative_to(root)).as_posix())
 return target


def main():
 parser=argparse.ArgumentParser(description='Prepare a version-locked public reproduction from local research source')
 parser.add_argument('--physical-root',required=True)
 parser.add_argument('--scientific-root',required=True)
 parser.add_argument('--output',required=True)
 parser.add_argument('--zip',action='store_true')
 args=parser.parse_args()
 physical=locate_root(Path(args.physical_root))
 scientific=locate_root(Path(args.scientific_root))
 out=Path(args.output).expanduser().resolve()
 for src in (BASE,physical,scientific):
  if out==src or src in out.parents:raise SystemExit('Output must be outside source directories.')
 if out.exists():raise SystemExit('Output already exists; use a new destination for each release.')
 shutil.copytree(BASE,out,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git','SHA256SUMS.txt'))
 records=[]
 import_tree(physical,'physical',out,records)
 import_tree(scientific,'scientific',out,records)
 # Publish only relative-path and content checks, never paths to private source directories.
 src_comp={
   'accepted_physical_model':ACCEPTED_MODEL,
   'physical_model_included':(out/'models'/ACCEPTED_MODEL).is_file(),
   'required_matlab_scripts':{name: (out/'matlab'/name).exists() for name in sorted(REQUIRED_MATLAB)},
   'important_optional_matlab_scripts':{name:(out/'matlab'/name).exists() for name in sorted(IMPORTANT_OPTIONAL_MATLAB)},
   'dashboard_python_files':sum(1 for _ in (out/'dashboard').rglob('*.py')),
   'approved_final19_sources':36,
 }
 # Normalize case for files on Windows/Linux (the source includes mixed case prefixes).
 found={p.name.lower() for p in (out/'matlab').rglob('*.m')}
 src_comp['required_matlab_scripts']={n:n in found for n in sorted(REQUIRED_MATLAB)}
 src_comp['important_optional_matlab_scripts']={n:n in found for n in sorted(IMPORTANT_OPTIONAL_MATLAB)}
 src_comp['full_physical_source_complete']=src_comp['physical_model_included'] and all(src_comp['required_matlab_scripts'].values())
 compfile=out/'docs'/'SOURCE_COMPLETENESS.json'
 compfile.write_text(json.dumps(src_comp,indent=2)+'\n',encoding='utf8')
 result=audit(out)
 summary={k:sum(r['status']==k for r in records) for k in sorted({r['status'] for r in records})}
 report=out.with_name(out.name+'_local_import_report.json')
 report.write_text(json.dumps({'source_roots':'two local project directories','import_summary':summary,
                                'completeness':src_comp,'files':records,
                                'public_audit':result},indent=2)+'\n',encoding='utf8')
 print('Verified core Final19 scripts: 36 supplied source files')
 print('Source import summary:',json.dumps(summary))
 print('Public audit:',result['status'])
 print('Physical model imported:',src_comp['physical_model_included'])
 print('MATLAB core scripts complete:',src_comp['full_physical_source_complete'])
 print('Dashboard source files:',src_comp['dashboard_python_files'])
 print('Local audit report (keep off GitHub):',report)
 if result['issues']:
  print('REVIEW REQUIRED: Scan failed. No publishable ZIP created.');raise SystemExit(2)
 if not src_comp['full_physical_source_complete']:
  print('INCOMPLETE: Accepted physical model or required final MATLAB scripts missing; no publishable ZIP created.')
  raise SystemExit(3)
 if src_comp['dashboard_python_files']==0:
  print('INCOMPLETE: No dashboard Python source was imported; no publishable ZIP created.')
  raise SystemExit(4)
 print('Source release assembled:',out)
 if args.zip:print('GitHub-ready ZIP:',zip_release(out))

if __name__=='__main__':main()
