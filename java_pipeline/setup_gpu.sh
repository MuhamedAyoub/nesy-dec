#!/usr/bin/env bash
# One-time setup on the GPU box (vast.ai PyTorch image or any CUDA Linux host).
#
# Creates two Python environments:
#   .venv       NeSy-Rep and GraphRL-Dec: the box's torch, plus transformers
#               and peft at the versions the Rails runs used (V2_RERUN_RUNBOOK.md).
#               On vast.ai PyTorch images it is a link to /venv/main.
#   .venv-rldec RLDec and HierDec: Python 3.10, ray[rllib] 2.9.2 and the other
#               pins of decomp-rldec/requirements.txt (ray 2.9.2 has no wheels
#               for Python 3.12+)
#
# Usage (from <repo>/): bash java_pipeline/setup_gpu.sh
#        RLDEC=0 bash java_pipeline/setup_gpu.sh   # main environment only
set -euo pipefail
RLDEC="${RLDEC:-1}"
cd "$(dirname "$0")/.."

command -v uv >/dev/null || python3 -m pip install -q --upgrade uv
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv

# --- main environment -------------------------------------------------------
# vast.ai PyTorch images keep a CUDA torch matched to the driver in /venv/main.
# Installing transformers and peft into a fresh venv lets the resolver pull a
# newer torch wheel the driver cannot run, so we install into /venv/main itself,
# pin torch to the version already there, and point .venv at it. Elsewhere a
# venv is created with a CUDA 12.1 torch.
if [[ -x /venv/main/bin/python ]] && /venv/main/bin/python -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
  ln -sfn /venv/main .venv
else
  uv venv -q .venv
  uv pip install -q --python .venv/bin/python torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121
fi
TORCH_VERSION=$(.venv/bin/python -c "import torch; print(torch.__version__)")
uv pip install -q --python .venv/bin/python "torch==$TORCH_VERSION" "transformers==4.45.2" "peft==0.13.2" \
  "scikit-learn>=1.3" "numpy" "nltk"
uv cache clean -q || true          # the disk on rented boxes is small
.venv/bin/python -c "
import torch, transformers, peft, sklearn
print('main env:', torch.__version__, 'cuda', torch.cuda.is_available(), transformers.__version__, peft.__version__, sklearn.__version__)
assert torch.cuda.is_available(), 'torch cannot see the GPU'
from transformers import AutoModel, AutoTokenizer
AutoTokenizer.from_pretrained('microsoft/unixcoder-base'); AutoModel.from_pretrained('microsoft/unixcoder-base')
print('unixcoder-base cached')
"

# --- RLDec / HierDec environment ---------------------------------------------
if [[ "$RLDEC" == "0" ]]; then df -h . | tail -1; echo "setup OK (main environment only, RLDEC=0)"; exit 0; fi
uv venv -q -p 3.10 .venv-rldec
uv pip install -q --python .venv-rldec/bin/python torch==2.1.2 --index-url https://download.pytorch.org/whl/cu121
uv pip install -q --python .venv-rldec/bin/python "torch==2.1.2" "numpy==1.26.4" "scipy>=1.11.4" "pandas==2.2.0" \
  "pyarrow==15.0.2" "networkx>=2.8.4" "ray[rllib]==2.9.2" "scikit-learn==1.3.2" "gymnasium==0.28.1" tifffile \
  "protobuf>=4.25.2,<5" "grpcio>=1.48.2" "setuptools<70"
uv cache clean -q || true
.venv-rldec/bin/python -c "import ray, torch, sklearn; print('rldec env:', ray.__version__, torch.__version__, 'cuda', torch.cuda.is_available(), sklearn.__version__)"
df -h . | tail -1
echo "setup OK"
