from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from agent.nodes import (
    check_draft,
    classify,
    draft_reply,
    fetch_email,
    human_review,
    route_after_check,
    route_after_classify,
    send_email,
)
from agent.state import EmailState


def build_graph(checkpointer=None):
    builder = StateGraph(EmailState)

    builder.add_node("fetch_email", fetch_email)
    # nodes that call Gemini: retry on network errors (e.g. a filter dropping the connection)
    llm_retry = RetryPolicy(max_attempts=4, initial_interval=5, retry_on=Exception)
    builder.add_node("classify", classify, retry_policy=llm_retry)
    builder.add_node("draft_reply", draft_reply, retry_policy=llm_retry)
    builder.add_node("check_draft", check_draft, retry_policy=llm_retry)
    builder.add_node("human_review", human_review)
    builder.add_node("send_email", send_email)

    builder.add_edge(START, "fetch_email")
    builder.add_edge("fetch_email", "classify")

    # branch: only price inquiries continue
    builder.add_conditional_edges("classify", route_after_classify,
                                  {"draft": "draft_reply", "end": END})

    builder.add_edge("draft_reply", "check_draft")

    # loop: a bad draft goes back to draft_reply (up to MAX_ATTEMPTS)
    builder.add_conditional_edges("check_draft", route_after_check,
                                  {"retry": "draft_reply", "ok": "human_review"})

    builder.add_edge("human_review", "send_email")
    builder.add_edge("send_email", END)

    # a checkpointer is required for interrupt() to pause and resume
    return builder.compile(checkpointer=checkpointer or MemorySaver())
