"""One real creative video render on Kaggle. No mock renderer or success fallback.

Reference: https://huggingface.co/zai-org/CogVideoX-2b
Run only on a private, finite Kaggle T4 notebook, never on the laptop.
"""
import datetime, hashlib, json, os, pathlib, subprocess, sys, time

OUT = pathlib.Path('/kaggle/working/film-render-proof')
OUT.mkdir(parents=True, exist_ok=True)
receipt = {'started_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'status': 'hardware_gate_pending', 'paid_product_ready': False,
           'model': 'zai-org/CogVideoX-2b',
           'model_documentation': 'https://huggingface.co/zai-org/CogVideoX-2b',
           'scope': 'standalone real render; customer workflow and payment are unverified'}

def checkpoint(status):
    receipt['status'] = status
    (OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print('FILM_PROBE', status, flush=True)

try:
    # Hardware must be earned before installs, model downloads or inference.
    smi = subprocess.run(['nvidia-smi'], capture_output=True, text=True, timeout=20, check=True)
    print(smi.stdout, flush=True)
    import torch
    names = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    print('ACTUAL_GPU_NAMES', names, flush=True)
    receipt['hardware'] = {'names': names, 'nvidia_smi': smi.stdout, 'torch': torch.__version__}
    assert len(names) == 2 and all('T4' in name for name in names), 'requires ordered GPU T4 x2'
    checkpoint('hardware_verified')
    os.environ['HF_HOME'] = '/kaggle/temp/oioi-model-cache'
    os.environ['HF_HUB_ETAG_TIMEOUT'] = '30'
    os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '60'
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q',
                    'diffusers>=0.30.1,<1', 'transformers>=4.44,<5',
                    'accelerate>=0.33,<2', 'imageio-ffmpeg>=0.5.1',
                    'sentencepiece', 'safetensors'], check=True, timeout=600)
    import diffusers, transformers, numpy as np
    from diffusers import CogVideoXPipeline
    from diffusers.utils import export_to_video
    from PIL import Image
    receipt['libraries'] = {'diffusers': diffusers.__version__, 'transformers': transformers.__version__}
    checkpoint('loading_real_model')
    pipe = CogVideoXPipeline.from_pretrained(receipt['model'], torch_dtype=torch.float16)
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_slicing()
    pipe.vae.enable_tiling()
    prompt = ('A cinematic slow camera move across a quiet futuristic garden at sunrise. '
              'Warm light shines through green leaves and glass architecture. A small silver '
              'robot gently waters a young tree, droplets sparkle as they fall. Natural movement, '
              'coherent scene, elegant composition, no text, no logos.')
    receipt['request'] = {'prompt': prompt, 'frames': 49, 'fps': 8, 'steps': 30,
                          'width': 720, 'height': 480, 'seed': 172026}
    checkpoint('rendering')
    started = time.monotonic()
    frames = pipe(prompt=prompt, num_videos_per_prompt=1, num_inference_steps=30,
                  num_frames=49, guidance_scale=6, output_type='pil',
                  generator=torch.Generator(device='cuda').manual_seed(172026)).frames[0]
    receipt['render_seconds'] = time.monotonic() - started
    arrays = [np.asarray(frame) for frame in frames]
    assert len(arrays) == 49 and all(np.isfinite(a).all() for a in arrays), 'invalid model output'
    receipt['actual_frame_std'] = float(np.std(arrays))
    receipt['actual_frame_change'] = float(np.mean(np.abs(arrays[-1].astype(float) - arrays[0].astype(float))))
    assert receipt['actual_frame_std'] > 1 and receipt['actual_frame_change'] > 0.1, 'blank or frozen render'
    target = OUT / 'original-garden-render.mp4'
    export_to_video(frames, str(target), fps=8)
    import imageio_ffmpeg
    reader = imageio_ffmpeg.read_frames(str(target))
    metadata = next(reader)
    decoded_count = sum(1 for _ in reader)
    receipt['media'] = {'metadata': metadata, 'decoded_frames': decoded_count,
                        'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
    assert decoded_count == 49 and metadata['size'] == (720, 480), 'MP4 decode validation failed'
    sheet = Image.new('RGB', (720, 480))
    for index, position in enumerate(np.linspace(0, 48, 9, dtype=int)):
        image = Image.fromarray(arrays[position].astype('uint8')).resize((240, 160))
        sheet.paste(image, ((index % 3) * 240, (index // 3) * 160))
    sheet.save(OUT / 'contact-sheet.jpg')
    receipt['finished_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    checkpoint('rendered_requires_visual_review')
except Exception as error:
    receipt['error_type'] = type(error).__name__
    receipt['error'] = str(error)[:1000]
    checkpoint('failed')
    raise
