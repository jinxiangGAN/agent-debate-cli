"""Prompt 模板，结构借鉴 MAD（player meta-prompt + moderator 的 JSON 裁决）。

和 MAD 的区别：这里不靠每个 agent 的私有记忆，而是把**共享文档全文**当上下文
（对应 MAD 的 broadcast），所以每个模板都会带上 `doc_text`。
"""
from __future__ import annotations


# ---- 讨论者 ----

def agent_turn(role: str, topic: str, language: str, doc_text: str,
               word_limit: int, author: str) -> str:
    return f"""{role}

你正在参加一场"共享文档"式的圆桌讨论。所有发言都写在同一份 Markdown 文档里，
不必强行认同别人的观点——目标是把问题讨论清楚、逼近正确答案。

议题：{topic}

下面是该文档的**当前完整内容**：
<文档>
{doc_text}
</文档>

现在轮到你（署名：{author}）发言。要求：
- 用 {language}，{word_limit} 字以内。
- 读完整份文档，提出新论点，或明确回应/反驳前面某条发言（可点名是谁说的），不要重复已有内容。
- **只输出你要追加的正文**：不要写 `## [xxx]` 这类标题行、不要复述文档、不要替别人发言（署名会由系统添加）。
- 只以 {author} 的身份发言。"""


# ---- 组织者（对应 MAD 的 moderator）----

def organizer_opening(role: str, topic: str, language: str,
                      doc_text: str, speakers: list[str]) -> str:
    return f"""{role}

你主持一场圆桌讨论，参与者：{", ".join(speakers)}。

议题：{topic}

当前文档内容：
<文档>
{doc_text}
</文档>

请你开场：用 {language} 把议题拆解成 2-3 个讨论要点，并说明希望各位重点回应哪些方面。
{"" }120 字以内。只输出正文，不要写标题行，不要替别人发言。"""


def organizer_review(role: str, topic: str, language: str,
                     doc_text: str, round_no: int, max_rounds: int) -> str:
    return f"""{role}

议题：{topic}
这是第 {round_no}/{max_rounds} 轮讨论后，共享文档的完整内容：
<文档>
{doc_text}
</文档>

你作为组织者，评估目前的讨论：是否已经就核心问题形成足够清晰的结论。
先用 {language} 写一段小结（概括共识与主要分歧，120 字以内），
然后**在最后另起一行**，严格输出如下 JSON（不要有多余内容）：
{{"consensus_reached": "Yes 或 No", "reason": "一句话理由", "current_answer": "目前最可能的结论"}}
consensus_reached 为 Yes 表示讨论可以收敛结束，No 表示还需再讨论一轮。"""


def organizer_final(role: str, topic: str, language: str, doc_text: str) -> str:
    return f"""{role}

议题：{topic}
以下是完整的讨论文档：
<文档>
{doc_text}
</文档>

讨论结束。请你用 {language} 给出最终收尾：综合各方观点，输出一个清晰、可执行的结论。
可以分点，但要具体。这段话代表本次圆桌的最终产出。只输出正文，不要写标题行。"""
