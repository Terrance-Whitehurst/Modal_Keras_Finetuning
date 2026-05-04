# Modal + Keras Object Detection — Aquarium (D-FINE)

Fine-tune a [D-FINE](https://arxiv.org/abs/2410.13842) object detection model on an aquarium dataset from [HuggingFace](https://huggingface.co/datasets/Francesco/aquarium-qlnqy) using [Keras 3](https://keras.io) and [keras-hub](https://keras.io/keras_hub/), running entirely on [Modal](https://modal.com) cloud GPUs.

> 📺 This repo is the companion code to the YouTube walkthrough: **[link coming soon]**

<p align="center">
  <img src="assets/before.jpg" width="49%" alt="Raw aquarium image" />
  <img src="assets/after.jpg" width="49%" alt="Same image with D-FINE detections" />
</p>

---

## What this demo shows

- Fine-tune **D-FINE** — a state-of-the-art real-time object detector — on a custom dataset using Keras 3
- Load and preprocess a HuggingFace object detection dataset with zero manual annotation work
- Apply the **freeze → unfreeze** transfer learning pattern to protect pretrained backbone weights during warmup
- Run the entire ML pipeline — dataset download, training, and inference — on **Modal cloud GPUs** with no local GPU required
- Visualize model predictions as annotated images with bounding boxes, class labels, and confidence scores

---

## Prerequisites

| Service | What it's for | Sign up |
|---------|---------------|---------|
| [Modal](https://modal.com) | Cloud GPU compute — runs training and inference | [modal.com](https://modal.com) |
| [HuggingFace](https://huggingface.co) | Dataset hosting — downloads the Aquarium dataset | [huggingface.co](https://huggingface.co) |
| [uv](https://docs.astral.sh/uv/) | Python dependency management | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/terrance-whitehurst/Modal_Keras_Finetuning.git
cd Modal_Keras_Finetuning
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Authenticate with Modal

```bash
uv run modal setup
```

### 4. (Optional) Create a HuggingFace token

The default Aquarium dataset is public — skip this step unless you swap to a gated dataset:

```bash
uv run modal secret create huggingface-token HF_TOKEN=hf_your_token_here
```

---

## Run it

```bash
uv run modal run apps/keras_finetune.py
```

One command. Downloads the dataset, trains the model, and runs inference — all on Modal's cloud GPUs.

---

## Configuration

All settings live at the top of `apps/keras_finetune.py`:

```python
# ── Configuration ──────────────────────────────────────────────────────────
HF_DATASET = "Francesco/aquarium-qlnqy"               # ← change this to try your own HuggingFace dataset
CLASS_NAMES = [                                        # class labels from the dataset
    "aquarium", "fish", "jellyfish", "penguin",
    "puffin", "shark", "starfish", "stingray",
]
IMAGE_SIZE  = (640, 640)                               # input resolution — this dataset is already 640×640
MAX_BOXES   = 50                                       # max detections per image

# ── Training ───────────────────────────────────────────────────────────────
MODEL_PRESET            = "dfine_nano_coco"            # keras-hub D-FINE preset (pretrained on COCO 80-class)
BACKBONE_FROZEN_EPOCHS  = 3                            # freeze backbone for warmup, then unfreeze all layers
EPOCHS                  = 20                           # ← increase to 50+ for production-quality results
BATCH_SIZE              = 8                            # images per training step
LEARNING_RATE           = 1e-4                         # AdamW learning rate

# ── Infrastructure ─────────────────────────────────────────────────────────
TRAIN_GPU   = "L4"                                     # Modal GPU type — L4, A100, or H100
VOLUME_NAME = "keras-aquarium-detection-vol"           # Modal Volume name for persisting data and checkpoints
```

---

## How it works

```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│  download_dataset()  │ ──► │       train()        │ ──► │      predict()       │
│                      │     │                      │     │                      │
│  HuggingFace Hub     │     │  D-FINE via keras-hub│     │  Load best.keras     │
│  → numpy arrays      │     │  Phase 1: freeze     │     │  Run on test images  │
│  → Modal Volume      │     │  Phase 2: unfreeze   │     │  Draw bounding boxes │
│                      │     │  → best.keras        │     │  → predictions/*.jpg │
└──────────────────────┘     └──────────────────────┘     └──────────────────────┘
                     ↕                    ↕                          ↕
              Modal Volume: /root/data/  (shared across all stages)
```

The full pipeline lives in a single file: `apps/keras_finetune.py`

---

## Download results

After the pipeline completes, download your annotated predictions:

```bash
modal volume get keras-aquarium-detection-vol /root/data/predictions/ .
```
