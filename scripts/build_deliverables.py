"""Build editable documentation and presentation from reviewed repository sources."""
import json
import re
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt as PptPt

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
MARKER = '2026-11-03 RAG 链路与课程评估补充'


def clean(text):
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1（\2）', text)
    return text.replace('**', '').replace('`', '')


def set_fonts(document):
    normal = document.styles['Normal']
    normal.font.name = 'Microsoft YaHei'
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    normal.paragraph_format.space_after = Pt(5)
    normal.paragraph_format.line_spacing = 1.2
    for section in document.sections:
        section.top_margin = section.bottom_margin = Cm(2)
        section.left_margin = section.right_margin = Cm(2.2)


def markdown(document, text):
    code = False
    table = None
    for line in text.splitlines():
        if line.startswith('```'):
            code = not code
            table = None
            continue
        if not line.strip():
            table = None
            continue
        if code:
            p = document.add_paragraph(line)
            for run in p.runs:
                run.font.name = 'Consolas'
                run.font.size = Pt(9)
        elif line.startswith('|'):
            cells = [clean(c.strip()) for c in line.strip().strip('|').split('|')]
            if all(re.fullmatch(r'[:\- ]+', c) for c in cells):
                continue
            if table is None:
                table = document.add_table(rows=0, cols=len(cells))
                table.style = 'Table Grid'
            for cell, value in zip(table.add_row().cells, cells):
                cell.text = value
        elif line.startswith('#'):
            level = min(len(line) - len(line.lstrip('#')), 4)
            document.add_heading(clean(line.lstrip('#').strip()), level=level)
            table = None
        else:
            document.add_paragraph(clean(line))
            table = None


def add_result(document, report):
    document.add_heading('本次实际实验结果', level=1)
    document.add_paragraph('时间：' + report['created_at'] + '；语料与数据摘要见 reports/latest/benchmark.json。')
    table = document.add_table(rows=1, cols=5)
    table.style = 'Table Grid'
    for cell, value in zip(table.rows[0].cells, ['方案', '通过数', '状态准确率', '证据 Hit@1', '拒答准确率']):
        cell.text = value
    for name, result in report['runs'].items():
        values = [name, f"{result['passed']}/{result['cases']}", f"{result['status_accuracy']:.2%}",
                  f"{result['hit_at_k']['1']:.2%}", f"{result['abstention_accuracy']:.2%}"]
        for cell, value in zip(table.add_row().cells, values):
            cell.text = value
    chart = ROOT / 'reports/latest/metrics.png'
    if chart.exists():
        document.add_picture(str(chart), width=Cm(16))
    document.add_paragraph('以上是检索后原文回答实验，不是 LLM 忠实度结果。人工评分与真实模型实验未完成时保留待补，不填造数据。')


def new_doc(name, title, sources, report, results=False):
    document = Document()
    set_fonts(document)
    document.add_heading(title, 0)
    document.add_paragraph('更新：2026-11-03；技术材料，供团队核对与改写。')
    for source in sources:
        markdown(document, (ROOT / source).read_text(encoding='utf-8'))
    if results:
        add_result(document, report)
    document.save(DOCS / name)


def append_existing(path, report):
    document = Document(path)
    body = document.element.body
    deleting = False
    for element in list(body):
        texts = ''.join(element.itertext())
        if MARKER in texts:
            deleting = True
        if deleting and element.tag != qn('w:sectPr'):
            body.remove(element)
    document.add_heading(MARKER, level=1)
    document.add_paragraph('本章更新前文的实现范围描述。早期“没有语义向量/索引”等陈述仅适用于保留的字符基线。原系统图与历史实验记录保留，新增链路以本章为准。')
    for source in ['docs/RAG_IMPLEMENTATION.md', 'docs/EVALUATION_GUIDE.md', 'docs/FAILURE_ANALYSIS.md', 'docs/FREE_API_SETUP.md']:
        markdown(document, (ROOT / source).read_text(encoding='utf-8'))
    add_result(document, report)
    document.save(path)


