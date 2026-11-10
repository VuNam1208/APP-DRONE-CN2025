from pathlib import Path
from copy import deepcopy
from io import BytesIO
import hashlib
import json
import re
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, Inches
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
TMP = Path.home() / 'AppData/Local/Temp/drone-word-tnu-20261018'
REF = ROOT / 'Bai_bao/TNU_JST_Template_VI_2021.docx'
OUT = ROOT / 'Bai_bao/main_TNU.docx'
SOURCE = (ROOT / 'Bai_bao/main.tex').read_text(encoding='utf-8')
PANDOC = TMP / 'pandoc/pandoc-3.6.4/pandoc.exe'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}


def command_replace(text, name, transform):
    pattern = re.compile(r'\\' + name + r'\s*\{')
    start = 0
    while match := pattern.search(text, start):
        depth, end = 1, match.end()
        while depth:
            if text[end] == '{' and text[end - 1] != '\\':
                depth += 1
            elif text[end] == '}' and text[end - 1] != '\\':
                depth -= 1
            end += 1
        replacement = transform(text[match.end():end - 1])
        text = text[:match.start()] + replacement + text[end:]
        start = match.start() + len(replacement)
    return text


def plain(text):
    return text.replace(r'\%', '%').replace(r'\newline', '\n').strip()


def clean_table(path):
    text = path.read_text(encoding='utf-8')
    text = command_replace(text, 'shortstack', lambda s: s.replace(r'\\', ' '))
    text = command_replace(text, 'tnutablehead', lambda s: r'\textbf{' + s + '}')
    rows = [s.strip() for s in text.splitlines() if '&' in s and s.rstrip().endswith(r'\\')]
    columns = rows[0].count('&') + 1
    return '\\begin{tabular}{' + 'l' * columns + '}\n' + '\n'.join(rows) + '\n\\end{tabular}'


