# Windows GPU setup — RTX 3050

The RTX 3050 can accelerate Faster-Whisper speech transcription and PaddleOCR. They run sequentially. Discovery, downloads, FFmpeg, SQLite and OpenCV frame sampling remain CPU-oriented.

## 1. Check the NVIDIA driver and Python environment

Use the repository virtual environment in PowerShell:

```powershell
nvidia-smi
python --version
python -c "import platform; print(platform.architecture()[0]); print(platform.machine())"
```

Use 64-bit Python 3.11 on Windows x64. Your NVIDIA driver must be new enough for the CUDA runtime selected below.

## 2. Install project dependencies

```powershell
python -m pip install --upgrade pip
pip install -e ".[dev,discovery,legacy-discovery,audio,ocr,vidtrace,instagram-browser,instagram-fallback]"
```

## 3. Install GPU-enabled PaddlePaddle for OCR

Your processing log showed `PaddleOCR | device=cpu`. The current PaddlePaddle installation is therefore using its CPU backend.

Remove the CPU or previous PaddlePaddle build:

```powershell
python -m pip uninstall -y paddlepaddle paddlepaddle-gpu
```

For Windows x64, Python 3.11 and CUDA 12.6, the current PaddlePaddle Windows install guide lists this stable GPU package:

```powershell
python -m pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
```

Do not install the special Windows wheel for NVIDIA 50-series GPUs: the laptop's RTX 3050 is a 30-series GPU. Use the standard CUDA 12.6 Windows wheel above. Confirm the current wheel instructions in the [official Windows pip installation guide](https://github.com/PaddlePaddle/docs/blob/develop/docs/install/pip/windows-pip_en.md).

## 4. Fix Faster-Whisper CUDA libraries

Your log contains this exact error:

```text
Library cublas64_12.dll is not found or cannot be loaded
```

That means CTranslate2 could not load the CUDA 12 cuBLAS DLL. The Whisper engine then rebuilt itself on CPU, which is why the log changed to `device=cpu | compute=int8`.

Current Faster-Whisper requires:
- cuBLAS for CUDA 12
- cuDNN 9 for CUDA 12

Install both from NVIDIA's official distribution and make sure their DLL folders are available on `PATH`. Restart PowerShell after modifying PATH.

Check:

```powershell
where.exe cublas64_12.dll
where.exe cudnn64_9.dll
```

An installed NVIDIA display driver and a working `nvidia-smi` do not, by themselves, prove these inference runtime DLLs are installed.

See the [Faster-Whisper GPU requirements](https://github.com/SYSTRAN/faster-whisper#gpu).

## 5. Verify both CUDA backends

Run:

```powershell
python -c "import ctranslate2; print('CTranslate2 CUDA devices:', ctranslate2.get_cuda_device_count()); print('CUDA compute types:', ctranslate2.get_supported_compute_types('cuda'))"
python -c "import paddle; print('Paddle:', paddle.__version__); print('Paddle CUDA:', paddle.is_compiled_with_cuda()); print('Paddle device:', paddle.device.get_device())"
shorts-lm doctor
```

Expected:
- CTranslate2 reports at least one CUDA device and supported compute types.
- Paddle CUDA reports `True` and Paddle device is `gpu:0`.
- `shorts-lm doctor` reports `nvidia_smi`, `ctranslate2_cuda` and `paddle_cuda` as available.

If `ctranslate2_cuda` is false, fix the cuBLAS/cuDNN runtime before expecting Whisper to use the GPU. If `paddle_cuda` is false, PaddleOCR will run on CPU even when you pass `--device cuda`.

## 6. Discover and process a small mixed batch

Populate the combined YouTube and Instagram inventory:

```powershell
shorts-lm discover graph-run --platform all --target-new 100 --min-metric 1000000
```

The aggregate target no longer prevents configured Instagram creator seeds from being attempted. The run report shows how many Instagram seed creators were queued and remain pending; they are still bounded by `--max-creators` and the run-time limit.

Then process 2–5 videos first:

```powershell
shorts-lm discover process --platform all --limit 5 --min-metric 1000000 --asr-model small --device cuda --asr-timeout-seconds 300
```

The worker prints per-video progress and ASR/OCR stage progress. Whisper runs in a separate process with a 300-second per-video hard timeout by default. If native inference gets stuck, the worker is terminated and the batch moves on to the next video. The failure is saved in the analysis report and processing logs.

The actual device is recorded in the ASR/OCR engine names:
- `vidtrace-faster-whisper-cuda-int8_float16` means Whisper used CUDA.
- `vidtrace-faster-whisper-cpu-int8` means Whisper fell back to CPU.
- `vidtrace-paddleocr-gpu-0` means PaddleOCR used CUDA.
- `vidtrace-paddleocr-cpu` means PaddleOCR used CPU.

## Notes for 4 GB VRAM

- Keep Whisper at `small` with `int8_float16` initially.
- ASR and OCR run sequentially; their GPU model resources are released between stages.
- Begin with `--limit 2` or `--limit 5`.
- If CUDA reports out-of-memory, retry explicitly with `--device cpu` or reduce `--max-ocr-frames`.
- Raise `--asr-timeout-seconds` only when the worker is still making progress and the audio genuinely needs longer.

## Official installation references

- [PaddlePaddle Windows pip installation](https://github.com/PaddlePaddle/docs/blob/develop/docs/install/pip/windows-pip_en.md)
- [PaddleOCR PaddlePaddle installation](https://www.paddleocr.ai/latest/en/version3.x/paddlepaddle_installation.html)
- [Faster-Whisper GPU requirements](https://github.com/SYSTRAN/faster-whisper#gpu)
