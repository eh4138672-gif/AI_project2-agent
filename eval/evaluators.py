from pydantic import BaseModel, Field

from agent.nodes import find_prices, get_llm, has_website_link, load_studio


def classification(outputs: dict, reference_outputs: dict) -> dict:
    """Evaluator 1 (code): is is_price_inquiry correct?"""
    correct = outputs.get("is_price_inquiry") == reference_outputs["is_price_inquiry"]
    return {"key": "classification", "score": int(correct)}


def link_no_prices(outputs: dict, reference_outputs: dict) -> dict:
    """Evaluator 2 (code): the website link is in the draft and no prices were written."""
    if not reference_outputs["is_price_inquiry"]:
        return {"key": "link_no_prices", "score": None, "comment": "not a price inquiry"}
    draft = outputs.get("draft") or ""
    if not draft:
        return {"key": "link_no_prices", "score": 0, "comment": "no draft was written"}
    problems = []
    if not has_website_link(draft):
        problems.append("missing website link")
    if prices := find_prices(draft):
        problems.append(f"wrote prices {prices}")
    return {"key": "link_no_prices", "score": int(not problems),
            "comment": ", ".join(problems) or "link included, no prices"}


class Judgement(BaseModel):
    score: int = Field(description="1 if the reply is good, 0 otherwise")
    reasoning: str = Field(description="Short explanation")


JUDGE_PROMPT = """You are grading a reply written by a photography studio to a customer who asked
about prices. The studio wants every such reply to send the customer to its website
({url}), where the prices and the portfolio are.

Customer email:
{email}

Reply:
{draft}

Give score=1 only if the reply is warm and nicely worded, relates personally to what the
customer asked about, clearly says the prices and portfolio are at the link, invites them to
get back in touch, is in the customer's language, and does not invent prices or promise dates.
Otherwise score=0."""


def answer_quality(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """Evaluator 3 (LLM-as-judge): is the reply well worded and does it send to the website?"""
    if not reference_outputs["is_price_inquiry"]:
        return {"key": "answer_quality", "score": None, "comment": "not a price inquiry"}
    draft = outputs.get("draft") or ""
    if not draft:
        return {"key": "answer_quality", "score": 0, "comment": "no draft was written"}
    result = get_llm().with_structured_output(Judgement).invoke(JUDGE_PROMPT.format(
        url=load_studio()["website_url"],
        email=f"Subject: {inputs['subject']}\n\n{inputs['body']}",
        draft=draft,
    ))
    return {"key": "answer_quality", "score": result.score, "comment": result.reasoning}