def slides(report):
    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    entries = [
        ('领域知识库问答系统', ['语义 Embedding + FAISS + 检索增强生成', '课程演示技术草稿｜2026-11-03', '成员姓名、分工与真实模型结果由团队补充']),
        ('问题与应用场景', ['基于指定产品文档或校园手册回答领域问题', '按产品与版本检索，减少知识串用', '回答带来源；资料不足拒答，敏感业务转人工']),
        ('语料与处理', [f"自建虚构语料 {report['corpus_documents']} 份，原文 {report['corpus_characters']} 字符", f"清洗、标题保留、切分后 {report['chunks']} 个片段", '演示规则不对应真实学校或真实产品；语料可公开复现']),
        ('系统架构', ['浏览器 → FastAPI → 会话编排', '文档清洗 → 分块 → 语义 Embedding → 向量持久化', '产品/版本过滤 → FAISS Top-K → LLM 或原文回答', '结果 → 指标与人评 → 失败分析与知识补充']),
        ('向量与索引', ['保留 4096 维字符哈希作为基线', '新增多语言 SentenceTransformer，也可接兼容 Embedding API', '归一化 float32 向量 + FAISS IndexFlatIP', '按模型标识隔离；增量建库；删除级联；索引按范围重建']),
        ('检索与回答模式', ['页面下拉选择 OpenRouter / Groq / Gemini / 自定义', 'auto：FAQ 优先；extractive：返回 Top-1 原文', 'llm：严格调用模型，失败不冒充生成成功', '自备 Key，保存并测试连接；密钥不随代码包提交']),
        ('现场演示步骤', ['配置页查看检索/生成状态并补建语义索引', '查询借阅上限、证明领取地点与版本差异', '对比未知功能或考试周时间的回答与证据', '运行 45 题实验，查看失败样本与评分表']),
        ('实验设置', ['45 个固定问题：36 可回答、8 无答案、1 转人工', '同一临时语料库、同一原文模式比较两种检索方案', '固定阈值：字符 0.16、语义 0.35；未在本测试集调参', '真实 LLM 方案依赖服务配置；未执行项明确标记']),
        ('实际结果：召回改善与拒答退化', []),
        ('失败案例：有来源仍可能答非所问', ['“工作日几点开放”被字符检索匹配到证明办理工作日', '“普通图书借多久”被语义检索匹配到续借 15 天', '“参考书能外借吗”被匹配到普通图书续借操作', '说明主体、属性、时间条件和否定表达需要专项评测']),
        ('失败案例：相似资料不能证明有答案', ['语音转写和价格问题仍可能返回相似但无关片段', '考试周另行公告，不能套用工作日/周末时间', '语义方案通过更多题，但无答案拒答准确率更低', '下一步：证据充分性、重排、独立开发集校准']),
        ('质量评估与局限', ['关键词匹配与证据 Hit@K 分开统计', '忠实度/相关性采用 0–2 分评阅，附依据和覆盖率', '未进行的人评、真实 LLM 运行不填入假数据', '小规模自建语料；无独立测试集；无生产性能结论']),
        ('提交与成员答辩', ['代码、语料、Prompt、结果与文档可复现打包', '报告至少 5000 字；每人贡献说明 500–1000 字', '成员真实分工、互评、服务配置与人评仍需团队填写', '可选 GraphRAG、微调；当前优先完成模型实验闭环'])
    ]
    for number, (title, bullets) in enumerate(entries, 1):
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        background = slide.background.fill
        background.solid()
        background.fore_color.rgb = RGBColor(246, 249, 252)
        title_box = slide.shapes.add_textbox(Inches(0.7), Inches(0.5), Inches(12), Inches(1))
        run = title_box.text_frame.paragraphs[0].add_run()
        run.text = title
        run.font.name = 'Microsoft YaHei'
        run.font.size = PptPt(32)
        run.font.bold = True
        run.font.color.rgb = RGBColor(23, 45, 77)
        if bullets:
            box = slide.shapes.add_textbox(Inches(0.85), Inches(1.8), Inches(11.7), Inches(4.8))
            frame = box.text_frame
            frame.word_wrap = True
            for i, text in enumerate(bullets):
                paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
                paragraph.text = '• ' + text
                paragraph.font.name = 'Microsoft YaHei'
                paragraph.font.size = PptPt(24)
                paragraph.space_after = PptPt(22)
                paragraph.font.color.rgb = RGBColor(38, 59, 85)
        else:
            chart = ROOT / 'reports/latest/metrics.png'
            if chart.exists():
                slide.shapes.add_picture(str(chart), Inches(2), Inches(1.5), height=Inches(5.3))
        footer = slide.shapes.add_textbox(Inches(0.7), Inches(7), Inches(12), Inches(0.3))
        footer.text_frame.paragraphs[0].text = f'RAG 课程项目｜技术草稿｜{number}/{len(entries)}'
    presentation.save(DOCS / '课程演示_技术草稿.pptx')


def main():
    report = json.loads((ROOT / 'reports/latest/benchmark.json').read_text(encoding='utf-8'))
    DOCS.mkdir(exist_ok=True)
    new_doc('项目说明文档.docx', '领域问答系统项目说明', ['README.md', 'docs/FREE_API_SETUP.md'], report, True)
    new_doc('业务操作手册.docx', '产品与校园知识库问答操作手册', ['BUSINESS_OPERATIONS.md', 'docs/EVALUATION_GUIDE.md', 'docs/FREE_API_SETUP.md'], report)
    new_doc('项目设计文档.docx', 'RAG 项目设计与实现', ['SYSTEM_DESIGN.md', 'docs/RAG_IMPLEMENTATION.md', 'docs/FREE_API_SETUP.md'], report, True)
    new_doc('课程报告补充材料.docx', '课程报告技术材料（待团队核对改写）',
            ['docs/RAG_IMPLEMENTATION.md', 'docs/EVALUATION_GUIDE.md', 'docs/FAILURE_ANALYSIS.md', 'docs/SUBMISSION_CHECKLIST.md'], report, True)
    for name in ['product_qa_robot_design.docx', '产品知识库问答系统_架构与核心实现设计文档.docx']:
        append_existing(ROOT / name, report)
    slides(report)
    print('已生成 4 份 Word、1 份 PPT，并补充现有两份设计 Word。')


if __name__ == '__main__':
    main()
