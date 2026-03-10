Cart Annotation Tool

A GUI tool for manually labeling cart crop images with **fill level** and **bag status**. Built with Tkinter and Pillow.

## Overview

Each image is labeled in a two-step flow:

1. **Fill Level** — Is the cart empty, partially filled, or full?
2. **Bag Status** — Is the cart bagged or unbagged? *(skipped automatically for empty carts)*

Labels are saved to a CSV file after every annotation. You can quit and resume at any time — already-labeled images are skipped on restart.

## Requirements

```
pip install pillow
```

Tkinter is included with standard Python installations.

## Usage

```bash
python code/label_carts.py --images_dir <path_to_images> --output_csv <path_to_csv>
```

### Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--images_dir` | Yes | — | Directory containing cart crop images (searched recursively) |
| `--output_csv` | No | `dataset/cart_labels.csv` | Path to the output CSV file |
| `--pre_label` | No | `None` | Pre-assign fill level: `empty`, `partial`, or `full` |

### Examples

**Label a folder of images interactively:**
```bash
python code/label_carts.py --images_dir data/cart_crops/ --output_csv labels/cart_labels.csv
```

**Auto-label all images as empty (no GUI interaction needed):**
```bash
python code/label_carts.py --images_dir data/empty_carts/ --output_csv labels/empty_labels.csv --pre_label empty
```

**Label only bag status for a folder known to contain full carts:**
```bash
python code/label_carts.py --images_dir data/full_carts/ --output_csv labels/full_labels.csv --pre_label full
```

## Output CSV Format

```
image_name,fill_level,bag_status
/path/to/cart_001.jpg,empty,not_applicable
/path/to/cart_002.jpg,partial,bagged
/path/to/cart_003.jpg,full,unbagged
```

| Column | Values |
|---|---|
| `image_name` | Full path to the image file |
| `fill_level` | `empty`, `partial`, `full` |
| `bag_status` | `bagged`, `unbagged`, `not_applicable` (for empty carts) |

## Keyboard Shortcuts

### Fill Level (Step 1)

| Key | Action |
|---|---|
| `1` | Empty |
| `2` | Partial |
| `3` | Full |

### Bag Status (Step 2)

| Key | Action |
|---|---|
| `B` | Bagged |
| `U` | Unbagged |

### Navigation

| Key | Action |
|---|---|
| `A` / `Left Arrow` | Previous image (without labeling) |
| `D` / `Right Arrow` | Next image (without labeling) |
| `S` | Skip current image |
| `Z` | Undo last label |
| `Escape` | Back to fill level step |
| `G` / `J` | Jump to a specific image number |
| `Q` | Save and quit |

### Zoom & Pan

| Key / Action | Effect |
|---|---|
| `+` / `=` | Zoom in |
| `-` / `_` | Zoom out |
| `0` | Reset zoom to fit |
| `Scroll wheel` | Zoom in/out |
| `Right-drag` | Pan image |
| `Middle-drag` | Pan image |

## Workflow

### Normal labeling

1. The tool loads all images from `--images_dir` and skips any already present in the CSV.
2. For each image:
   - **Step 1:** Press `1`, `2`, or `3` to set fill level.
   - If `partial` or `full`: **Step 2** appears — press `B` or `U` for bag status.
   - If `empty`: bag status is set to `not_applicable` automatically.
3. Label is saved immediately and the next image is shown.

### Pre-label mode

- `--pre_label empty`: Instantly auto-labels all unlabeled images as `empty / not_applicable`. No manual input needed.
- `--pre_label partial` or `--pre_label full`: Skips Step 1 and goes straight to bag status for every image.

### Resuming

Simply re-run with the same `--output_csv` path. Already-labeled images are detected and skipped.

### Undo

Press `Z` to undo the last saved label. The tool returns to that image so you can re-label it.

## Supported Image Formats

`.jpg`, `.jpeg`, `.png`, `.bmp`

Images are discovered recursively within `--images_dir`.
