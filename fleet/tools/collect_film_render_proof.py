"""Download a finished private render and verify the actual MP4 against its receipt."""
import hashlib, json, os, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
KERNEL = 'isearchxsolve/oiioii-real-render-proof'
DEST = ROOT / 'state/film_render_output_20261017'
env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}
status = subprocess.run(['kaggle', 'kernels', 'status', KERNEL], capture_output=True,
                        text=True, encoding='utf-8', env=env, timeout=40, check=True).stdout
print(status.strip())
if 'COMPLETE' not in status and 'ERROR' not in status:
    raise SystemExit('Render has not finished; no completion claimed.')
DEST.mkdir(parents=True, exist_ok=True)
subprocess.run(['kaggle', 'kernels', 'output', KERNEL, '-p', str(DEST)], env=env, check=True, timeout=180)
receipts = list(DEST.rglob('receipt.json'))
if len(receipts) != 1:
    raise RuntimeError('Expected exactly one genuine GPU receipt')
receipt = json.loads(receipts[0].read_text())
if receipt.get('status') != 'rendered_requires_visual_review':
    print(json.dumps(receipt, indent=2))
    raise SystemExit('Real GPU attempt failed; failure receipt preserved.')
video = receipts[0].parent / 'original-garden-render.mp4'
digest = hashlib.sha256(video.read_bytes()).hexdigest()
assert digest == receipt['media']['sha256'], 'Downloaded MP4 hash differs from GPU output'
assert video.stat().st_size == receipt['media']['bytes'], 'Downloaded MP4 size differs from GPU output'
local = {'artifact': str(video), 'sha256': digest, 'bytes': video.stat().st_size,
         'decoded_frames_on_gpu': receipt['media']['decoded_frames'],
         'hardware': receipt['hardware']['names'], 'requires_visual_review': True,
         'customer_workflow_verified': False, 'payment_verified': False}
(DEST / 'download_verified.json').write_text(json.dumps(local, indent=2), encoding='utf-8')
print(json.dumps(local, indent=2))
