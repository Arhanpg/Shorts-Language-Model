# Windows GPU setup — RTX 3050

This project uses the RTX 3050 for Faster-Whisper ASR and PaddleOCR when the required NVIDIA runtimes are installed. Discovery, database work, FFmpeg and frame sampling continue to use the CPU.

## 1. Check the NVIDIA driver

Open PowerShell:

```powershell
nvidia-smi
```

For PaddlePaddle 3.2.0 with CUDA 12.6, its current installation guide lists NVIDIA driver 550.54.14 or newer for Windows. Update the NVIDIA driver first if your installed driver is older.

## 2. Install the ShortsLM packages

Activate the repository's Python 3.11 virtual environment, then install the project dependencies:

```powershell
python -m pip install --upgrade pip
pip install -e ".[dev,discovery,legacy-discovery,audio,ocr,vidtrace,instagram-browser,instagram-fallback]"
```

## 3. Replace CPU PaddlePaddle with the GPU build

The processing log you shared says `PaddleOCR | device=cpu`. That means OCR was running on CPU in that run. Remove any CPU or previous GPU PaddlePaddle package, then install the official CUDA 12.6 wheel:

```powershell
python -m pip uninstall -y paddlepaddle paddlepaddle-gpu
python -m pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
```

This wheel index is from the official PaddleOCR installation guide. The matching Python 3.11 Windows wheel is provided there for CUDA 12.6.

## 4. Install CUDA 12 and cuDNN 9 runtime libraries for Whisper

The current Faster-Whisper/CTranslate2 GPU path requires cuBLAS for CUDA 12 and cuDNN 9 for CUDA 12. On Windows, make sure the matching NVIDIA DLLs are installed and available on `PATH` before starting PowerShell/Python. If you installed them after opening the terminal, close and reopen it.

Check that the DLLs can be found:

```powershell
where.exe cublas64_12.dll
where.exe cudnn64_9.dll
```

An up-to-date NVIDIA driver alone does not guarantee that the CUDA/cuDNN runtime DLLs required by Faster-Whisper are present.

## 5. Verify both GPU backends

Run:

```powershell
python -c "import paddle; print('Paddle:', paddle.__version__); print('Paddle CUDA:', paddle.is_compiled_with_cuda()); print('Paddle device:', paddle.device.get_device())"
python -c "import ctranslate2; print('CTranslate2 CUDA devices:', ctranslate2.get_cuda_device_count()); print('CUDA compute types:', ctranslate2.get_supported_compute_types('cuda'))"
```

Expected:
- Paddle CUDA reports `True` and Paddle device is `gpu:0`.
- CTranslate2 reports at least one CUDA device and supported compute types.

If Paddle says CUDA is unavailable or CTranslate2 reports zero CUDA devices, do not assume the next processing run will use the GPU.

## 6. Run a small mixed-platform batch

First discover both platforms into the same SQLite inventory:

```powershell
shorts-lm discover graph-run --platform all --target-new 100 --min-metric 1000000
```

Then run:

```powershell
shorts-lm discover process --platform all --limit 10 --min-metric 1000000 --asr-model small --device cuda
```

The command prefers CUDA for both Whisper and PaddleOCR. It alternates YouTube and Instagram candidates when both have eligible inventory. The summary shows per-platform selected/downloaded/processed counts.

The actual ASR and OCR device is also recorded in the engine name inside each video's analysis JSON and the JSONL dataset index. Check those values after the first run. A CPU device in the recorded engine name means the library fell back or the GPU runtime was not available.

For an explicit CPU run, pass `--device cpu`. The CLI accepts `--asr-device` as an alias.

## Notes for the 4 GB VRAM limit

- The default Whisper model is `small` with `int8_float16`, rather than full FP16 large models.
- ASR and OCR execute sequentially. The VidTrace wrappers release their model resources between stages.
- Start with `--limit 2` or `--limit 5` before processing ten videos.
- If CUDA reports an out-of-memory error, retry with `--device cpu` or reduce `--max-ocr-frames`. Do not increase the frame count until the GPU run is stable.

## Official installation references

- [PaddlePaddle installation guide](https://www.paddleocr.ai/latest/en/version3.x/paddlepaddle_installation.html)
- [Faster-Whisper GPU requirements](https://github.com/SYSTRAN/faster-whisper#gpu)
