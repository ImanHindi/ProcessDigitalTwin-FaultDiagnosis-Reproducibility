from pathlib import Path
from PIL import Image
try:
    import tifffile
except Exception:
    tifffile=None
from final19_common import REPORT_DIR
OUT=REPORT_DIR/'publication_figures_600dpi'
files=sorted(OUT.glob('*.png'))
if not files:raise SystemExit('No Final19 publication PNG files found.')
failed=[]
for p in files:
    try:
        with Image.open(p) as im:im.load();w,h=im.size
        if w<500 or h<300:raise RuntimeError(f'small image {w}x{h}')
        tif=p.with_suffix('.tiff')
        if tif.exists() and tifffile is not None:
            with tifffile.TiffFile(tif) as tf:_=tf.pages[0].asarray()
        print('OK',p.name,w,h)
    except Exception as exc:failed.append((p,exc));print('FAIL',p.name,exc)
if failed:raise SystemExit(2)
print(f'Verified {len(files)} Final19 publication figures.')
