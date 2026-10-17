"""Stage a private finite T4 proof notebook without touching existing film notebooks."""
import json, pathlib
root = pathlib.Path(__file__).resolve().parents[2]
source = (root / 'fleet/kernels/film_render_probe.py').read_text(encoding='utf-8')
compile(source, 'film_render_probe.py', 'exec')
dest = root / 'state/film_render_probe_20261017'
dest.mkdir(parents=True, exist_ok=True)
notebook = {'nbformat': 4, 'nbformat_minor': 4,
            'metadata': {'kernelspec': {'name': 'python3', 'display_name': 'Python 3', 'language': 'python'},
                         'accelerator': 'GPU'},
            'cells': [{'cell_type': 'code', 'execution_count': None, 'metadata': {},
                       'outputs': [], 'source': source.splitlines(keepends=True)}]}
metadata = {'id': 'isearchxsolve/oiioii-real-render-proof', 'title': 'OiiOii Real Render Proof',
            'code_file': 'film_render_probe.ipynb', 'language': 'python', 'kernel_type': 'notebook',
            'is_private': True, 'enable_gpu': True, 'machine_shape': 'NvidiaTeslaT4',
            'enable_internet': True, 'dataset_sources': [], 'competition_sources': [], 'kernel_sources': []}
(dest / metadata['code_file']).write_text(json.dumps(notebook, indent=1), encoding='utf-8')
(dest / 'kernel-metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
print('COMPILE_OK PRIVATE_T4_PROBE', str(dest))
