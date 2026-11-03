# 数据目录

| 文件 | 用途 |
| --- | --- |
| demo_knowledge.json | 原有虚构产品语料 |
| course_knowledge.json | 新增虚构校园办事语料 |
| eval_cases.json | 8 个基础回归问题 |
| eval_extended.json | 45 个扩展评估问题 |
| iphone_11-18_中文产品与使用指南.html | 导入样例，不属于固定实验语料 |
| rag.sqlite3 | 本机运行数据库，保留已有资料与咨询记录 |
| *.llm.json | 本机模型配置与密钥，不随代码包提交 |

目录整理保留了运行数据位置。语料和评估文件进入提交包；数据库、密钥、临时文件被打包脚本排除。缓存模型位于项目的 .cache/huggingface，不在此目录。
