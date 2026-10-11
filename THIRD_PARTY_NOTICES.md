# Third-party notices

ViTranscript's own source code is released under the [MIT License](LICENSE).

The app **does not bundle** any model weights or ffmpeg binaries. They are downloaded
on first use into the user's data directory, and each one stays under its own license.
Check the linked model cards and repositories for the full attribution and license terms
before you redistribute them.

## Speech recognition models (faster-whisper / CTranslate2)

Each model is pinned to a Hugging Face commit in `app/config.py` (`MODEL_REGISTRY`).

| Key | Runtime artifact (CTranslate2) | License stated by the artifact | Original model | Original license |
|---|---|---|---|---|
| `phowhisper-small` | [`diepho/PhoWhisper-small-ct2`](https://huggingface.co/diepho/PhoWhisper-small-ct2) | Apache-2.0 | [`vinai/PhoWhisper-small`](https://huggingface.co/vinai/PhoWhisper-small) | BSD-3-Clause |
| `phowhisper-medium` | [`diepho/PhoWhisper-medium-ct2`](https://huggingface.co/diepho/PhoWhisper-medium-ct2) | not stated | [`vinai/PhoWhisper-medium`](https://huggingface.co/vinai/PhoWhisper-medium) | BSD-3-Clause |
| `phowhisper-large` | [`kiendt/PhoWhisper-large-ct2`](https://huggingface.co/kiendt/PhoWhisper-large-ct2) | MIT | [`vinai/PhoWhisper-large`](https://huggingface.co/vinai/PhoWhisper-large) | BSD-3-Clause |
| `large-v3-turbo` | [`deepdml/faster-whisper-large-v3-turbo-ct2`](https://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2) | MIT | [`openai/whisper-large-v3-turbo`](https://huggingface.co/openai/whisper-large-v3-turbo) | MIT |
| `whisper-small` | [`Systran/faster-whisper-small`](https://huggingface.co/Systran/faster-whisper-small) | MIT | [`openai/whisper-small`](https://huggingface.co/openai/whisper-small) | Apache-2.0 |

PhoWhisper: VinAI Research — *PhoWhisper: Automatic Speech Recognition for Vietnamese*
(Le et al., 2024).

## Speaker diarization models (sherpa-onnx)

They are downloaded from the [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) releases
(Apache-2.0), and their SHA-256 is pinned in `app/diarize.py`.

- **Segmentation:** `sherpa-onnx-pyannote-segmentation-3-0`, converted from
  [`pyannote/segmentation-3.0`](https://huggingface.co/pyannote/segmentation-3.0) (MIT).
- **Speaker embedding:** `3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k`, from
  [3D-Speaker](https://github.com/modelscope/3D-Speaker) /
  ModelScope `iic/speech_eres2net_base_sv_zh-cn_3dspeaker_16k` (Apache-2.0).

## Punctuation restoration: ViBERT-CAPU ONNX INT8

- Runtime artifact: `welcomyou/vibert-capu-onnx`
- Revision: `a7754d037f4a9e29f7f3224f27acb60149eab874` (the SHA-256 is pinned in `app/config.py`)
- Source: https://huggingface.co/welcomyou/vibert-capu-onnx
- Original model: `dragonSwing/vibert-capu`
- Original source: https://huggingface.co/dragonSwing/vibert-capu
- License stated by the model repositories: CC-BY-SA-4.0

## FFmpeg

The app uses the `ffmpeg`/`ffprobe` already on the user's `PATH`. If none is found, the
[`static-ffmpeg`](https://github.com/zackees/static_ffmpeg) package (MIT) downloads a
prebuilt FFmpeg binary. FFmpeg is licensed under LGPL-2.1+ or GPL-2.0+/GPL-3.0+,
depending on how the build was configured. See https://ffmpeg.org/legal.html.

## Python dependencies

The runtime dependencies are listed in `pyproject.toml`, with exact versions in `uv.lock`.
Each one stays under its own license (for example faster-whisper: MIT, sherpa-onnx:
Apache-2.0, FastAPI: MIT, onnxruntime: MIT).