def prepare():
    assert hashlib.sha256(REF.read_bytes()).hexdigest().upper() == '67F53F54D77FF0947976642E67385FB6F7041FB8F81943EE4CB57E8E8EEB7F27'
    TMP.mkdir(parents=True, exist_ok=True)
    tikz = re.search(r'\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}', SOURCE, re.S).group()
    pipeline = r'''\documentclass{article}
\usepackage[paperwidth=154mm,paperheight=15mm,margin=1mm]{geometry}
\usepackage{fontspec}\setmainfont{Times New Roman}
\usepackage{tikz}\usetikzlibrary{arrows.meta,positioning}
\pagestyle{empty}\setlength{\parindent}{0pt}
\begin{document}\centering
''' + tikz + '\n\\end{document}\n'
    (TMP / 'pipeline.tex').write_text(pipeline, encoding='utf-8')
    body = SOURCE[SOURCE.index(r'\section{Giới thiệu}'):]
    body = re.sub(r'(?<!\\)%[^\n]*', '', body)
    labels = {'fig:pipeline': '1', 'fig:app-map-pair': '2',
              'tab:assignment-ablation': '1', 'tab:geometry': '2',
              'tab:independent': '3', 'tab:caa-sensitivity': '4',
              'eq:assignment': '5', 'eq:operational-length': '3', 'eq:recovery-ratio': '6'}
    body = re.sub(r'\\eqref\{([^}]+)\}', lambda m: '(' + labels[m[1]] + ')', body)
    body = re.sub(r'\\ref\{([^}]+)\}', lambda m: labels[m[1]], body)
    bbl = (Path.home() / 'AppData/Local/Temp/drone-paper-revision2-20261008/main.bbl').read_text(encoding='utf-8')
    keys = re.findall(r'\\bibitem\{([^}]+)\}', bbl)
    body = re.sub(r'\\cite\{([^}]+)\}', lambda m: ', '.join('[' + str(keys.index(k) + 1) + ']' for k in m[1].split(',')), body)
    body = re.sub(r'\\label\{[^}]+\}', '', body)
    section, subsection = 0, 0

    def heading(m):
        nonlocal section, subsection
        if m[1] == 'section':
            section += 1
            subsection = 0
            return r'\section{' + str(section) + '. ' + m[2] + '}'
        subsection += 1
        return r'\subsection{' + f'{section}.{subsection}. ' + m[2] + '}'

    body = re.sub(r'\\(section|subsection)\{([^}]+)\}', heading, body)
    equation = 0

    def eq(m):
        nonlocal equation
        equation += 1
        value = re.sub(r'\\begin\{aligned\}|\\end\{aligned\}', '', m[1]).replace('&', '')
        return '\n\\[\n' + value + '\n\\]\n\n\\noindent EQUATIONNUMBER' + str(equation) + '\n\n'

    body = re.sub(r'\\begin\{equation\}(.*?)\\end\{equation\}', eq, body, flags=re.S)
    figure = 0

    def fig(m):
        nonlocal figure
        figure += 1
        image = TMP / 'pipeline.png' if figure == 1 else ROOT / 'Bai_bao/figures/fig2_app_map_pair.png'
        return '\n\\noindent FIGUREIMAGE' + str(figure) + '\n\n'

    body = re.sub(r'\\begin\{figure\}.*?\\end\{figure\}', fig, body, flags=re.S)
    table = 0
    captions = []

    def tab(m):
        nonlocal table
        table += 1
        captions.append(re.search(r'\\caption\{([^}]+)\}', m[0])[1])
        name = re.search(r'\\input\{([^}]+)\}', m[0])[1]
        return '\n\\noindent TABLECAPTION' + str(table) + '\n\n' + clean_table(ROOT / 'Bai_bao' / name) + '\n\n'

    body = re.sub(r'\\begin\{table\}.*?\\end\{table\}', tab, body, flags=re.S)

    def enum(m):
        items = re.split(r'\\item\s+', m[1])[1:]
        return '\n\n' + '\n\n'.join(r'\noindent LISTITEM' + str(i) + ' ' + v.strip() for i, v in enumerate(items, 1)) + '\n\n'

    body = re.sub(r'\\begin\{enumerate\}(?:\[[^\]]*\])?(.*?)\\end\{enumerate\}', enum, body, flags=re.S)
    body = re.sub(r'\\(?:FloatBarrier|medskip|small|centering|ifanonymous|else|fi)\b', '', body)
    body = body[:body.index(r'\bibliographystyle')]
    references = []
    for i, part in enumerate(re.split(r'\\bibitem\{[^}]+\}', bbl)[1:], 1):
        part = re.sub(r'\\end\{thebibliography\}.*', '', part, flags=re.S)
        part = part.replace(r'\newblock', ' ')
        references.append(r'\noindent REFERENCEITEM' + str(i) + ' ' + re.sub(r'\s+', ' ', part).strip())
    body += '\n\\section*{TÀI LIỆU THAM KHẢO/ REFERENCES}\n' + '\n\n'.join(references)
    macros = '\n'.join(re.findall(r'^\\newcommand\{\\(?:Uset|Ua|Premain|Lmax|Tlost|dsaf|bmin|Nc|Dh|tauzero)\}.*$', SOURCE, re.M))
    tex = '\\documentclass{article}\n' + macros + '\n\\begin{document}\n' + body + '\n\\end{document}\n'
    (TMP / 'body.tex').write_text(tex, encoding='utf-8')
    (TMP / 'captions.json').write_text(json.dumps(captions, ensure_ascii=False), encoding='utf-8')
    print('Prepared', equation, 'equations,', table, 'tables,', figure, 'figures,', len(keys), 'references')


def font(run, size=11, bold=None, italic=None):
    run.font.name = 'Times New Roman'
    run.font.size = Pt(size)
    run.font.color.rgb = __import__('docx').shared.RGBColor(0, 0, 0)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def para_format(p, size=11, indent=True):
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1
    p.paragraph_format.first_line_indent = Cm(.5) if indent else Cm(0)
    p.paragraph_format.widow_control = True
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for r in p.runs:
        font(r, size)


