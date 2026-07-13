"""Prompt templates. Structure borrowed from MAD (player meta-prompt +
moderator JSON verdict). Unlike MAD, context is the **full shared document**
(instead of each agent's private memory), so every template carries `doc_text`.
"""
from __future__ import annotations


# ---- Debater ----

def agent_turn(role: str, topic: str, language: str, doc_text: str,
               word_limit: int, author: str) -> str:
    return f"""{role}

You are taking part in a shared-document roundtable debate. All contributions are
written into one Markdown document. You do NOT have to agree with others — the goal
is to think the problem through and converge on the best answer.

Topic: {topic}

Here is the **current full content** of the document:
<document>
{doc_text}
</document>

It is now your turn (you sign as: {author}). Requirements:
- Reply in {language}, within {word_limit} words.
- Read the whole document, then add a NEW point or explicitly respond to / rebut a
  specific earlier remark (you may name who said it). Do not repeat what's already there.
- Output ONLY the body of your contribution: no `## [xxx]` heading line, no restating
  the document, do not speak for others (the signature is added for you).
- Speak only as {author}."""


# ---- Organizer (MAD's moderator) ----

def organizer_opening(role: str, topic: str, language: str,
                      doc_text: str, speakers: list[str]) -> str:
    return f"""{role}

You are chairing a roundtable. Participants: {", ".join(speakers)}.

Topic: {topic}

Current document content:
<document>
{doc_text}
</document>

Please kick off the discussion: in {language}, briefly frame the topic and invite each
participant to put forward the points THEY think matter most. Do NOT prescribe the agenda,
the decision points, or the answers — let the participants surface the substance themselves.
Keep it under 120 words. Output only the body — no heading line, do not speak for others."""


def organizer_review(role: str, topic: str, language: str,
                     doc_text: str, round_no: int, max_rounds: int) -> str:
    return f"""{role}

Topic: {topic}
This is the full document after round {round_no}/{max_rounds}:
<document>
{doc_text}
</document>

As the organizer, assess the discussion: has it reached a clear enough conclusion on
the core question? First write a short summary in {language} (consensus and the main
disagreement, under 120 words). Then, **on a final separate line**, output EXACTLY this
JSON (nothing else after it):
{{"consensus_reached": "Yes or No", "reason": "one-line reason", "current_answer": "best current conclusion"}}
consensus_reached = Yes means the debate can converge and end; No means one more round is needed."""


def organizer_final(role: str, topic: str, report_language: str, doc_text: str) -> str:
    return f"""{role}

Topic: {topic}
Here is the complete discussion document:
<document>
{doc_text}
</document>

The debate is over. As the organizer, write a COMPREHENSIVE FINAL REPORT that consolidates
everything discussed. Write the ENTIRE report in {report_language} (even if the debate above
was in another language). Use this structure with Markdown headings:

### 概述
One paragraph: the topic and what was decided overall.

### 各决策点结论
For EVERY decision point raised (not only the ones that fully converged), give: the conclusion
reached, who argued what, and any concession that settled it. If a point was left unresolved,
say so explicitly and state the open question.

### 关键分歧与如何化解
The sharpest disagreements and how (or whether) they were resolved.

### 最终可执行建议
A concrete, actionable list — specific enough to implement (files/changes where relevant).

### 未决事项
Anything still open or deferred.

Be specific and faithful to the actual arguments above. Output only the report body."""
