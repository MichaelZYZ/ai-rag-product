"""Synchronize the RAG supplement into existing project documentation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = '\n## 2026-11-03：课程 RAG 链路补充\n'

README = r'''
本次保留字符检索基线，新增本地/API 语义 Embedding、FAISS 精确索引、严格模型模式和 45 题可复现实验。默认启动仍为 hash + auto；需要语义检索时安装可选依赖并设置环境变量。

```bash
source .venv/bin/activate
python -m pip install -r requirements-rag.txt
python seed.py --course
export RAG_RETRIEVER=semantic
export RAG_ANSWER_MODE=extractive
python reindex.py
python run_server.py
```

`seed.py --course` 会重建演示产品及虚构校园语料中同产品、版本、来源的资料，保留其他来源。请勿将自行修改过的同名演示文档当正式资料使用。正常启动不会自动添加校园样例。

模型缓存默认位于 `.cache/huggingface`，可通过 HF_HOME 覆盖。首次下载需要网络，缓存后可使用 `HF_HUB_OFFLINE=1`。配置页面新增检索/生成状态与补建语义索引按钮。原文入库后语义向量按需补建；旧数据库无需重传资料即可运行 `reindex.py`。

真实生成可在“知识配置 → 免费 API 与模型选择”中保存服务与 Key，或配置 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL，并设置 `RAG_ANSWER_MODE=llm`。Base URL 后追加 `/chat/completions`；完整配置不代表服务已验证。模型缺失/失败时严格模式返回失败状态，不伪装成模型回答。自动模式 `auto` 保留 FAQ 优先和原文回退；`extractive` 绕过 FAQ 快捷回答并返回 Top-1 原文。FAQ 冲突与敏感业务仍转人工。`.env.example` 仅为参考，应用支持网页配置和进程环境，不自动加载该文件。

语义 Embedding 默认为本地多语言模型；需 API Embedding 时设 `EMBEDDING_PROVIDER=api`，并分别设置 EMBEDDING_BASE_URL、EMBEDDING_API_KEY、EMBEDDING_MODEL。向量服务和生成服务可独立配置。`RAG_MIN_SCORE` 可覆盖阈值，但必须在独立开发集上校准，不能把相似度当置信概率。

```bash
python benchmark.py
python benchmark.py --with-llm --output reports/llm-run
python review_results.py reports/latest
python -m pip install -r requirements-docs.txt
python scripts/plot_results.py reports/latest
python scripts/build_deliverables.py
python scripts/package_project.py
```

第二条命令只应在服务配置完整且获准发送教学语料后运行。实验使用临时数据库，不污染正式咨询记录；未执行的方案明确列在 skipped 中。新增依赖在本次 macOS 环境验证，Windows 扩展依赖兼容性尚未实测，原基础启动检查保持不变。

当前真实离线结果：45 题中字符基线通过 33 题，语义方案通过 38 题；证据 Hit@1 分别为 80.56% 和 91.67%，无答案题拒答准确率分别为 87.50% 和 50.00%。语义召回改善同时出现错误接受，不能据此宣称已解决幻觉。真实 LLM 结果与人工忠实度/相关性评分尚待服务配置及评阅，未用推测数据填充。

新增文件：`app/semantic.py`（语义向量/FAISS）、`reindex.py`（增量索引）、`benchmark.py` 和 `app/experiments.py`（完整实验）、`review_results.py`（人评汇总）、`data/course_knowledge.json`（虚构校园资料）、`data/eval_extended.json`（45 题）、`reports/latest/`（实际结果）、`docs/`（设计、评估、失败分析和提交核对）、`scripts/`（图表、Word/PPT 和打包工具）。

详细设计见 [RAG 补充设计](docs/RAG_IMPLEMENTATION.md)，操作见 [业务手册](BUSINESS_OPERATIONS.md)，评估见 [复现与人评说明](docs/EVALUATION_GUIDE.md)，实际失败见 [失败案例分析](docs/FAILURE_ANALYSIS.md)。代码包排除数据库、密钥环境文件和模型缓存；迁移正式知识库仍需另行备份原数据库。
'''

OPERATIONS = r'''
### 1. 选择运行方式

原有双击启动默认保留字符检索和自动回答。要展示完整语义 RAG，请先在项目目录激活虚拟环境，安装 `python -m pip install -r requirements-rag.txt`。macOS/Linux 在同一终端执行下面命令：

```bash
export RAG_RETRIEVER=semantic
export RAG_ANSWER_MODE=extractive
python reindex.py
python run_server.py
```

Windows PowerShell 使用对应虚拟环境解释器；环境设置方式如下：

```powershell
$env:RAG_RETRIEVER = 'semantic'
$env:RAG_ANSWER_MODE = 'extractive'
.\.venv\Scripts\python.exe reindex.py
.\.venv\Scripts\python.exe run_server.py
```

第一次本地模型下载可能需几分钟；缓存放在 `.cache/huggingface`。下载后可断网使用。若出现依赖或模型错误，先检查终端信息；无需删除数据库。CPU 推理默认使用单线程。语义模式下模型/FAISS 不可用会明确报错，不会悄悄切回字符方案。

### 2. 配置真正的模型生成

推荐直接在“知识配置 → 免费 API 与模型选择”中选择服务商和模型，填 Key 并保存测试，无需重启。也可在启动服务的同一终端设置 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY 和 RAG_ANSWER_MODE=llm，再启动服务。网页保存的配置优先于环境变量。密钥仅在本机配置，不发到聊天或写入文档。应用不会自动读取 .env。API 地址应是追加 /chat/completions 前的 Base URL。兼容服务若要求占位鉴权值，应按其说明配置。

严格模型模式只有确实收到模型内容才显示“模型生成”；配置缺失、超时、空响应时提示服务不可用。自动模式命中 FAQ 时仍是直接知识库回答。点击聊天来源按钮查看回答方式和证据，不能只凭文字流畅程度判断是否使用了大模型。

### 3. 导入与补建索引

上传与原来的三步审核流程相同。导入成功代表原文和基线片段已保存；在配置页点击“补建语义向量索引”，看到当前模型已索引片段数与总数一致后再演示。首次语义问答也会补建，但会较慢。更换 Embedding 模型后重新补建，系统保留模型隔离，不复用旧空间向量。删除文档会级联删除关联向量。

需要课堂校园样例时运行 `python seed.py --course`。这些规则是虚构语料，不能用于真实校园办事；该命令重建同名演示来源，其他来源保留。正常双击启动只保留原演示初始化逻辑，不自动添加新语料。

### 4. 效果检查与失败分析

页面“查看效果评估”仍运行 8 题离线快速回归，不代表真实模型质量。完整 45 题检索对比运行 `python benchmark.py`。真实生成对比需先配置服务，再运行 `python benchmark.py --with-llm --output reports/llm-run`。查看输出目录的 RESULTS.md 和 benchmark.json；失败项也保留，不能从报告里删除。

用电子表格打开 human_review.csv，只对成功回答填写 faithfulness、answer_relevance、reviewer、reason。两项分数均为 0/1/2；评分标准见 docs/EVALUATION_GUIDE.md。不要修改 id、run、record_digest 或答案证据。保存为 UTF-8 CSV 后运行 `python review_results.py 输出目录`。未评分显示 null，不能当满分。检查 coverage，少量抽样不能冒充全量人评。

### 5. 文档更新与交付

安装 requirements-docs.txt 后运行 `python scripts/plot_results.py reports/latest` 生成图表；运行 `python scripts/build_deliverables.py` 同步 Word 补充与 PPT 技术草稿；运行 `python scripts/package_project.py` 生成 dist 下代码包。代码包不含实际运行数据库、缓存模型和真实密钥；目标机器需安装依赖并初始化资料。需要迁移已上传资料时单独备份数据库，不把运行数据混进课堂提交包。

教师报告中的真实模型结果、人工评分、成员分工、每人贡献和互评仍须根据实际情况填写，参见 docs/SUBMISSION_CHECKLIST.md。不要直接把生成的技术素材当作已完成个人评审的最终报告。
'''

DESIGN = '''
新增语义模块、索引表、回答模式、接口、实验数据流与一致性策略详见 [RAG 完整链路补充设计](docs/RAG_IMPLEMENTATION.md)。本章与该补充设计优先解释新增功能；前文字符向量与 FAQ 章节仍描述保留的基线路径。

新增 `semantic_vectors(chunk_id, identity, content_hash, vector, dimension)`，按模型空间隔离并随片段级联删除；持久化归一化 float32 向量，按产品和版本构建内存 FAISS IndexFlatIP。索引按需增量补建，模型推理放在会话写事务之前。该索引是精确搜索，未引入 ANN 或常驻向量服务。

新增 GET /api/rag/status 与 POST /api/rag/reindex。问答结果新增 retriever、generation_mode、generation_error。严格模型模式绕过 FAQ 快捷回答，服务异常不伪装成生成成功；自动模式保留原兼容路径。

完整实验使用 6 份虚构文档、45 个问题，在独立临时库中比较相同语料的 hash_extractive 与 semantic_extractive。真实结果与图表位于 reports/latest，当前分别通过 33/45 与 38/45；新增语义方案存在拒答退化，见 [实际失败分析](docs/FAILURE_ANALYSIS.md)。关键词匹配、证据命中与人工忠实度/相关性分开统计。人评尚未完成时留空，不用检索分数替代。

真实 LLM 实验入口已经实现，实际质量结果需配置用户指定服务后运行。GraphRAG、微调、在线逐事实校验、生产鉴权和正式人工工单服务未实现，也不是本次基础课程闭环的前置条件。
'''


def update(name, content, replacements=()):
    path = ROOT / name
    text = path.read_text(encoding='utf-8').split(MARKER)[0]
    for old, new in replacements:
        text = text.replace(old, new)
    path.write_text(text.rstrip() + '\n' + MARKER + content.strip() + '\n', encoding='utf-8')


def main():
    update('README.md', README, [
        ('根据两份设计文档实现的可运行 MVP。', '根据设计文档实现的可运行问答系统，包含字符基线与可选语义 RAG。'),
        ('生产部署可换成语义模型和专用向量库。', '新增语义模型与 FAISS 路径见文末补充；生产部署仍需扩展性能与权限。'),
        ('该文件被 `.gitignore` 排除，Git 拉取或复制不含数据库的代码到另一台机器时，不会带上已上传资料、聊天记录、人工问答和自定义 Prompt。',
         '新增数据库文件由 `.gitignore` 排除；历史仓库曾跟踪该文件，忽略规则不会自动移除已跟踪文件。提交打包脚本会明确排除所有 SQLite 运行数据。复制不含数据库的代码到另一台机器时，不会带上已上传资料、聊天记录、人工问答和自定义 Prompt。'),
        ('网页、Excel、鉴权、限流和人工工单系统集成', 'URL 抓取、Excel、鉴权、限流和人工工单系统集成')])
    update('BUSINESS_OPERATIONS.md', OPERATIONS)
    update('ARCHITECTURE.md', DESIGN, [
        ('## 5. 问答决策流程', '## 5. 默认 auto 模式问答决策流程'),
        ('当前实现面向课堂演示：没有管理员鉴权、权限隔离、限流或正式工单系统；SQLite 和内存中逐条比较向量适合小规模资料；字符 n-gram 并非语义 Embedding。', '当前实现面向课堂演示：没有管理员鉴权、权限隔离、限流或正式工单系统；字符基线与新增 FAISS 精确检索均面向小规模资料，语义模式使用独立预训练 Embedding。'),
        ('这是单体应用，没有独立的向量数据库或训练服务。', '这是单体应用，支持字符检索基线与可选 FAISS 语义检索，没有独立训练服务。'),
        ('SQLite 文件被 Git 忽略，跨机器迁移需另行复制该文件', '新增 SQLite 文件被 Git 忽略，历史已跟踪文件需单独核对；提交包明确排除运行数据库，跨机器迁移需另行复制该文件')])
    update('SYSTEM_DESIGN.md', DESIGN, [
        ('代码中的局部变量 `semantic` 实际也是字符哈希向量点积。', '字符基线中的局部变量 `cosine` 是字符哈希向量点积，与新增语义模型表示分开。'),
        ('当前捕获所有异常并静默回退，便于演示，但后续需要增加异常日志来定位服务问题。', 'auto 模式捕获模型异常并回退，但返回 generation_error；严格 llm 模式返回失败状态，不回退冒充成功。'),
        ('引入语义向量、关键词检索和重排，在标注集上调整阈值。', '语义向量与 FAISS 已补充；后续加入关键词融合与重排，在独立开发集上校准阈值。'),
        ('整理日期：2026-10-09。', '整理日期：2026-10-09；RAG 链路补充更新：2026-11-03。'),
        ('当前没有独立向量数据库、语义 Embedding 模型或模型微调流程。',
         '当前支持可选语义 Embedding 与 FAISS 精确索引，没有独立向量数据库服务或模型微调流程；原字符基线仍保留。')])
    update('PROJECT_QA_GUIDE.md', DESIGN, [
        ('本项目使用字符 n-gram 哈希向量，将连续的 2～4 个字符映射到固定的 4096 维空间。', '本项目保留字符 n-gram 哈希基线，并新增本地/API 语义 Embedding 与 FAISS。字符基线将连续的 2～4 个字符映射到固定的 4096 维空间；语义路线使用预训练模型表示。'),
        ('片段检索时综合向量相似度与问题字符覆盖率进行排序：', '字符基线片段检索时综合向量相似度与问题字符覆盖率排序；语义路线使用归一化内积排序：'),
        ('当前使用的是字符哈希向量，主要反映字面片段的重合，没有通过预训练学习深层语义。', '默认基线使用字符哈希向量，主要反映字面片段重合；新增 semantic 路线使用预训练多语言模型，在本机实际完成了 FAISS 对比实验。'),
        ('主动说明当前方法适合离线演示、部署简单，同时承认它对语义理解的限制。', '说明字符基线与语义模型的区别，以及语义召回改善仍伴随无答案错误接受的实测结果。'),
        ('FAQ 未充分匹配时再使用片段检索，可以兼顾常见问题的稳定性与资料覆盖范围。', 'auto 模式中 FAQ 未充分匹配时再使用片段；extractive 与 llm 模式绕过 FAQ 快捷回答以便进行检索/生成实验，冲突检查保留。'),
        ('后续可以引入语义向量和重排模型、OCR、结构化对话状态，并扩充同义问法、否定表达、跨版本和冲突问题的评估集。', '语义向量与 45 题扩展评估已实现；后续需要证据充分性检查、重排模型、OCR、结构化对话状态、独立开发集以及真实模型/人工质量评估。')])


    for name in ['README.md', 'BUSINESS_OPERATIONS.md', 'ARCHITECTURE.md', 'SYSTEM_DESIGN.md', 'PROJECT_QA_GUIDE.md']:
        path = ROOT / name
        text = path.read_text(encoding='utf-8')
        text = text.replace('超时 20 秒', '超时 45 秒')
        text += '\n## 免费 API 下拉配置（2026-11-03）\n\n'
        text += '知识配置页已新增服务商与模型下拉框，默认预选 OpenRouter 免费路由；另有 Groq Free Plan、Gemini 免费层及自定义兼容 API。填入自己的 Key 后保存并测试，无需改源码或重启。额度以账户和官方政策为准，不自动切换收费模型。\n\n'
        text += '配置由 app/llm_config.py 管理，密钥保存在数据库旁的 *.llm.json 本机文件，不写入 SQLite、不回显、不进入提交包。配置接口为 GET/PUT/DELETE /api/llm/config；POST /api/llm/test 仅发送固定测试短句。网页配置优先于环境变量；清除后恢复环境变量方式。benchmark.py --with-llm 可读取已保存服务，离线回归禁止远程调用。\n\n'
        text += '完整操作、限制与官方链接见 [免费 API 配置说明](docs/FREE_API_SETUP.md)。本次已完成协议与错误路径测试，真实平台连通性需要用户自备 Key 后验证。\n'
        path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
