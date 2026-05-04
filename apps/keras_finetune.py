"""
Modal + Keras Object Detection — Aquarium (D-FINE)

Fine-tune a D-FINE object detection model on the Aquarium dataset using
Keras 3 and keras-hub, running entirely on Modal cloud GPUs. No local GPU
required — the full pipeline runs in the cloud with a single command.

Usage:
    uv run modal run apps/keras_finetune.py
"""

import modal

# ── Configuration ──────────────────────────────────────────────────────────
HF_DATASET = "Francesco/aquarium-qlnqy"               # ← change this to try your own HuggingFace dataset
CLASS_NAMES = [                                        # class labels from the dataset
    "aquarium", "fish", "jellyfish", "penguin",
    "puffin", "shark", "starfish", "stingray",
]
NUM_CLASSES = len(CLASS_NAMES)                         # number of object classes to detect
IMAGE_SIZE  = (640, 640)                               # input resolution — this dataset is already 640×640
MAX_BOXES   = 50                                       # max detections per image (pad shorter lists to this)

# ── Training ───────────────────────────────────────────────────────────────
MODEL_PRESET            = "dfine_nano_coco"            # keras-hub D-FINE preset (pretrained on COCO 80-class)
BACKBONE_FROZEN_EPOCHS  = 3                            # freeze backbone for warmup, then unfreeze all layers
EPOCHS                  = 20                           # ← increase to 50+ for production-quality results
BATCH_SIZE              = 8                            # images per training step
LEARNING_RATE           = 1e-4                         # AdamW learning rate
GLOBAL_CLIPNORM         = 10.0                         # gradient clipping norm

# ── Infrastructure ─────────────────────────────────────────────────────────
TRAIN_GPU     = "L4"                                   # Modal GPU type — L4, A100, or H100
TRAIN_TIMEOUT = 3600                                   # hard timeout in seconds (1 hour)
VOLUME_NAME   = "keras-aquarium-detection-vol"         # Modal Volume name for persisting data and checkpoints

# ── Modal App Setup ────────────────────────────────────────────────────────
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
DATA_DIR = "/root/data"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "keras>=3.5",
        "keras-hub>=0.28",
        "tensorflow>=2.16",
        "datasets>=3.0",
        "pillow>=10.0",
        "numpy>=1.26",
    )
)

app = modal.App("keras-aquarium-detection", image=image)


# ── Stage 1: Download & Prepare Dataset ────────────────────────────────────
@app.function(
    volumes={DATA_DIR: volume},
    secrets=[modal.Secret.from_name("huggingface-token", required=False)],
    timeout=600,
)
def download_dataset():
    """Download the Aquarium dataset from HuggingFace and save as numpy arrays."""
    import os

    import numpy as np
    from datasets import load_dataset

    print(f"📥 Downloading '{HF_DATASET}' from HuggingFace...")
    ds = load_dataset(HF_DATASET)

    for split_name in ["train", "validation", "test"]:
        split = ds[split_name]
        split_dir = os.path.join(DATA_DIR, split_name)
        os.makedirs(split_dir, exist_ok=True)

        all_images = []
        all_boxes  = []
        all_labels = []

        for sample in split:
            # ── Image ── already 640×640 for this dataset, just convert to array
            img_array = np.array(sample["image"].convert("RGB"), dtype=np.float32) / 255.0
            all_images.append(img_array)

            # ── Bounding boxes & labels ──
            objects = sample["objects"]
            raw_boxes  = np.array(objects["bbox"],     dtype=np.float32)   # [[x,y,w,h], ...]
            raw_labels = np.array(objects["category"], dtype=np.int32)     # [cls_id, ...]

            # Pad or truncate to MAX_BOXES so every sample has the same shape
            n = min(len(raw_boxes), MAX_BOXES)
            padded_boxes  = np.full((MAX_BOXES, 4), -1.0, dtype=np.float32)
            padded_labels = np.full((MAX_BOXES,),   -1,   dtype=np.int32)

            if n > 0:
                padded_boxes[:n]  = raw_boxes[:n]
                padded_labels[:n] = raw_labels[:n]

            all_boxes.append(padded_boxes)
            all_labels.append(padded_labels)

        # Save as stacked numpy arrays
        np.save(os.path.join(split_dir, "images.npy"), np.stack(all_images))
        np.save(os.path.join(split_dir, "boxes.npy"),  np.stack(all_boxes))
        np.save(os.path.join(split_dir, "labels.npy"), np.stack(all_labels))

        print(f"  ✅ {split_name}: {len(all_images)} images")

    volume.commit()
    print("\n✅ Dataset prepared and saved to Modal Volume.")


