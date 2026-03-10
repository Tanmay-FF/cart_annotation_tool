"""
Cart Annotation Tool - GUI labeling for fill level + bag status.

Usage:
    python label_carts.py --images_dir <path_to_images> --output_csv <path_to_csv>

Keyboard shortcuts:
    Fill Level:  1=Empty  2=Partial  3=Full
    Bag Status:  B=Bagged  U=Unbagged
    Navigation:  A/Left=Prev  D/Right=Next  S=Skip  Z=Undo  Q=Quit  Escape=Back
    Zoom:        +/= Zoom in   -/_ Zoom out   0 Reset zoom   Scroll=Zoom
    Jump:        G or J to open jump-to-image dialog

Progress auto-saves after every label. Resume anytime.
"""

import tkinter as tk
from tkinter import ttk, simpledialog
from PIL import Image, ImageTk
import csv
import os
import argparse
from pathlib import Path
from collections import OrderedDict


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_existing_labels(csv_path):
    labels = OrderedDict()
    if os.path.exists(csv_path):
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                labels[row['image_name']] = {
                    'fill_level': row['fill_level'],
                    'bag_status': row['bag_status'],
                }
    return labels


def save_labels(csv_path, labels):
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['image_name', 'fill_level', 'bag_status'])
        writer.writeheader()
        for image_name, label_data in labels.items():
            writer.writerow({
                'image_name': image_name,
                'fill_level': label_data['fill_level'],
                'bag_status': label_data['bag_status'],
            })


def collect_images(images_dir):
    extensions = {'.jpg', '.jpeg', '.png', '.bmp'}
    images = []
    for root, _, files in os.walk(images_dir):
        for f in sorted(files):
            if Path(f).suffix.lower() in extensions:
                images.append(os.path.join(root, f))
    return sorted(images)


# ---------------------------------------------------------------------------
# Colors (Catppuccin Mocha)
# ---------------------------------------------------------------------------
BG           = '#1e1e2e'
BG_DARK      = '#181825'
FG           = '#cdd6f4'
FG_DIM       = '#6c7086'
ACCENT       = '#89b4fa'
GREEN        = '#a6e3a1'
YELLOW       = '#f9e2af'
RED          = '#f38ba8'
PEACH        = '#fab387'
MAUVE        = '#cba6f7'
BTN_BG       = '#313244'
BTN_ACTIVE   = '#45475a'
SURFACE      = '#313244'


# ---------------------------------------------------------------------------
# GUI Application
# ---------------------------------------------------------------------------

