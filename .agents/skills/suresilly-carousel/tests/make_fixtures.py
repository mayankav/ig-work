#!/usr/bin/env python3
"""
Regenerates the contaminated-cutout fixtures by reproducing the ORIGINAL defect:
slice a labelled sprite-sheet cell, drop the near-uniform paper background, and
keep whatever is left — which includes the printed caption ("2. Thinking").

These fixtures are the real-world regression evidence for tests/test_qa_gates.py.
"""
import pathlib
import cv2
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
SHEETS = HERE.parent / "mascot" / "style_refs"
OUT = HERE / "fixtures" / "contaminated"
CELLS = {("silly_sheet_2_emotions.jpg", 1): "thinking",
         ("silly_sheet_2_emotions.jpg", 4): "determined",
         ("silly_sheet_3_activities.jpg", 4): "reader"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for (sheet, idx), name in CELLS.items():
        im = cv2.imread(str(SHEETS / sheet))
        h, w = im.shape[:2]
        cw, ch = w // 3, h // 2
        col, row = idx % 3, idx // 3
        cell = im[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw]

        # the old approach: everything close to the paper colour becomes transparent
        corners = np.array([cell[0, 0], cell[0, -1], cell[-1, 0], cell[-1, -1]], np.int16)
        bg = corners.mean(0)
        near = (np.abs(cell.astype(np.int16) - bg).max(2) <= 12).astype(np.uint8) * 255
        alpha = 255 - near
        rgba = np.dstack([cell, alpha])
        ys, xs = np.where(alpha > 20)
        rgba = rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        cv2.imwrite(str(OUT / f"{name}.png"), rgba)
        print(f"  wrote {name}.png {rgba.shape[1]}x{rgba.shape[0]}")


if __name__ == "__main__":
    main()
