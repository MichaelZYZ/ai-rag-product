# 产品知识问答项目架构

本文描述仓库当前实现，适用于开发、演示和后续改造。项目是本地运行的产品知识问答应用：将产品资料整理为可检索片段和问答，按产品与版本回答用户问题，并记录知识缺口、人工补充和评价。

## 1. 总体结构

```mermaid
flowchart LR
    U[浏览器<br/>app/static/index.html] -->|HTTP /api| A[FastAPI<br/>app/main.py]
    A --> C[业务与检索<br/>app/core.py]
    C --> P[文档解析与清洗<br/>html_extract.py / cleaning.py]
    C --> F[FAQ 提取与话术整理<br/>app/faq.py]
    C --> V[字符 n-gram 向量化<br/>scikit-learn]
    C <--> D[(SQLite<br/>data/rag.sqlite3)]
    C -. 已配置时 .-> L[兼容 Chat Completions 的 LLM 服务]
```

这是单体应用，支持字符检索基线与可选 FAISS 语义检索，没有独立训练服务。页面是原生 HTML、CSS 和 JavaScript；后端由 Uvicorn 承载 FastAPI；SQLite 同时保存业务记录、清洗后的原文和向量。默认数据库路径是 `data/rag.sqlite3`，可用 `RAG_DB` 环境变量覆盖。

## 2. 模块职责

| 位置 | 职责 |
| --- | --- |
| `app/static/index.html` | 产品问答与独立知识配置视图：清洗参数、三步导入、QA 预览审核、Prompt 调整、话术整理；保留知识缺口、统计与评估；通过 `fetch` 调用 API。 |
| `app/main.py` | FastAPI 路由、请求字段校验、异常到 HTTP 状态码的转换、统计查询。 |
| `app/core.py` | 数据库初始化、资料入库、向量检索、FAQ 匹配、会话编排、转人工、人工补充和可选 LLM 调用。 |
| `app/html_extract.py` | 从 HTML 提取可见文字，保留标题和块级分隔，过滤脚本、样式等页面内容。 |
| `app/cleaning.py` | 规范化字符和空白、过滤页码与重复行，并生成清洗报告。 |
| `app/faq.py` | 提取原文中的显式问答；从明确事实、章节和带主题的条目生成来源可核对的问答。 |
| `prompts/answer.txt` | 可选 LLM 在片段回答路径使用的默认系统提示词；页面可保存自定义覆盖内容。 |
| `seed.py`、`data/demo_knowledge.json` | 导入虚构演示产品和资料。 |
| `evaluate.py`、`app/evaluation_worker.py`、`data/eval_cases.json`、`tests/` | 可复现评估样例；网页评估在当前数据库副本上运行固定样例，避免污染正式记录。 |
| `run_server.py`、`start_mac.command`、`start_windows.bat`、`bootstrap_windows.ps1` | 本地启动入口；macOS 和 Windows 脚本检查并补齐 Python、虚拟环境和依赖。 |

## 3. 资料导入流程

```mermaid
flowchart TD
    A[知识配置：导入文件与参数] --> B[POST /api/documents/preview]
    B --> C[prepare_document：解析、清洗、QA 与片段]
    C --> D[展示原文和统计，不写库]
    D --> E[QA 问答分段：核对答案、调整问题、勾选 QA]
    E -- 返回调整 --> A
    E -- 确认入库 --> F[POST /api/documents：同一文件和参数]
    F --> G[重新处理并校验候选索引，保留原文答案]
    G --> H[向量化并事务保存完整原文、片段、已选 QA 和清洗参数]
    H --> I[完成：测试对应产品版本的问答]
```

预览接口为 `POST /api/documents/preview`，确认入库接口为 `POST /api/documents`，单文件上限 5 MB。支持 `.txt`、`.md`、`.html`、`.htm`、`.docx` 和可提取文字的 `.pdf`。HTML 提取可见正文；DOCX 读取文档 XML；PDF 使用 `pypdf` 提取文字，扫描件需要事先 OCR。