class CartLabelerApp:
    ZOOM_LEVELS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]

    def __init__(self, root, images_dir, output_csv, pre_label=None):
        self.root = root
        self.output_csv = output_csv
        self.pre_label = pre_label

        # Data
        self.labels = load_existing_labels(output_csv)
        all_images = collect_images(images_dir)
        labeled_set = set(self.labels.keys())
        self.unlabeled = [p for p in all_images if p not in labeled_set]
        self.total_images = len(all_images)
        self.history = []
        self.idx = 0

        # State
        self.stage = 'fill'
        self.fill_label = None

        # Zoom / pan state
        self._zoom_idx = 3           # index into ZOOM_LEVELS, default 1.0 (fit)
        self._fit_mode = True        # True = auto-fit to canvas
        self._pan_x = 0              # pan offset in image coords
        self._pan_y = 0
        self._drag_start = None      # for mouse drag panning
        self._current_pil = None
        self._photo = None

        # Window setup
        self.root.title("Cart Labeler")
        self.root.configure(bg=BG)
        self.root.geometry("1100x800")
        self.root.minsize(800, 600)

        self._build_ui()
        self._bind_keys()

        # Handle pre_label for empty (fully auto)
        if self.pre_label == 'empty':
            self._auto_label_all_empty()
            return

        if not self.unlabeled:
            self.status_var.set("All images already labeled!")
            return

        if self.pre_label in ('partial', 'full'):
            self.fill_label = self.pre_label
            self.stage = 'bag'

        self._show_current()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self):
        # --- Top bar: progress + jump ---
        top = tk.Frame(self.root, bg=BG_DARK, pady=8, padx=12)
        top.pack(fill='x')

        self.progress_var = tk.StringVar(value="Loading...")
        tk.Label(top, textvariable=self.progress_var, font=('Segoe UI', 11, 'bold'),
                 bg=BG_DARK, fg=FG).pack(side='left')

        # Jump button
        jump_btn = tk.Button(top, text="Jump (G)", font=('Segoe UI', 9),
                             bg=BTN_BG, fg=ACCENT, activebackground=BTN_ACTIVE,
                             relief='flat', padx=8, pady=2, cursor='hand2',
                             command=self._on_jump)
        jump_btn.pack(side='left', padx=(15, 5))

        self.filename_var = tk.StringVar()
        tk.Label(top, textvariable=self.filename_var, font=('Segoe UI', 9),
                 bg=BG_DARK, fg=FG_DIM).pack(side='right')

        # Progress bar
        style = ttk.Style()
        style.theme_use('default')
        style.configure('green.Horizontal.TProgressbar',
                        troughcolor=BTN_BG, background=GREEN, thickness=6)
        self.progressbar = ttk.Progressbar(self.root, style='green.Horizontal.TProgressbar',
                                           maximum=max(self.total_images, 1))
        self.progressbar.pack(fill='x', padx=0)

        # --- Center: image canvas with scrollbars ---
        canvas_frame = tk.Frame(self.root, bg=BG)
        canvas_frame.pack(fill='both', expand=True, padx=10, pady=(10, 5))

        self.canvas = tk.Canvas(canvas_frame, bg=BG, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self._redraw_image())

        # Mouse zoom & pan
        self.canvas.bind('<MouseWheel>', self._on_mousewheel)         # Windows scroll
        self.canvas.bind('<Button-4>', self._on_mousewheel)           # Linux scroll up
        self.canvas.bind('<Button-5>', self._on_mousewheel)           # Linux scroll down
        self.canvas.bind('<ButtonPress-2>', self._on_pan_start)       # Middle-click drag
        self.canvas.bind('<B2-Motion>', self._on_pan_drag)
        self.canvas.bind('<ButtonPress-3>', self._on_pan_start)       # Right-click drag
        self.canvas.bind('<B3-Motion>', self._on_pan_drag)

        # --- Zoom controls bar ---
        zoom_bar = tk.Frame(self.root, bg=BG)
        zoom_bar.pack(fill='x', padx=20, pady=(0, 3))

        self.zoom_var = tk.StringVar(value="Fit")
        tk.Label(zoom_bar, text="Zoom:", font=('Segoe UI', 9),
                 bg=BG, fg=FG_DIM).pack(side='left')

        for text, cmd in [("-", self._zoom_out), ("Fit", self._zoom_reset), ("+", self._zoom_in)]:
            btn = tk.Button(zoom_bar, text=text, font=('Segoe UI', 10, 'bold'),
                            bg=BTN_BG, fg=FG, activebackground=BTN_ACTIVE,
                            relief='flat', width=4, cursor='hand2', command=cmd)
            btn.pack(side='left', padx=2)

        tk.Label(zoom_bar, textvariable=self.zoom_var, font=('Segoe UI', 9),
                 bg=BG, fg=ACCENT, width=8).pack(side='left', padx=(6, 0))

        # Hint
        tk.Label(zoom_bar, text="Scroll=Zoom  |  Right-drag=Pan  |  Middle-drag=Pan",
                 font=('Segoe UI', 8), bg=BG, fg=FG_DIM).pack(side='right')

        # --- Stage indicator ---
        self.stage_var = tk.StringVar(value="")
        self.stage_label = tk.Label(self.root, textvariable=self.stage_var,
                                    font=('Segoe UI', 13, 'bold'), bg=BG, fg=ACCENT)
        self.stage_label.pack(pady=(0, 5))

        # --- Button panel ---
        self.btn_frame = tk.Frame(self.root, bg=BG)
        self.btn_frame.pack(fill='x', padx=20, pady=(0, 5))

        # Fill-level buttons
        self.fill_frame = tk.Frame(self.btn_frame, bg=BG)
        self.fill_buttons = {}
        fill_config = [
            ('1  EMPTY',       'empty',       GREEN),
            ('2  PARTIAL',     'partial',     YELLOW),
            ('3  FULL',        'full',        PEACH),
        ]
        for text, value, color in fill_config:
            btn = tk.Button(self.fill_frame, text=text, font=('Segoe UI', 11, 'bold'),
                            bg=BTN_BG, fg=color, activebackground=BTN_ACTIVE, activeforeground=color,
                            relief='flat', padx=18, pady=8, cursor='hand2',
                            command=lambda v=value: self._on_fill(v))
            btn.pack(side='left', padx=4, expand=True, fill='x')
            self.fill_buttons[value] = btn

        # Bag-status buttons
        self.bag_frame = tk.Frame(self.btn_frame, bg=BG)
        self.bag_buttons = {}
        bag_config = [
            ('B  BAGGED',   'bagged',   MAUVE),
            ('U  UNBAGGED', 'unbagged', RED),
        ]
        for text, value, color in bag_config:
            btn = tk.Button(self.bag_frame, text=text, font=('Segoe UI', 12, 'bold'),
                            bg=BTN_BG, fg=color, activebackground=BTN_ACTIVE, activeforeground=color,
                            relief='flat', padx=30, pady=10, cursor='hand2',
                            command=lambda v=value: self._on_bag(v))
            btn.pack(side='left', padx=6, expand=True, fill='x')
            self.bag_buttons[value] = btn

        # --- Bottom bar: nav buttons + status ---
        bottom = tk.Frame(self.root, bg=BG_DARK, pady=6, padx=12)
        bottom.pack(fill='x', side='bottom')

        nav_btns = [
            ('<< Prev (A)', self._on_prev, FG),
            ('Next (D) >>', self._on_next, FG),
            ('Undo (Z)',    self._on_undo, FG_DIM),
            ('Skip (S)',    self._on_skip, FG_DIM),
            ('Back (Esc)',  self._on_back, YELLOW),
            ('Jump (G)',    self._on_jump, ACCENT),
            ('Quit (Q)',    self._on_quit, RED),
        ]
        for text, cmd, color in nav_btns:
            btn = tk.Button(bottom, text=text, font=('Segoe UI', 9),
                            bg=BTN_BG, fg=color, activebackground=BTN_ACTIVE,
                            relief='flat', padx=10, pady=3, cursor='hand2', command=cmd)
            btn.pack(side='left', padx=3)

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(bottom, textvariable=self.status_var, font=('Segoe UI', 9),
                 bg=BG_DARK, fg=FG_DIM).pack(side='right')

    def _bind_keys(self):
        # Fill level
        self.root.bind('1', lambda e: self._on_fill('empty'))
        self.root.bind('2', lambda e: self._on_fill('partial'))
        self.root.bind('3', lambda e: self._on_fill('full'))
        # Bag status
        self.root.bind('b', lambda e: self._on_bag('bagged'))
        self.root.bind('B', lambda e: self._on_bag('bagged'))
        self.root.bind('u', lambda e: self._on_bag('unbagged'))
        self.root.bind('U', lambda e: self._on_bag('unbagged'))
        # Navigation
        self.root.bind('s', lambda e: self._on_skip())
        self.root.bind('S', lambda e: self._on_skip())
        self.root.bind('z', lambda e: self._on_undo())
        self.root.bind('Z', lambda e: self._on_undo())
        self.root.bind('q', lambda e: self._on_quit())
        self.root.bind('Q', lambda e: self._on_quit())
        self.root.bind('<Escape>', lambda e: self._on_back())
        # Jump
        self.root.bind('g', lambda e: self._on_jump())
        self.root.bind('G', lambda e: self._on_jump())
        self.root.bind('j', lambda e: self._on_jump())
        self.root.bind('J', lambda e: self._on_jump())
        # Prev / Next (without labeling)
        self.root.bind('a', lambda e: self._on_prev())
        self.root.bind('A', lambda e: self._on_prev())
        self.root.bind('d', lambda e: self._on_next())
        self.root.bind('D', lambda e: self._on_next())
        self.root.bind('<Left>', lambda e: self._on_prev())
        self.root.bind('<Right>', lambda e: self._on_next())
        # Zoom
        self.root.bind('<plus>', lambda e: self._zoom_in())
        self.root.bind('<equal>', lambda e: self._zoom_in())
        self.root.bind('<minus>', lambda e: self._zoom_out())
        self.root.bind('<underscore>', lambda e: self._zoom_out())
        self.root.bind('0', lambda e: self._zoom_reset())

    # -----------------------------------------------------------------------
    # Zoom & Pan
    # -----------------------------------------------------------------------

    def _zoom_in(self):
        if self._fit_mode:
            self._fit_mode = False
            self._zoom_idx = 3  # start at 1.0x
        if self._zoom_idx < len(self.ZOOM_LEVELS) - 1:
            self._zoom_idx += 1
        self._update_zoom_label()
        self._redraw_image()

    def _zoom_out(self):
        if self._fit_mode:
            self._fit_mode = False
            self._zoom_idx = 3
        if self._zoom_idx > 0:
            self._zoom_idx -= 1
        self._update_zoom_label()
        self._redraw_image()

    def _zoom_reset(self):
        self._fit_mode = True
        self._pan_x = 0
        self._pan_y = 0
        self._zoom_idx = 3
        self._update_zoom_label()
        self._redraw_image()

    def _update_zoom_label(self):
        if self._fit_mode:
            self.zoom_var.set("Fit")
        else:
            pct = int(self.ZOOM_LEVELS[self._zoom_idx] * 100)
            self.zoom_var.set(f"{pct}%")

    def _on_mousewheel(self, event):
        # Scroll up = zoom in, scroll down = zoom out
        if event.num == 4 or (hasattr(event, 'delta') and event.delta > 0):
            self._zoom_in()
        elif event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
            self._zoom_out()

    def _on_pan_start(self, event):
        self._drag_start = (event.x, event.y)

    def _on_pan_drag(self, event):
        if self._drag_start is None or self._fit_mode:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        self._drag_start = (event.x, event.y)
        self._pan_x += dx
        self._pan_y += dy
        self._redraw_image()

    # -----------------------------------------------------------------------
    # Display
    # -----------------------------------------------------------------------

    def _show_current(self):
        if self.idx >= len(self.unlabeled):
            save_labels(self.output_csv, self.labels)
            self.stage_var.set("ALL DONE!")
            self.status_var.set(f"Labeled {len(self.labels)} images total. Saved to {self.output_csv}")
            self._current_pil = None
            self.canvas.delete('all')
            self.fill_frame.pack_forget()
            self.bag_frame.pack_forget()
            return

        img_path = self.unlabeled[self.idx]
        img_name = os.path.basename(img_path)

        # Update info
        labeled_count = len(self.labels)
        remaining = len(self.unlabeled) - self.idx
        self.progress_var.set(f"  {self.idx + 1} / {len(self.unlabeled)}  |  "
                              f"Labeled: {labeled_count}  |  Remaining: {remaining}")
        self.filename_var.set(img_name)
        self.progressbar['value'] = labeled_count

        # Load image
        try:
            self._current_pil = Image.open(img_path)
        except Exception as e:
            print(f"Could not open {img_path}: {e}")
            self.idx += 1
            self._show_current()
            return

        # Reset zoom/pan for new image
        self._fit_mode = True
        self._pan_x = 0
        self._pan_y = 0
        self._update_zoom_label()

        self._redraw_image()
        self._update_stage_ui()

    def _redraw_image(self):
        if self._current_pil is None:
            return
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        iw, ih = self._current_pil.size

        if self._fit_mode:
            # Fit entire image to canvas
            scale = min(cw / iw, ch / ih)
            new_w = int(iw * scale)
            new_h = int(ih * scale)
            img = self._current_pil.resize((new_w, new_h), Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            self.canvas.delete('all')
            self.canvas.create_image(cw // 2, ch // 2, anchor='center', image=self._photo)
        else:
            # Manual zoom level
            zoom = self.ZOOM_LEVELS[self._zoom_idx]
            new_w = int(iw * zoom)
            new_h = int(ih * zoom)
            img = self._current_pil.resize((new_w, new_h), Image.LANCZOS)

            # Center + pan offset
            cx = cw // 2 + self._pan_x
            cy = ch // 2 + self._pan_y

            self._photo = ImageTk.PhotoImage(img)
            self.canvas.delete('all')
            self.canvas.create_image(cx, cy, anchor='center', image=self._photo)

    def _update_stage_ui(self):
        if self.stage == 'fill':
            self.stage_var.set("Step 1: Select FILL LEVEL")
            self.stage_label.configure(fg=ACCENT)
            self.bag_frame.pack_forget()
            self.fill_frame.pack(fill='x')
        elif self.stage == 'bag':
            fill_display = self.fill_label.upper() if self.fill_label else '?'
            self.stage_var.set(f"Fill: {fill_display}  ->  Step 2: Select BAG STATUS")
            self.stage_label.configure(fg=GREEN)
            self.fill_frame.pack_forget()
            self.bag_frame.pack(fill='x')

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _on_fill(self, value):
        if self.stage != 'fill':
            return
        if self.idx >= len(self.unlabeled):
            return
        self.fill_label = value
        if value == 'empty':
            self._commit_label(value, 'not_applicable')
        else:
            self.stage = 'bag'
            self._update_stage_ui()

    def _on_bag(self, value):
        if self.stage != 'bag':
            return
        if self.idx >= len(self.unlabeled):
            return
        self._commit_label(self.fill_label, value)

    def _commit_label(self, fill, bag):
        img_name = self.unlabeled[self.idx]
        self.labels[img_name] = {'fill_level': fill, 'bag_status': bag}
        self.history.append(img_name)
        save_labels(self.output_csv, self.labels)
        self.status_var.set(f"Labeled: {fill} / {bag}")

        # Reset stage and advance
        self.idx += 1
        if self.pre_label in ('partial', 'full'):
            self.fill_label = self.pre_label
            self.stage = 'bag'
        else:
            self.stage = 'fill'
            self.fill_label = None
        self._show_current()

    def _on_prev(self):
        """Go to previous image without labeling (A / Left arrow)."""
        if self.idx <= 0:
            self.status_var.set("Already at the first image")
            return
        self.idx -= 1
        if self.pre_label in ('partial', 'full'):
            self.fill_label = self.pre_label
            self.stage = 'bag'
        else:
            self.stage = 'fill'
            self.fill_label = None
        self.status_var.set(f"<< Image {self.idx + 1}")
        self._show_current()

    def _on_next(self):
        """Go to next image without labeling (D / Right arrow)."""
        if self.idx >= len(self.unlabeled) - 1:
            self.status_var.set("Already at the last image")
            return
        self.idx += 1
        if self.pre_label in ('partial', 'full'):
            self.fill_label = self.pre_label
            self.stage = 'bag'
        else:
            self.stage = 'fill'
            self.fill_label = None
        self.status_var.set(f">> Image {self.idx + 1}")
        self._show_current()

    def _on_skip(self):
        if self.idx >= len(self.unlabeled):
            return
        self.status_var.set("Skipped")
        self.idx += 1
        if self.pre_label in ('partial', 'full'):
            self.fill_label = self.pre_label
            self.stage = 'bag'
        else:
            self.stage = 'fill'
            self.fill_label = None
        self._show_current()

    def _on_undo(self):
        if not self.history:
            self.status_var.set("Nothing to undo")
            return
        last = self.history.pop()
        del self.labels[last]
        save_labels(self.output_csv, self.labels)
        for j, p in enumerate(self.unlabeled):
            if p == last:
                self.idx = j
                break
        if self.pre_label in ('partial', 'full'):
            self.fill_label = self.pre_label
            self.stage = 'bag'
        else:
            self.stage = 'fill'
            self.fill_label = None
        self.status_var.set(f"Undid: {last}")
        self._show_current()

    def _on_back(self):
        if self.stage == 'bag' and not self.pre_label:
            self.stage = 'fill'
            self.fill_label = None
            self._update_stage_ui()
            self.status_var.set("Back to fill level")
        elif self.pre_label:
            self.status_var.set("Cannot go back (pre-label active)")

    def _on_jump(self):
        """Open a dialog to jump to a specific image number."""
        total = len(self.unlabeled)
        if total == 0:
            return
        result = simpledialog.askinteger(
            "Jump to Image",
            f"Enter image number (1 - {total}):",
            parent=self.root,
            minvalue=1,
            maxvalue=total,
            initialvalue=self.idx + 1,
        )
        if result is not None:
            self.idx = result - 1
            if self.pre_label in ('partial', 'full'):
                self.fill_label = self.pre_label
                self.stage = 'bag'
            else:
                self.stage = 'fill'
                self.fill_label = None
            self.status_var.set(f"Jumped to image {result}")
            self._show_current()

    def _on_quit(self):
        save_labels(self.output_csv, self.labels)
        print(f"Saved {len(self.labels)} labels to {self.output_csv}")
        self.root.destroy()

    def _auto_label_all_empty(self):
        count = 0
        for img_path in self.unlabeled:
            self.labels[img_path] = {'fill_level': 'empty', 'bag_status': 'not_applicable'}
            count += 1
        save_labels(self.output_csv, self.labels)
        self.progress_var.set(f"Auto-labeled {count} images as EMPTY")
        self.progressbar['value'] = len(self.labels)
        self.status_var.set(f"Done! Total: {len(self.labels)} labels in {self.output_csv}")
        self.stage_var.set("ALL DONE - Auto-labeled EMPTY")
        print(f"Auto-labeled {count} empty images. Total: {len(self.labels)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Cart annotation tool for fill level + bag status')
    parser.add_argument('--images_dir', required=True,
                        help='Directory containing cart crop images (searched recursively)')
    parser.add_argument('--output_csv', default='dataset/cart_labels.csv',
                        help='Output CSV path (default: dataset/cart_labels.csv)')
    parser.add_argument('--pre_label', default=None,
                        choices=['empty', 'partial', 'full'],
                        help='Pre-assign fill level (skip fill step, only ask bag status)')
    args = parser.parse_args()

    root = tk.Tk()
    app = CartLabelerApp(root, args.images_dir, args.output_csv, args.pre_label)
    root.mainloop()


if __name__ == '__main__':
    main()
