# 评估与复现说明

## 数据与实验范围

基础回归使用 data/demo_knowledge.json 与 data/eval_cases.json 中的 8 个问题。新增实验使用同一份产品语料加上 data/course_knowledge.json：共 6 份自建虚构文档，覆盖三个知识库主体及多个版本。校园规则不对应任何真实学校，不得作为真实办事指南。实验不自动导入 iPhone HTML；该文件中的外部事实需要另行核验，不能混入本组自建语料的实验结论。

data/eval_extended.json 固定为 45 个问题，包含可回答题、无答案题和转人工题。每条有唯一 id、问题、产品、版本、预期状态；可回答题另有答案关键词、来源和预期证据。多轮题使用 history 明确记录前文。此规模仍小，适合课堂验证，不能代表生产业务。没有另设开发集，所以本次不针对这组结果调阈值，不宣称泛化性能。

## 运行离线实验

安装基础依赖后运行 `python -m pip install -r requirements-rag.txt`。第一次使用本地 Embedding 会下载模型；默认模型是 sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2。模型在本机推理，实验不调用远程 Embedding API 或 LLM。设置 HF_HOME 可指定模型缓存目录，预先下载后可以设置 HF_HUB_OFFLINE=1 离线使用。

```bash
python benchmark.py --output reports/latest
python review_results.py reports/latest
python -m pip install -r requirements-docs.txt
python scripts/plot_results.py reports/latest
```

benchmark.py 始终创建临时数据库，不清空、导入或修改正式知识库。它以相同语料、题目和抽取式回答模式比较 hash_extractive 与 semantic_extractive，强制绕过 FAQ 直接回答，减少业务快捷路径对检索对比的干扰；FAQ 冲突仍转人工。字符阈值 0.16、语义阈值 0.35 在实验前固定，均未经过独立开发集校准。重跑覆盖指定输出目录，应为需要留档的实验选择新目录。

## 真实模型实验

先在网页保存服务商、模型和 Key，或在当前进程环境设置 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL，再运行 `python benchmark.py --with-llm --output reports/llm-run`。应用不自动读取 .env，.env.example 仅为配置参考。不要在命令历史、截图、报告或代码包中保存密钥。API 应支持 Chat Completions；Base URL 通常带 /v1，代码追加 /chat/completions，实际以服务商文档为准。

此命令额外运行 hash_llm 和 semantic_llm。严格模型模式不把原文回退记为模型生成；调用失败会记录 error 类型与失败数量。没有完整配置的方案会进入 skipped，不能解释为已通过。模型、语料摘要、题目摘要、阈值、运行时间、逐题答案和证据保存在 benchmark.json。报告不包含密钥或服务返回的原始异常信息。

仅应使用已获许可发送的教学语料。benchmark 使用项目内明确标注的虚构语料，正常应用问答则会把当前检索片段发给所配置服务。需要离线部署时保持本地 Embedding，并使用本机 LLM 服务；当前未提供或打包 LLM 权重。

## 指标口径

| 指标 | 计算方式 | 限制 |
| --- | --- | --- |
| 状态准确率 | 预期状态与实际状态一致，且没有生成服务错误 | 不证明答案正确 |
| 答案关键词准确率 | 在预期可回答题中，状态正确且包含全部 expected_terms 的比例 | 同义正确答案可能被误判；多余错误事实可能漏检 |
| 拒答准确率 | 预期 no_answer 的问题中正确拒答的比例 | 需同时看可回答题的错误拒答，避免全部拒答 |
| 证据 Hit@K | 前 K 个片段同时命中预期来源和 expected_evidence | 比仅命中文件严格，仍依赖标注完整性 |
| 平均耗时 | 逐题从历史上下文建立到问答及证据检索的墙钟耗时 | 包含评估额外检索，不等同于在线单次延迟；模型预热和初次建库在计时之外 |
| 忠实度 | 人工逐事实核对实际答案与本次提供证据 | 不是检索分数或关键词命中率 |
| 答案相关性 | 人工核对是否直接、充分回答原问题的条件与目标 | 有来源也可能答非所问 |

原网页的 8 题评估仍保持原口径，并移除子进程的 LLM 配置，适合作为快速回归。完整模型实验应使用 benchmark.py；不能把网页曲线称为模型 loss 或把其状态矩阵称为幻觉评估。

## 人工评阅

human_review.csv 为每个方案、每个问题导出原始答案和本次引用证据。只有 actual_status 为 answered 且无生成错误的记录需要填写两项质量分数。拒答和转人工由状态指标单独评估。faithfulness：2 为所有事实有证据，1 为部分事实缺少证据，0 为核心事实无证据或与证据矛盾。answer_relevance：2 为直接充分回答，1 为部分回答或有明显冗余，0 为答非所问。必须同时填写两项分数、reviewer 与 reason。

`python review_results.py reports/latest` 校验记录摘要、重复项、分数范围和评阅依据，输出 quality_scores.json。分数除以 2 归一化后仅对实际评阅项取平均，并报告覆盖率。空白项保持 null，不冒充人工实验结果。不同实验的评阅表不能混用。建议组员独立评阅再讨论分歧；本项目未伪造组员评分。

## 失败分析与提交

RESULTS.md 自动列出实际失败记录；docs/FAILURE_ANALYSIS.md 解释代表样本的原因与改进方向。新增检索方案的变化必须同时观察正确回答和无答案问题，不能只报告更高的召回率。修改模型、阈值、分块或 Prompt 后，应另存新目录、比较相同样本并重新评阅，不覆盖旧证据。参考 FAISS 官方文档 https://github.com/facebookresearch/faiss/wiki/Getting-started 与模型卡 https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 。