def cell_text(cell, text, size=10, bold=False, italic=False, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = text
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    for p in cell.paragraphs:
        para_format(p, size, False)
        p.alignment = align
        for r in p.runs:
            font(r, size, bold, italic)
    return cell.paragraphs[0]


def populate_front(table, lang):
    def cell(row, col):
        return table.rows[row].cells[col]

    en = lang == 'en'
    title = ('A METHOD FOR FLIGHT-ROUTE REALLOCATION\nIN MULTI-UAV SYSTEMS FOLLOWING A FAILURE' if en else
             'PHƯƠNG PHÁP ĐIỀU PHỐI LẠI TUYẾN BAY\nCHO HỆ THỐNG ĐA UAV KHI XẢY RA SỰ CỐ')
    authors = 'Vu Dinh Nam' if en else 'Vũ Đình Nam'
    second = 'Pham Manh Thang' if en else 'Phạm Mạnh Thắng'
    affiliation = ('University of Engineering and Technology, Vietnam National University, Hanoi' if en else
                   'Trường Đại học Công nghệ, Đại học Quốc gia Hà Nội')
    abstracts = re.findall(r'\\textbf\{(?:ABSTRACT|TÓM TẮT)\}\\par\\vspace\{4pt\}\s*(.*?)\\end\{minipage\}', SOURCE, re.S)
    for row in table.rows:
        for height in list(row._tr.xpath('./w:trPr/w:trHeight')):
            height.getparent().remove(height)
    cell_text(cell(0, 0), title, 12, True)
    p = cell_text(cell(1, 0), '', 10, True)
    font(p.add_run(authors), 10, True)
    if en:
        ref = OxmlElement('w:footnoteReference')
        ref.set(qn('w:id'), '1')
        ref.set(qn('w:customMarkFollows'), '1')
        p.add_run()._r.append(ref)
    r = p.add_run('*')
    font(r, 10, True)
    r.font.superscript = True
    font(p.add_run(', ' + second), 10, True)
    cell_text(cell(2, 0), affiliation, 9, False, True)
    cell_text(cell(3, 0), 'ARTICLE INFO' if en else 'THÔNG TIN BÀI BÁO', 10, True, align=WD_ALIGN_PARAGRAPH.CENTER)
    cell_text(cell(3, 2), 'ABSTRACT' if en else 'TÓM TẮT', 10, True)
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
    cell_text(cell(4, 2), plain(abstracts[0 if en else 1]), 10, align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    dates = ['Received:', 'Revised:', 'Published:'] if en else ['Ngày nhận bài:', 'Ngày hoàn thiện:', 'Ngày đăng:']
    for i, text in enumerate(dates, 4):
        cell_text(cell(i, 0), text, 9, align=WD_ALIGN_PARAGRAPH.RIGHT)
        cell_text(cell(i, 1), '', 9)
    cell_text(cell(7, 0), 'KEYWORDS' if en else 'TỪ KHÓA', 10, True, align=WD_ALIGN_PARAGRAPH.CENTER)
    keywords = ['Multi-UAV systems', 'Residual-route handoff', 'Failure recovery', 'Online route reallocation', 'Vehicle separation'] if en else ['Hệ thống đa UAV', 'Bàn giao tuyến dư', 'Phục hồi sau sự cố', 'Điều phối lại trực tuyến', 'Phân tách UAV']
    cell_text(cell(8, 0), '\n'.join(keywords), 10)
    table.autofit = False


def border(element, edges):
    old = element.find(qn('w:tblBorders'))
    if old is not None:
        element.remove(old)
    borders = OxmlElement('w:tblBorders')
    for name in ['top', 'bottom', 'left', 'right', 'insideH', 'insideV']:
        e = OxmlElement('w:' + name)
        e.set(qn('w:val'), 'single' if name in edges else 'nil')
        e.set(qn('w:sz'), '4')
        e.set(qn('w:color'), '000000')
        borders.append(e)
    element.append(borders)


def assemble():
    d = Document(REF)
    front = [deepcopy(t._tbl) for t in d.tables[:2]]
    sect = deepcopy(d.sections[0]._sectPr)
    for typ in list(sect.findall(qn('w:type'))):
        sect.remove(typ)
    body = d._element.body
    for child in list(body):
        body.remove(child)
    body.append(sect)
    for node in front:
        sect.addprevious(node)
        p = d.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.line_spacing = 1
        for r in p.runs:
            font(r, 2)
    populate_front(Table(front[0], d._body), 'en')
    populate_front(Table(front[1], d._body), 'vi')
    # Match the reference's explicit first-page/body break.
    p = d.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    p.add_run().add_break(WD_BREAK.PAGE)
    converted = Document(TMP / 'converted.docx')
    for el in converted._element.body:
        if el.tag != qn('w:sectPr'):
            sect.addprevious(deepcopy(el))
    data_tables = list(d.tables[2:])
    for name in ['Normal', 'Body Text', 'First Paragraph', 'Compact', 'Heading 1', 'Heading 2', 'Title']:
        if name not in d.styles:
            d.styles.add_style(name, 1)
        s = d.styles[name]
        s.font.name = 'Times New Roman'
        s.font.size = Pt(11)
        s.font.color.rgb = __import__('docx').shared.RGBColor(0, 0, 0)
        s.paragraph_format.line_spacing = 1
        s.paragraph_format.space_after = Pt(0)
    captions = json.loads((TMP / 'captions.json').read_text(encoding='utf-8'))
    reference_mode = False
    for p in list(d.paragraphs):
        text = p.text.strip()
        style = p.style.name
        para_format(p)
        if style.startswith('Heading'):
            is_second = style == 'Heading 2'
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
            p.paragraph_format.keep_with_next = True
            for r in p.runs:
                font(r, 11, True, is_second)
        if text.startswith('TÀI LIỆU THAM KHẢO'):
            reference_mode = True
        if text.startswith('REFERENCEITEM'):
            match = re.match(r'REFERENCEITEM(\d+)\s*', text)
            for r in p.runs:
                if 'REFERENCEITEM' in r.text:
                    r.text = re.sub(r'REFERENCEITEM\d+\s*', '[' + match[1] + '] ', r.text)
                    break
            para_format(p, 10, False)
            p.paragraph_format.left_indent = Cm(.5)
            p.paragraph_format.first_line_indent = Cm(-.5)
            p.paragraph_format.space_after = Pt(3)
        elif text.startswith('LISTITEM'):
            match = re.match(r'LISTITEM(\d+)\s*', text)
            for r in p.runs:
                if 'LISTITEM' in r.text:
                    r.text = re.sub(r'LISTITEM\d+\s*', match[1] + '. ', r.text)
                    break
            p.paragraph_format.left_indent = Cm(.5)
            p.paragraph_format.first_line_indent = Cm(-.5)
            p.paragraph_format.space_after = Pt(2)
        if text.startswith('FIGUREIMAGE'):
            n = int(text[-1])
            p.clear()
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.keep_with_next = True
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            image = TMP / 'pipeline.png' if n == 1 else ROOT / 'Bai_bao/figures/fig2_app_map_pair.png'
            p.add_run().add_picture(str(image), width=Cm(15.2 if n == 1 else 10.64))
            cap = d.add_paragraph()
            p._p.addnext(cap._p)
            para_format(cap, 10, False)
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap.paragraph_format.space_after = Pt(5)
            font(cap.add_run(f'Hình {n}. '), 10, True)
            font(cap.add_run('Quy trình điều phối lại.' if n == 1 else 'Tuyến bay: (a) trước bàn giao; (b) sau bàn giao.'), 10, False, True)
        elif text.startswith('TABLECAPTION'):
            n = int(text[-1])
            p.clear()
            p.paragraph_format.first_line_indent = Cm(0)
            p.paragraph_format.keep_with_next = True
            p.paragraph_format.space_before = Pt(5)
            p.paragraph_format.space_after = Pt(5)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            font(p.add_run(f'Bảng {n}. '), 10, True)
            font(p.add_run(captions[n - 1]), 10, False, True)
        elif text.startswith('EQUATIONNUMBER'):
            n = int(text.removeprefix('EQUATIONNUMBER'))
            eqel = p._p.getprevious()
            eqp = Paragraph(eqel, d._body)
            t = d.add_table(rows=1, cols=2)
            t.autofit = False
            t.alignment = WD_TABLE_ALIGNMENT.CENTER
            t.columns[0].width = Cm(14.2)
            t.columns[1].width = Cm(1)
            border(t._tbl.tblPr, [])
            for cell, width in zip(t.rows[0].cells, [14.2, 1]):
                cell.width = Cm(width)
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                margins = OxmlElement('w:tcMar')
                for side in ['top', 'left', 'bottom', 'right']:
                    e = OxmlElement('w:' + side)
                    e.set(qn('w:w'), '0')
                    e.set(qn('w:type'), 'dxa')
                    margins.append(e)
                cell._tc.get_or_add_tcPr().append(margins)
            cell = t.rows[0].cells[0]
            cell._tc.remove(cell.paragraphs[0]._p)
            cell._tc.append(deepcopy(eqel))
            mathp = cell.paragraphs[0]
            para_format(mathp, 11, False)
            mathp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            mathp.paragraph_format.space_before = Pt(3)
            mathp.paragraph_format.space_after = Pt(3)
            numberp = cell_text(t.rows[0].cells[1], f'({n})', 11, align=WD_ALIGN_PARAGRAPH.RIGHT)
            t.rows[0].cells[1].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            eqel.addprevious(t._tbl)
            eqel.getparent().remove(eqel)
            p._p.getparent().remove(p._p)
    for i, t in enumerate(data_tables, 1):
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        widths = {1: [7.0, 2.4, 3.8, 2.0], 2: [2.4, 3.4, 6.0, 3.4], 3: [5.8, 2.4, 2.4, 2.4, 2.2], 4: [1.7, 1.7, 3.5, 3.5, 4.8]}[i]
        for col, width in zip(t.columns, widths):
            col.width = Cm(width)
        border(t._tbl.tblPr, ['top', 'bottom'])
        for j, row in enumerate(t.rows):
            if j == 0:
                row._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
            row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
            for k, cell in enumerate(row.cells):
                cell.width = Cm(widths[k])
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                for p in cell.paragraphs:
                    para_format(p, 10, False)
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT if k == 0 else WD_ALIGN_PARAGRAPH.CENTER
                    p.paragraph_format.space_before = Pt(1)
                    p.paragraph_format.space_after = Pt(1)
                    p.paragraph_format.keep_with_next = j < len(t.rows) - 1
                    if i == 4:
                        p.paragraph_format.space_before = Pt(0)
                        p.paragraph_format.space_after = Pt(0)
                    if j == 0:
                        for r in p.runs:
                            r.bold = True
                if j == 0:
                    b = OxmlElement('w:tcBorders')
                    e = OxmlElement('w:bottom')
                    e.set(qn('w:val'), 'single')
                    e.set(qn('w:sz'), '4')
                    b.append(e)
                    cell._tc.get_or_add_tcPr().append(b)
    d.save(OUT)
    # Preserve the reference's real footnote part, replacing only its email.
    with ZipFile(OUT) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    foot = parts['word/footnotes.xml'].decode('utf-8').replace('abc@xyz.com', 'namvd1208@vnu.edu.vn')
    parts['word/footnotes.xml'] = foot.encode('utf-8')
    with ZipFile(OUT, 'w', ZIP_DEFLATED) as z:
        for n, data in parts.items():
            z.writestr(n, data)
    x = etree.fromstring(parts['word/document.xml'])
    print('Saved', OUT)
    print('Native math objects:', len(x.findall('.//m:oMath', NS)))
    print('Data tables:', len(data_tables), 'Images:', len(d.inline_shapes))


if __name__ == '__main__':
    prepare() if sys.argv[1] == 'prepare' else assemble()