# ── Stage 2: Train ─────────────────────────────────────────────────────────
@app.function(
    gpu=TRAIN_GPU,
    volumes={DATA_DIR: volume},
    timeout=TRAIN_TIMEOUT,
)
def train():
    """Fine-tune D-FINE on the Aquarium dataset using Keras 3 + keras-hub."""
    import os
    os.environ["KERAS_BACKEND"] = "tensorflow"

    import keras
    import keras_hub
    import numpy as np
    import tensorflow as tf

    print("🔧 Loading dataset from Volume...")
    volume.reload()

    def load_split(split_name):
        d = os.path.join(DATA_DIR, split_name)
        return (
            np.load(os.path.join(d, "images.npy")),
            np.load(os.path.join(d, "boxes.npy")),
            np.load(os.path.join(d, "labels.npy")),
        )

    train_images, train_boxes, train_labels = load_split("train")
    val_images,   val_boxes,   val_labels   = load_split("validation")

    print(f"  Train : {len(train_images)} images")
    print(f"  Val   : {len(val_images)} images")

    # ── tf.data pipelines ──
    def make_dataset(images, boxes, labels, shuffle=False):
        ds = tf.data.Dataset.from_tensor_slices((
            images,
            {"boxes": boxes, "labels": labels},
        ))
        if shuffle:
            ds = ds.shuffle(buffer_size=len(images), seed=42)
        return ds.batch(BATCH_SIZE).prefetch(tf.data.AUTOTUNE)

    train_ds = make_dataset(train_images, train_boxes, train_labels, shuffle=True)
    val_ds   = make_dataset(val_images,   val_boxes,   val_labels)

    # ── Build model: pretrained backbone + fresh detection head ──
    print(f"\n🏗️  Building D-FINE model (preset: {MODEL_PRESET})...")
    backbone = keras_hub.models.DFineBackbone.from_preset(MODEL_PRESET)
    model = keras_hub.models.DFineObjectDetector(
        backbone=backbone,
        num_classes=NUM_CLASSES,
        bounding_box_format="xywh",
    )
    print(f"   Parameters: {model.count_params():,}")

    # ── Phase 1: warm up — train detection head only ──
    print(f"\n🔥 Phase 1/{BACKBONE_FROZEN_EPOCHS} epochs — backbone frozen (detection head only)")
    model.backbone.trainable = False
    model.compile(
        optimizer=keras.optimizers.AdamW(
            learning_rate=LEARNING_RATE,
            global_clipnorm=GLOBAL_CLIPNORM,
        ),
    )
    model.fit(train_ds, validation_data=val_ds, epochs=BACKBONE_FROZEN_EPOCHS)

    # ── Phase 2: fine-tune all layers ──
    remaining = EPOCHS - BACKBONE_FROZEN_EPOCHS
    print(f"\n🚀 Phase 2: unfreezing all layers ({remaining} more epochs, {EPOCHS} total)")
    model.backbone.trainable = True
    model.compile(
        optimizer=keras.optimizers.AdamW(
            learning_rate=LEARNING_RATE / 5,   # lower LR for full fine-tuning
            global_clipnorm=GLOBAL_CLIPNORM,
        ),
    )

    checkpoint_dir  = os.path.join(DATA_DIR, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_path = os.path.join(checkpoint_dir, "best.keras")

    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=remaining,
        callbacks=[
            keras.callbacks.ModelCheckpoint(
                checkpoint_path,
                save_best_only=True,
                monitor="val_loss",
                verbose=1,
            ),
            keras.callbacks.EarlyStopping(
                monitor="val_loss",
                patience=5,
                restore_best_weights=True,
                verbose=1,
            ),
        ],
    )

    # Save the final (best) weights
    model.save(checkpoint_path)
    volume.commit()

    print(f"\n✅ Training complete.")
    print(f"   Best model → {checkpoint_path}")
    print(f"   Final train loss : {history.history['loss'][-1]:.4f}")
    print(f"   Final val loss   : {history.history['val_loss'][-1]:.4f}")


