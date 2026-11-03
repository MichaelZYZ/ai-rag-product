# 领域知识库智能问答系统

面向产品文档与校园办事资料的 RAG 问答演示，支持文档导入、产品/版本隔离、来源展示、FAQ、多轮追问、语义检索和可选 LLM 生成。演示语料是自建虚构数据。

## 启动

- Windows：双击 **start_windows.bat**。
- macOS：双击 **start_mac.command**，或运行 `./start_mac.command`。
- 打开启动终端打印的地址，通常为 `http://127.0.0.1:8000`；端口被占用时自动选择其他端口。

启动器安装基础依赖，并仅在空库中导入演示资料。基础运行需要 Python 3.9+。手动启动：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m scripts.seed --if-empty
python run_server.py
```

Windows 手动运行时使用 `.venv\Scripts\python.exe`，或先激活对应虚拟环境。

## 免费 API 与语义检索

进入 **知识配置 → 免费 API 与模型选择**，下拉选择 OpenRouter（默认免费路由）、Groq、Gemini 或自定义服务，填入自己的 API Key 后保存并测试。默认启用“知识库回答不了时调用当前模型”：外部通用参考会单独标记来源、服务商与实际响应模型，不作为已验证产品资料，原知识缺口仍可手动补充。免费额度以账户为准，不自动切换收费模型。详见[免费 API 操作说明](docs/guides/FREE_API_SETUP.md)。

默认使用字符检索基线。启用语义 Embedding + FAISS 时，先安装可选依赖，再设置检索模式；详细的 Windows 与 macOS 步骤见[业务操作手册](docs/guides/BUSINESS_OPERATIONS.md)。

```bash
python -m pip install -r requirements/rag.txt
export RAG_RETRIEVER=semantic
python -m scripts.reindex
python run_server.py
```

## 目录

```text
app/                 后端、检索逻辑和网页
scripts/             初始化、评估、索引、文档生成与打包命令
requirements/        语义 RAG 和文档生成的可选依赖
prompts/             模型提示词
data/                教学语料、评估题与本机运行数据
docs/
  guides/            项目说明、操作、API 配置和评估说明
  design/            架构、核心设计及已有设计 Word
  analysis/          实际失败案例分析
  course/            作业原文及提交核对
  exports/           生成的 Word 和 PPT
reports/latest/      已运行实验的结果、图表和评分表
tests/               自动化测试与 Windows 检查
dist/                生成的提交压缩包（不进入 Git）
```

文档入口：[文档索引](docs/README.md) · [完整项目说明](docs/guides/PROJECT_OVERVIEW.md) · [系统设计](docs/design/SYSTEM_DESIGN.md) · [Word/PPT 文件](docs/exports/README.md)。

## 维护命令

以下命令均在项目根目录执行。维护脚本统一使用 `python -m scripts.<名称>`，避免直接运行子目录文件造成导入失败。

| 操作 | 命令 |
| --- | --- |
| 初始化空知识库 | `python -m scripts.seed --if-empty` |
| 重建演示与校园样例 | `python -m scripts.seed --course` |
| 补建语义索引 | `python -m scripts.reindex` |
| 8 题离线回归 | `python -m scripts.evaluate` |
| 45 题检索对比 | `python -m scripts.benchmark` |
| 包含真实模型实验 | `python -m scripts.benchmark --with-llm --output reports/llm-run` |
| 汇总人工评分 | `python -m scripts.review_results reports/latest` |
| 检查文档链接与来源 | `python -m scripts.update_documentation` |
| 生成实验图表 | `python -m scripts.plot_results reports/latest` |
| 更新 Word 与 PPT | `python -m scripts.build_deliverables` |
| 生成代码与材料 zip | `python -m scripts.package_project` |
| 自动化测试 | `python -m unittest discover -s tests` |

文档与图表生成另需安装 `python -m pip install -r requirements/docs.txt`。真实模型实验需先配置服务；人工评分不会自动填满。45 题离线结果和局限见[实验结果](reports/latest/RESULTS.md)与[失败分析](docs/analysis/FAILURE_ANALYSIS.md)。

## 数据与迁移

运行数据库继续使用 `data/rag.sqlite3`，可由 `RAG_DB` 指定；本机模型配置与密钥位于数据库旁的 `*.llm.json`。目录整理没有移动这些运行数据，也没有清除已下载模型。模型缓存默认在 `.cache/huggingface/`。

提交压缩包生成到 `dist/rag_course_project.zip`，排除运行数据库、密钥文件、虚拟环境和缓存。历史数据库曾进入 Git，忽略规则不会自动移除已跟踪内容；跨机器迁移正式资料时应单独备份数据库。`scripts.seed --course` 会重建同产品、版本和来源的演示资料，请勿把同名演示来源作为正式数据保存。
