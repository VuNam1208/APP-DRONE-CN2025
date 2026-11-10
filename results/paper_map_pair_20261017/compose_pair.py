"""Crop and join app screenshots; leave the captured map pixels unchanged."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CROP = (815, 115, 1225, 600)
PANELS = [
    ('pair_initial.png', '(a) Kế hoạch ban đầu'),
    ('pair_replan.png', '(b) Sau bàn giao'),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-dir', default='.')
    args = parser.parse_args()
    source_dir = HERE / args.source_dir
    width, height = CROP[2] - CROP[0], CROP[3] - CROP[1]
    gap, heading = 24, 28
    figure = Image.new('RGB', (2 * width + gap, height + heading), 'white')
    draw = ImageDraw.Draw(figure)
    font = ImageFont.truetype('C:/Windows/Fonts/times.ttf', 22)
    checksums = {}
    for index, (filename, label) in enumerate(PANELS):
        source = source_dir / filename
        image = Image.open(source).convert('RGB').crop(CROP)
        x = index * (width + gap)
        figure.paste(image, (x, heading))
        draw.text((x + width / 2, 4), label, font=font, fill='black', anchor='mt')
        checksums[filename] = hashlib.sha256(source.read_bytes()).hexdigest()
    output = ROOT / 'Bai_bao/figures/fig2_app_map_pair.png'
    figure.save(output, dpi=(160, 160))
    (source_dir / 'composition.json').write_text(json.dumps({
        'sources_sha256': checksums, 'identical_crop_px': CROP,
        'output': str(output.relative_to(ROOT)),
        'processing': 'Identical crop, side-by-side paste and panel labels; map attribution is in the paper footnote. No map retouching.',
    }, indent=2), encoding='utf-8')
    print(output.relative_to(ROOT))


if __name__ == '__main__':
    main()
