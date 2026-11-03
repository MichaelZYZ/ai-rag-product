# 实验结果

本文件由 benchmark.py 根据实际运行结果生成。关键词匹配不等同于忠实度。

| 方案 | 通过/总数 | 状态准确率 | 答案关键词准确率 | Hit@1（证据片段） | LLM 回答数 |
| --- | --- | --- | --- | --- | --- |
| hash_extractive | 33/45 | 0.8444 | 0.6944 | 0.8056 | 0 |
| semantic_extractive | 38/45 | 0.9111 | 0.9167 | 0.9167 | 0 |

忠实度与答案相关性：待人工评阅 human_review.csv，空白不计为零分或满分。

## 未执行方案

- llm：未请求真实模型实验；配置服务后加 --with-llm

## 实际失败案例

### hash_extractive / extended_08

问题：任务能设置到期时间吗？
预期：answered / 截止日期
实际：no_answer / 现有产品资料中暂未找到相关说明，请补充问题或联系人工客服。
证据检索 Hit@1：True；生成方式：rule

### hash_extractive / extended_13

问题：本科生在 2025 年可以借多少本？
预期：answered / 6 本
实际：no_answer / 现有产品资料中暂未找到相关说明，请补充问题或联系人工客服。
证据检索 Hit@1：True；生成方式：rule

### hash_extractive / extended_17

问题：怎么在网站上办理续借？
预期：answered / 我的借阅、续借
实际：no_answer / 现有产品资料中暂未找到相关说明，请补充问题或联系人工客服。
证据检索 Hit@1：True；生成方式：rule

### hash_extractive / extended_20

问题：2025 年续借能延长几天？
预期：answered / 7 天
实际：no_answer / 现有产品资料中暂未找到相关说明，请补充问题或联系人工客服。
证据检索 Hit@1：True；生成方式：rule

### hash_extractive / extended_21

问题：图书馆工作日几点开放？
预期：answered / 08:00、22:00
实际：answered / 示例校园证明办理(自建虚构教学语料)
电子在读证明在审核通过后 2 个工作日内提供下载,节假日不计入工作日。
证据检索 Hit@1：False；生成方式：extractive

### hash_extractive / extended_22

问题：图书馆周末几点开放？
预期：answered / 09:00、18:00
实际：no_answer / 现有产品资料中暂未找到相关说明，请补充问题或联系人工客服。
证据检索 Hit@1：True；生成方式：rule

### hash_extractive / extended_23

问题：图书弄丢了怎么处理？
预期：answered / 服务台、挂失
实际：no_answer / 现有产品资料中暂未找到相关说明，请补充问题或联系人工客服。
证据检索 Hit@1：False；生成方式：rule

### hash_extractive / extended_24

问题：在读证明在哪里申请？
预期：answered / 学生服务平台、证明申请
实际：answered / 示例校园证明办理(自建虚构教学语料)
电子在读证明不收费,纸质在读证明每份收费 5 元。
证据检索 Hit@1：False；生成方式：extractive

### hash_extractive / extended_25

问题：电子在读证明多久可以下载？
预期：answered / 2 个工作日
实际：answered / 示例校园证明办理(自建虚构教学语料)
电子在读证明不收费,纸质在读证明每份收费 5 元。
证据检索 Hit@1：False；生成方式：extractive

### hash_extractive / extended_28

问题：纸质在读证明去哪里领取？
预期：answered / 行政楼 102 室
实际：answered / 示例校园证明办理(自建虚构教学语料)
电子在读证明不收费,纸质在读证明每份收费 5 元。
证据检索 Hit@1：False；生成方式：extractive

### hash_extractive / extended_29

问题：纸质在读证明可以让朋友代领吗？
预期：answered / 不能代领
实际：answered / 示例校园证明办理(自建虚构教学语料)
电子在读证明不收费,纸质在读证明每份收费 5 元。
证据检索 Hit@1：False；生成方式：extractive

### hash_extractive / unanswerable_04

问题：考试周图书馆几点关门？
预期：no_answer / 
实际：answered / 示例校园图书馆规则(自建虚构教学语料)
考试周开放时间另行公告,本指南未提供考试周安排。
证据检索 Hit@1：None；生成方式：extractive

### semantic_extractive / original_05

问题：星云笔记支持语音转写吗？
预期：no_answer / 
实际：answered / 星云笔记 2.0(虚构演示产品)
星云笔记 2.0 支持创建文字笔记和标签。
证据检索 Hit@1：None；生成方式：extractive

### semantic_extractive / original_06

问题：星云笔记价格是多少？
预期：no_answer / 
实际：answered / 星云笔记 2.0(虚构演示产品)
星云笔记 2.0 的单个笔记最多支持 20 个标签。
证据检索 Hit@1：None；生成方式：extractive

### semantic_extractive / extended_13

问题：本科生在 2025 年可以借多少本？
预期：answered / 6 本
实际：answered / 示例校园图书馆旧规则(自建虚构教学语料)
普通图书借期为 21 天,可以续借 1 次,每次延长 7 天。
证据检索 Hit@1：False；生成方式：extractive

### semantic_extractive / extended_15

问题：普通图书可以借多久？
预期：answered / 30 天
实际：answered / 示例校园图书馆规则(自建虚构教学语料)
普通图书可以续借 1 次,每次延长 15 天;已被他人预约的图书不能续借。
证据检索 Hit@1：False；生成方式：extractive

### semantic_extractive / extended_16

问题：参考工具书能带出图书馆吗？
预期：answered / 不能外借
实际：answered / 示例校园图书馆规则(自建虚构教学语料)
续借操作:登录图书馆网站,进入“我的借阅”,选择图书并点击“续借”。
证据检索 Hit@1：False；生成方式：extractive

### semantic_extractive / unanswerable_04

问题：考试周图书馆几点关门？
预期：no_answer / 
实际：answered / 示例校园图书馆规则(自建虚构教学语料)
工作日开放时间为 08:00 至 22:00,周末开放时间为 09:00 至 18:00。
证据检索 Hit@1：None；生成方式：extractive

### semantic_extractive / unanswerable_05

问题：证明可以邮寄到家吗？
预期：no_answer / 
实际：answered / 示例校园证明办理(自建虚构教学语料)
纸质在读证明需要携带学生证到行政楼 102 室领取;不能代领。
证据检索 Hit@1：None；生成方式：extractive

