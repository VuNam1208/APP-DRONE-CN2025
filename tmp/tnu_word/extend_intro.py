from docx import Document

path = 'Bai_bao/main_TNU.docx'
doc = Document(path)
matches = [p for p in doc.paragraphs if p.text.startswith('Bàn giao tuyến đang thực hiện cần xét cả')]
assert len(matches) == 1
p = matches[0]
text = ('Bàn giao tuyến đang thực hiện cần xét cấu trúc đường bay, không chỉ số điểm còn lại. '
        'Do đó, bảo toàn tuyến cần được đánh giá cùng quãng nối, cân bằng tải và phân tách UAV.')
assert not any(q.text == text for q in doc.paragraphs)
for run in p.runs:
    run.text = ''
p.runs[0].text = text
doc.save(path)
print('Added one introduction paragraph.')