界面使用“导入 → QA 问答分段 → 完成”的流程。可配置页码和相邻重复行过滤、片段长度（120～2000 字）及重叠长度（小于片段长度的一半）。预览不写库，确认时重新上传原文件并传入 `review=true`、已选 QA 的索引及问题；答案由后端从重新处理的原文候选取得。没有选择 QA 时仍保存片段，取消 QA 不删除原文事实。

清洗后的完整文字保存在 `document_texts`，本次参数保存在 `cleaning_report.settings`。切片默认每段最多约 360 字，长行默认重叠 50 字（不超过正文容量的一半），标题随正文一起存入片段。`HashingVectorizer` 使用字符 2 至 4 gram、4096 维、L2 归一化；向量以 `float32` 字节存入 SQLite。导入时还会识别文档中的 `Q:/A:`、`问题:/答案:`，并从明确事实或章节标题生成初始 FAQ。

## 4. 话术整理与人工补充

“知识配置”中的“整理产品话术”要求选择目标产品和版本，调用 `POST /api/faqs/train`，可以限定产品和版本。它逐份读取已保存的资料原文，从章节、显式问答以及“首次开机：…”“无法充电：…”这类带主题的条目补充问答。保存前会检查答案文字出自该文档，并按文档及规范化问题去重，因此重复执行不会重复新增。旧文档缺少完整原文时，系统会尽量从已存片段重建。

这里的“训练”是**整理并索引 FAQ**，不会修改模型参数。自动生成的答案基于资料文字，仍可能需要人工审核问法是否自然、适用范围是否准确。

人工补充走 `POST /api/faqs/manual`，或对知识缺口调用 `POST /api/gaps/{gap_id}/answer`。人工答案作为独立资料、片段和 FAQ 入库；填写知识缺口时会校验产品、版本和问题范围。若同一范围已有不同答案，接口会要求先核对资料。

## 5. 默认 auto 模式问答决策流程

```mermaid
flowchart TD
    Q[用户问题] --> S[确定产品与版本、记录会话]
    S --> H{敏感业务或要求人工?}
    H -- 是 --> T[创建转人工记录]
    H -- 否 --> P{产品发现问题或产品未确定?}
    P -- 是 --> PC[返回候选产品或提示无知识库]
    P -- 否 --> R[同范围 FAQ 匹配 + 片段检索]
    R --> X{FAQ 答案冲突?}
    X -- 是 --> T
    X -- 否 --> M{FAQ 命中?}
    M -- 是 --> FA[返回 FAQ 答案和来源]
    M -- 否 --> K{片段达到阈值且通过关键词检查?}
    K -- 否 --> N[拒答并记录知识缺口]
    K -- 是 --> LA[可选 LLM 依据片段作答；否则返回命中原文]
```

`POST /api/ask` 是主入口。产品范围可来自页面选择、问题中的产品名称或会话上下文；版本随产品范围确定。含简单追问词的问题会拼接上一轮用户问题。FAQ 匹配会参考意图类别、关键英文词、字符向量相似度和二元字符覆盖率；片段检索按同一产品、同一版本过滤，返回最多 4 条候选，使用向量相似度与字符重合度排序。低于当前演示阈值 `0.16` 或未通过英文关键词检查时拒答。