# ── Stage 3: Predict ───────────────────────────────────────────────────────
@app.function(
    gpu=TRAIN_GPU,
    volumes={DATA_DIR: volume},
    timeout=600,
)
def predict():
    """Load the best checkpoint and annotate test images with bounding boxes."""
    import os
    os.environ["KERAS_BACKEND"] = "tensorflow"

    import keras
    import keras_hub  # noqa: F401 — registers D-FINE layers for model deserialization
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    print("🔍 Loading model checkpoint from Volume...")
    volume.reload()

    checkpoint_path = os.path.join(DATA_DIR, "checkpoints", "best.keras")
    model = keras.saving.load_model(checkpoint_path)

    test_images  = np.load(os.path.join(DATA_DIR, "test", "images.npy"))
    predictions_dir = os.path.join(DATA_DIR, "predictions")
    os.makedirs(predictions_dir, exist_ok=True)

    # One distinct colour per class
    COLORS = [
        "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
        "#FFEAA7", "#DDA0DD", "#98D8C8", "#F7DC6F",
    ]
    CONF_THRESHOLD = 0.3                               # ← minimum confidence to draw a box
    num_to_save    = min(20, len(test_images))

    print(f"🎯 Running inference on {num_to_save} test images...\n")

    for idx in range(num_to_save):
        batch = test_images[idx : idx + 1]             # shape (1, 640, 640, 3)

        # ── Inference ──
        preds = model.predict(batch, verbose=0)

        # Verified output keys: boxes, confidence, labels, num_detections
        pred_boxes  = preds["boxes"][0]                # (300, 4)  xywh absolute
        pred_conf   = preds["confidence"][0]           # (300,)    float32
        pred_labels = preds["labels"][0]               # (300,)    int32
        n_valid     = int(preds["num_detections"][0])  # how many detections are real

        # ── Draw annotated image ──
        img  = Image.fromarray((batch[0] * 255).astype(np.uint8))
        draw = ImageDraw.Draw(img)

        for det_idx in range(n_valid):
            score  = float(pred_conf[det_idx])
            cls_id = int(pred_labels[det_idx])

            if score < CONF_THRESHOLD:
                continue
            if cls_id < 0 or cls_id >= NUM_CLASSES:
                continue

            x, y, w, h = pred_boxes[det_idx]
            x1, y1, x2, y2 = x, y, x + w, y + h

            color = COLORS[cls_id % len(COLORS)]
            label = f"{CLASS_NAMES[cls_id]} {score:.0%}"

            # Try to use a readable font, fall back to PIL default
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
            except (OSError, IOError):
                font = ImageFont.load_default()

            draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
            text_y = max(0, y1 - 18)                   # clamp so label doesn't clip above image
            draw.rectangle([x1, text_y, x1 + len(label) * 9, text_y + 18], fill=color)
            draw.text((x1 + 4, text_y + 2), label, fill="white", font=font)

        output_path = os.path.join(predictions_dir, f"detection_{idx:03d}.jpg")
        img.save(output_path, quality=95)

    volume.commit()

    print(f"✅ Saved {num_to_save} annotated images to {predictions_dir}/")
    print(f"\n📦 Download results:")
    print(f"   modal volume get {VOLUME_NAME} /root/data/predictions/ .")


# ── Entry Point ────────────────────────────────────────────────────────────
@app.local_entrypoint()
def main():
    """Chain all three pipeline stages: download → train → predict."""
    print("=" * 60)
    print("  Modal + Keras Object Detection — Aquarium (D-FINE)")
    print("=" * 60)

    print("\n📥 Stage 1/3  Downloading dataset...")
    download_dataset.remote()

    print("\n🚀 Stage 2/3  Training model...")
    train.remote()

    print("\n🔍 Stage 3/3  Running predictions...")
    predict.remote()

    print("\n" + "=" * 60)
    print("  ✅ Pipeline complete!")
    print(f"  📦 Download: modal volume get {VOLUME_NAME} /root/data/predictions/ .")
    print("=" * 60)
