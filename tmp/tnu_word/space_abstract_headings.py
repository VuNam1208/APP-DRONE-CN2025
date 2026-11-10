from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

path = 'Bai_bao/main_TNU.docx'
doc = Document(path)
before = [node.text for node in doc.element.iter(qn('w:t'))]
for table in doc.tables[:2]:
    for tc in table.rows[3]._tr.findall(qn('w:tc')):
        pr = tc.get_or_add_tcPr()
        margins = pr.find(qn('w:tcMar'))
        if margins is None:
            margins = OxmlElement('w:tcMar')
            pr.append(margins)
        for edge in ('top', 'bottom'):
            node = margins.find(qn('w:' + edge))
            if node is None:
                node = OxmlElement('w:' + edge)
                margins.append(node)
            node.set(qn('w:w'), '60')
            node.set(qn('w:type'), 'dxa')
assert before == [node.text for node in doc.element.iter(qn('w:t'))]
doc.save(path)
print('Added 3 pt top/bottom padding to both abstract heading rows; text unchanged.')