命中 FAQ 时将保存的答案作为事实答案返回。未命中 FAQ 但片段足够相关时，若设置了 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL`，后端会把命中片段交给兼容 Chat Completions 的服务；未设置或调用失败时返回命中片段原文。API 的 `answer` 保留事实答案，聊天界面展示的 `display_answer` 仅增加口语化引导，不改变事实内容；`suggested_questions` 从同产品、同版本的 FAQ 中选择最多两个后续问题。回答还附带来源、相关度、状态、会话 ID 和消息 ID。退款、投诉等关键词触发转人工；资料不足的问题进入 `unanswered`，供人工补充。

模型 Prompt 可以在独立“知识配置”界面编辑。自定义内容保存在 `settings`，新模型请求会立即使用它；删除自定义配置后恢复读取 `prompts/answer.txt`。页面会显示模型环境变量是否已配置。这个 Prompt 只参与上述模型调用，FAQ 答案和无模型时的固定话术不会受其影响。

## 6. 数据模型

| 表 | 主要内容 | 关系或用途 |
| --- | --- | --- |
| `products` | 产品 ID、名称、别名 | 产品范围的根节点。 |
| `documents` | 产品、版本、类别、标题、来源、清洗报告 | 一份导入资料或人工 FAQ。 |
| `document_texts` | 清洗后的完整文字 | 与 `documents` 一对一，供再次整理 FAQ。 |
| `chunks` | 文本片段及向量 | 按产品和版本检索；删除文档时级联删除。 |
| `faqs` | 问题、答案、类别、来源、生成类型及问题向量 | 优先回答的结构化问答；删除文档时级联删除。 |
| `sessions` | 当前会话的产品、版本和创建时间 | 保存会话范围。 |
| `messages` | 用户与助手消息、回答状态、产品 ID | 会话历史与咨询统计。 |
| `unanswered` | 无答案问题、产品、版本、解决时间 | 知识缺口列表。 |
| `handoffs` | 转人工摘要和状态 | 敏感业务或冲突答案的记录。 |
| `feedback` | 对具体助手消息的正负评价 | 同一消息只保留一条当前评价。 |
| `settings` | 当前自定义模型 Prompt | 无自定义值时读取 `prompts/answer.txt`。 |
| `training_runs` | 每次按需整理的时间、范围、扫描资料数、新增问答数和整理后问答总数 | 绘制问答整理曲线；不代表模型参数训练。 |

`chunks` 和 `faqs` 都有 `(product_id, version)` 索引。问答类型主要有文档显式问答、规则或章节问答、按需整理问答以及人工问答。数据库初始化时会为旧库补充新增字段。

## 7. 主要 API

| 接口 | 作用 |
| --- | --- |
| `GET /api/products`、`GET /api/products/featured`、`GET /api/products/catalog`、`GET /api/products/search` | 产品选择、热门产品和搜索。 |
| `POST /api/products` | 新建或更新产品。 |
| `POST /api/documents/preview` | 文件清洗、片段与候选 QA 预览，不写库。 |
| `POST /api/documents`、`GET /api/documents`、`DELETE /api/documents/{id}` | 导入、查看和删除资料。 |
| `GET /api/faqs`、`POST /api/faqs/train`、`POST /api/faqs/manual` | 查看、整理和人工补充问答。 |
| `POST /api/ask` | 提问并返回答案、状态与来源。 |
| `POST /api/gaps/{id}/answer` | 为知识缺口补充答案。 |
| `POST /api/feedback` | 对指定回答提交“有帮助 / 没帮助”评价。 |
| `GET /api/prompt`、`PUT /api/prompt`、`DELETE /api/prompt` | 查看、保存和恢复默认模型 Prompt。 |
| `GET /api/stats`、`GET /api/handoffs` | 查看统计、知识缺口和转人工记录。 |
| `GET /api/evaluation` | 在当前 SQLite 数据库副本上运行固定样例，返回问答整理历史、混淆矩阵、检索命中率@k 和案例对比，不写入正式咨询记录。 |

FastAPI 自动接口文档位于 `/docs`。

## 8. 运行与边界

本地运行可使用启动脚本，或安装 `requirements.txt` 后执行 `uvicorn app.main:app --reload`。Windows 的 `.bat` 入口调用 PowerShell 引导脚本：优先复用可用的 `.venv`，否则通过启动器、注册表、常见目录和 PATH 枚举 Python 3.9+ 并逐个尝试，升级兼容的 pip，校验依赖及应用模块导入；都不可用且未尝试过 3.11 时通过 `winget` 安装 Python 3.11。Python 探测代码避免嵌入双引号，兼容 PowerShell 5.1 原生命令传参；`start_windows.bat --setup-only` 仅准备环境、不启动服务。Python 3.9～3.14 的 Windows x64 依赖解析已通过；同版本 Windows 启动与测试矩阵见 `.github/workflows/windows-startup.yml`，本次 macOS 环境尚未执行该工作流。macOS 的 `.command` 入口执行相同的环境检查；缺少 Python 时通过 Homebrew 安装 Python 3.11，缺少 Homebrew 时先调用官方安装脚本。`run_server.py` 会在 `127.0.0.1` 的 8000 至 8010 端口中选择可用端口，并打印实际数据库路径。启动脚本只在数据库没有资料时调用 `seed.py --if-empty` 导入演示数据；手动执行 `seed.py` 会重建演示资料。新增 SQLite 文件被 Git 忽略，历史已跟踪文件需单独核对；提交包明确排除运行数据库，跨机器迁移需另行复制该文件，详见 README。

当前实现面向课堂演示：没有管理员鉴权、权限隔离、限流或正式工单系统；字符基线与新增 FAISS 精确检索均面向小规模资料，语义模式使用独立预训练 Embedding。可选 LLM 只用于片段回答，现有代码没有逐句忠实度校验。上线前需要补充权限和审核、检索质量评估、文档 OCR、冲突治理及运行监控。

## 2026-11-03：课程 RAG 链路补充
新增语义模块、索引表、回答模式、接口、实验数据流与一致性策略详见 [RAG 完整链路补充设计](docs/RAG_IMPLEMENTATION.md)。本章与该补充设计优先解释新增功能；前文字符向量与 FAQ 章节仍描述保留的基线路径。

新增 `semantic_vectors(chunk_id, identity, content_hash, vector, dimension)`，按模型空间隔离并随片段级联删除；持久化归一化 float32 向量，按产品和版本构建内存 FAISS IndexFlatIP。索引按需增量补建，模型推理放在会话写事务之前。该索引是精确搜索，未引入 ANN 或常驻向量服务。

新增 GET /api/rag/status 与 POST /api/rag/reindex。问答结果新增 retriever、generation_mode、generation_error。严格模型模式绕过 FAQ 快捷回答，服务异常不伪装成生成成功；自动模式保留原兼容路径。

完整实验使用 6 份虚构文档、45 个问题，在独立临时库中比较相同语料的 hash_extractive 与 semantic_extractive。真实结果与图表位于 reports/latest，当前分别通过 33/45 与 38/45；新增语义方案存在拒答退化，见 [实际失败分析](docs/FAILURE_ANALYSIS.md)。关键词匹配、证据命中与人工忠实度/相关性分开统计。人评尚未完成时留空，不用检索分数替代。

真实 LLM 实验入口已经实现，实际质量结果需配置用户指定服务后运行。GraphRAG、微调、在线逐事实校验、生产鉴权和正式人工工单服务未实现，也不是本次基础课程闭环的前置条件。

## 免费 API 下拉配置（2026-11-03）

知识配置页已新增服务商与模型下拉框，默认预选 OpenRouter 免费路由；另有 Groq Free Plan、Gemini 免费层及自定义兼容 API。填入自己的 Key 后保存并测试，无需改源码或重启。额度以账户和官方政策为准，不自动切换收费模型。

配置由 app/llm_config.py 管理，密钥保存在数据库旁的 *.llm.json 本机文件，不写入 SQLite、不回显、不进入提交包。配置接口为 GET/PUT/DELETE /api/llm/config；POST /api/llm/test 仅发送固定测试短句。网页配置优先于环境变量；清除后恢复环境变量方式。benchmark.py --with-llm 可读取已保存服务，离线回归禁止远程调用。

完整操作、限制与官方链接见 [免费 API 配置说明](docs/FREE_API_SETUP.md)。本次已完成协议与错误路径测试，真实平台连通性需要用户自备 Key 后验证。
