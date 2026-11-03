# 验证记录（2026-11-03）

- 当前 macOS 环境的 66 项自动化测试通过，新增外部模型回退、来源与实际模型标识、持久化、开关及额度错误验证。详见 EXTERNAL_FALLBACK.md；先前清洗与补充流程见 KNOWLEDGE_OPTIMIZATION.md。
- 原 scripts/evaluate.py 的 8 个固定样例全部通过。
- 实际下载的本地多语言模型 + FAISS：45 题中字符原文基线通过 33 题，语义原文方案通过 38 题。原始逐题结果、失败项与指标见 benchmark.json。
- 在临时数据库通过真实 API 路径完成 31 条语义向量补建，状态接口确认 31/31；“纸质在读证明去哪里领取？”返回行政楼 102 室并标记为 extractive。
- 页面 JavaScript 通过 node --check；未声称完成浏览器交互回归。
- 依赖通过 pip check。准确依赖版本见 environment.json；新增可选依赖未在 Windows 矩阵中实际运行。
- 四份新 Word 均可由 python-docx 重新打开，XML 与 ZIP 校验通过；现有两份设计 Word 的补充标题各出现一次，原架构文档中的 10 个媒体文件完整保留。
- PPT 技术草稿 13 页，全部图形边界位于页面内；未声称完成 Office 人工排版审阅。
- 真实 LLM 实验未执行，没有完整服务配置；人工忠实度/相关性评分未填写，quality_scores.json 保留 null 与 0 覆盖率。协议/异常测试中的受控模型响应不作为真实生成质量证据。
- 免费 API 下拉及模型目录根据 2026-11-03 官方资料核对。受控连接测试覆盖 Gemini 请求地址、模型与鉴权，OpenRouter 默认及跨服务密钥隔离，429 额度提示和本地保存后实验读取；没有用真实用户 Key 发起平台调用。新增前端脚本通过 node --check。

## 目录整理后的复核（2026-11-03）

- 维护脚本移至 scripts，以 `python -m scripts.<名称>` 执行；48 项测试与 8 题回归通过。
- 文档按 guides、design、analysis、course、exports 归类；本地文档链接检查通过，Word/PPT 按新路径重新生成。
- 根目录 Windows/macOS 启动入口保留，脚本内部路径和 Windows CI 同步更新；未声称本机执行了 Windows 启动。
- macOS 启动脚本在临时数据库、禁用下载的条件下完成 --setup-only 检查；基础环境与演示初始化通过。
- 可选依赖移至 requirements/rag.txt 和 requirements/docs.txt，嵌套依赖路径解析通过。
- 运行数据库、密钥配置与模型缓存未迁移。Finder 和 Office 临时文件归档到 .cache/cleanup/2026-11-03，未混入交付包。
- 整理后的 zip 解压到含空格的新目录后，文档检查及 8 题回归通过；包内清单摘要校验通过，包含新脚本、可选依赖与文档，不含密钥和运行数据库。
