"""Crop real app captures and compose the report's four-panel Figure 2."""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont, ImageOps


def font(size: int, bold: bool = False):
    name = "arialbd.ttf" if bold else "arial.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def main() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    source = os.path.join(root, "results", "report_app_captures")
    map_crop = (580, 70, 1460, 660)
    panels = [
        ("b0_initial.png", map_crop, "(a) Nhiệm vụ ban đầu"),
        ("b0_failure.png", map_crop, "(b) UAV 2 mất liên lạc tại 20%"),
        ("b1_replan.png", map_crop, "(c) B1: 2 -> 2 xung đột"),
        ("proposed_replan.png", map_crop, "(d) Đề xuất: 2 -> 0 xung đột"),
    ]
    cell_w, cell_h, header_h, gap = 1180, 790, 62, 24
    canvas = Image.new(
        "RGB", (cell_w * 2 + gap, (cell_h + header_h) * 2 + gap), "white"
    )
    draw = ImageDraw.Draw(canvas)
    title_font = font(30, bold=True)
    for index, (filename, crop, title) in enumerate(panels):
        image = Image.open(os.path.join(source, filename)).convert("RGB").crop(crop)
        image = ImageOps.fit(image, (cell_w, cell_h), method=Image.Resampling.LANCZOS)
        column, row = index % 2, index // 2
        x = column * (cell_w + gap)
        y = row * (cell_h + header_h + gap)
        draw.text((x + 12, y + 12), title, fill="#111827", font=title_font)
        canvas.paste(image, (x, y + header_h))
        draw.rectangle(
            (x, y + header_h, x + cell_w - 1, y + header_h + cell_h - 1),
            outline="#475569", width=2,
        )
    output = os.path.join(root, "Bai_bao", "figures", "fig2_app_trajectory.png")
    canvas.save(output, quality=95, dpi=(240, 240))
    print(os.path.relpath(output, root))


if __name__ == "__main__":
    main()
