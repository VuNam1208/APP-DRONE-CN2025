from docx import Document

path = 'Bai_bao/main_TNU.docx'
doc = Document(path)
matches = [p for p in doc.paragraphs if p.text.startswith('Luna và cộng sự')]
assert len(matches) == 1
p = matches[0]
old = 'Luna và cộng sự\u00a0[13] gộp điểm chưa quan sát thành tuyến chung để phân phối lại trong chuyến bay, có kiểm chứng bay thực.'
new = 'Phương pháp lập kế hoạch lại trong chuyến bay ở\u00a0[13] gộp các điểm chưa quan sát thành tuyến chung để phân phối lại và đã được kiểm chứng bằng bay thực.'
assert p.text.startswith(old), p.text
replacement = p.text.replace(old, new, 1)
for r in p.runs:
    r.text = ''
p.runs[0].text = replacement
doc.save(path)
print('Updated one introduction paragraph; other content preserved.')
