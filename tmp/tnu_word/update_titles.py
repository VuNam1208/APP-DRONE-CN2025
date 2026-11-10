from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor

root = Path(__file__).resolve().parents[2]
path = root / 'Bai_bao/main_TNU.docx'
doc = Document(path)
titles = [
    'A METHOD FOR FLIGHT-ROUTE REALLOCATION\nIN MULTI-UAV SYSTEMS FOLLOWING A FAILURE',
    'PHƯƠNG PHÁP ĐIỀU PHỐI LẠI TUYẾN BAY\nCHO HỆ THỐNG ĐA UAV KHI XẢY RA SỰ CỐ',
]
for table, title in zip(doc.tables[:2], titles):
    cell = table.rows[0].cells[0]
    p = cell.paragraphs[0]
    p.clear()
    run = p.add_run(title)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(12)
    run.bold = True
    run.font.color.rgb = RGBColor(0, 0, 0)
doc.save(path)
print('Updated Vietnamese and English titles only')
