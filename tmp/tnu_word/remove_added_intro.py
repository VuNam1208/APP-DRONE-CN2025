from docx import Document

path = 'Bai_bao/main_TNU.docx'
doc = Document(path)
text = ('Bàn giao tuyến đang thực hiện cần xét cấu trúc đường bay, không chỉ số điểm còn lại. '
        'Do đó, bảo toàn tuyến cần được đánh giá cùng quãng nối, cân bằng tải và phân tách UAV.')
matches = [p for p in doc.paragraphs if p.text == text]
assert len(matches) == 1
p = matches[0]._p
p.getparent().remove(p)
doc.save(path)
print('Removed only the newly added paragraph.')
