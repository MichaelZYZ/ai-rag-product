# 项目文档索引

## 使用与维护

- [完整项目说明](guides/PROJECT_OVERVIEW.md)
- [业务操作手册](guides/BUSINESS_OPERATIONS.md)
- [免费 API 下拉配置](guides/FREE_API_SETUP.md)
- [实验复现与质量评分](guides/EVALUATION_GUIDE.md)
- [项目答辩问答指南](guides/PROJECT_QA_GUIDE.md)

## 设计与分析

- [架构说明](design/ARCHITECTURE.md)
- [系统与核心实现设计](design/SYSTEM_DESIGN.md)
- [语义 RAG 补充设计](design/RAG_IMPLEMENTATION.md)
- [实际失败案例分析](analysis/FAILURE_ANALYSIS.md)
- [已有产品问答方案 Word](design/product_qa_robot_design.docx)
- [已有架构与实现设计 Word](design/产品知识库问答系统_架构与核心实现设计文档.docx)

## 课程与交付

- [期末大作业要求原文](course/2026_期末大作业.docx)
- [提交核对与待团队填写项](course/SUBMISSION_CHECKLIST.md)
- [生成的 Word/PPT 索引](exports/README.md)
- [实际实验结果](../reports/latest/RESULTS.md)
- [验证记录](../reports/latest/VALIDATION.md)

Markdown 是维护来源；docs/exports 中的 Word/PPT 通过 `python -m scripts.build_deliverables` 更新。运行命令、目录职责和数据迁移见[项目首页](../README.md)。

根目录原有说明、操作和设计文档已分别归入 guides 与 design；原有评估、初始化和索引脚本已归入 scripts，使用 `python -m scripts.<名称>` 执行。根目录 Windows/macOS 启动入口保持原名。数据库、密钥文件与模型缓存路径保持不变。
