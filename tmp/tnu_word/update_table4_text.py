from copy import deepcopy
from pathlib import Path
import sys

from docx import Document
from docx.shared import Pt

root = Path(__file__).resolve().parents[2]
tmp = Path.home() / 'AppData/Local/Temp/drone-word-tnu-20261018'
target = root / 'Bai_bao/main_TNU.docx'
if sys.argv[1] == 'prepare':
    source = (root / 'Bai_bao/main.tex').read_text(encoding='utf-8')
    text = next(line for line in source.splitlines() if line.startswith(r'Bảng~\ref{tab:caa-sensitivity} cho thấy'))
    text = text.replace(r'\ref{tab:caa-sensitivity}', '4')
    (tmp / 'table4-paragraph.tex').write_text(text, encoding='utf-8')
else:
    doc = Document(target)
    old = [p for p in doc.paragraphs if p.text.startswith(('Với ngưỡng ngang ', 'Với ngưỡng đứng '))]
    assert len(old) == 2, 'Expected exactly two paragraphs to replace'
    replacement = Document(tmp / 'table4-paragraph.docx')
    assert len(replacement.paragraphs) == 1
    old[0].clear()
    for child in replacement.paragraphs[0]._p:
        if not child.tag.endswith('}pPr'):
            old[0]._p.append(deepcopy(child))
    for run in old[0].runs:
        run.font.name = 'Times New Roman'
        run.font.size = Pt(11)
    old[1]._p.getparent().remove(old[1]._p)
    doc.save(target)
    print('Updated only the two Table 4 interpretation paragraphs in Word')
