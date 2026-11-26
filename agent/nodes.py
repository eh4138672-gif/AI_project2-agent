import json
import os
import re
from datetime import datetime
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from agent.state import EmailState

ROOT = Path(__file__).resolve().parent.parent
STUDIO_FILE = ROOT / "studio.json"
OUTBOX_DIR = ROOT / "outbox"
MAX_ATTEMPTS = 3


# ---------- helpers ----------

def get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        temperature=0,
    )


def prompt_version() -> str:
    # v1 = basic prompts ("before"), v2 = improved prompts ("after")
    return os.getenv("PROMPT_VERSION", "v2")


def load_studio() -> dict:
    return json.loads(STUDIO_FILE.read_text(encoding="utf-8"))


PRICE_PATTERNS = [
    re.compile(r"(\d[\d,]*)\s*(?:₪|ש\"ח|ש״ח|שקל|שקלים|NIS|ILS)"),
    re.compile(r"₪\s*(\d[\d,]*)"),
]


def find_prices(text: str) -> list[int]:
    """Return every amount in the text that appears next to a currency sign."""
    prices = []
    for pattern in PRICE_PATTERNS:
        for match in pattern.findall(text):
            prices.append(int(match.replace(",", "")))
    return prices


def has_website_link(text: str) -> bool:
    return load_studio()["website_url"].rstrip("/") in text


def message_text(msg) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)


def email_block(state: EmailState) -> str:
    return f"From: {state['sender']}\nSubject: {state['subject']}\n\n{state['body']}"


# ---------- prompts ----------

CLASSIFY_V1 = "Is the following email asking about prices or photography packages?\n\n{email}"

CLASSIFY_V2 = """You classify emails sent to a photography studio.

is_price_inquiry = true ONLY if the sender asks how much something costs, asks for a quote,
or asks what a package / extra includes (wedding, bar mitzvah, family, maternity, newborn,
business headshots, extra hours, albums, video, etc.).
If an email asks about availability AND price, it is a price inquiry.

is_price_inquiry = false for: questions only about a free date / availability, thank-you notes,
invoices and receipts, complaints, job applications (even if they ask about salary),
advertising / spam (even if it mentions prices).

Examples:
- "How much is a wedding shoot?" -> true
- "Do you have 12/1 free for a wedding?" -> false (availability only)
- "Are you free on 20/3, and how much is the premium package?" -> true
- "I'm looking for a job as an assistant, how much do you pay per hour?" -> false
- "Can I get an invoice for last month?" -> false

Email:
{email}"""

DRAFT_V1 = """Write a reply to this customer email. Tell them the prices and our portfolio
are on our website: {url}

Email:
{email}
{feedback}"""

DRAFT_V2 = """You are the photographer of the studio "{studio}", replying to a customer who asked
about prices.

Write a warm, beautifully worded, personal reply:
1. Thank them for reaching out and relate to what they asked about specifically
   (e.g. congratulate on the wedding / the baby / the bar mitzvah).
2. Tell them that all the packages, prices and the portfolio of previous work are on the
   website, and include this exact link on its own line: {url}
3. Invite them to reply or get in touch after looking, and say you'd be happy to help.
4. Do NOT write any price, amount, discount or package detail - those are only on the website.
   Do not promise availability of dates.
5. Reply in the language the customer wrote in, short (up to ~100 words).
6. Sign as "{studio}". Write only the email body, no subject line.

Email:
{email}
{feedback}"""

CHECK_PROMPT = """You review a draft reply of a photography studio to a customer who asked about prices.
The reply should send the customer to the website ({url}) for prices and portfolio.

Customer email:
{email}

Draft reply:
{draft}

Check:
- Is it warm, polite and personal (relates to what the customer asked about)?
- Does it clearly say that prices and the portfolio are on the website?
- Does it avoid writing any prices or promising dates?
Set ok=true if the draft is good enough to send. Otherwise explain briefly in `problems`
what must be fixed."""


class Classification(BaseModel):
    is_price_inquiry: bool = Field(description="True if the email asks about prices or packages")
    reason: str = Field(description="One short sentence explaining the decision")


class DraftReview(BaseModel):
    ok: bool = Field(description="True if the draft can be sent as is")
    problems: str = Field(default="", description="What is missing or wrong. Empty if ok")


# ---------- nodes ----------

def fetch_email(state: EmailState) -> dict:
    """Dev stage: read the email from a json file. (Bonus: replace with Gmail API.)"""
    if state.get("body"):  # already given (e.g. during evaluation)
        return {"attempts": 0, "feedback": ""}
    data = json.loads(Path(state["email_file"]).read_text(encoding="utf-8"))
    return {
        "sender": data["sender"],
        "subject": data["subject"],
        "body": data["body"],
        "attempts": 0,
        "feedback": "",
    }


def classify(state: EmailState) -> dict:
    template = CLASSIFY_V1 if prompt_version() == "v1" else CLASSIFY_V2
    llm = get_llm().with_structured_output(Classification)
    result = llm.invoke(template.format(email=email_block(state)))
    return {"is_price_inquiry": result.is_price_inquiry}


def draft_reply(state: EmailState) -> dict:
    studio = load_studio()
    feedback = ""
    if state.get("feedback"):
        feedback = (
            "\nYour previous draft was rejected. Fix these problems:\n"
            f"{state['feedback']}\n\nPrevious draft:\n{state.get('draft', '')}"
        )
    template = DRAFT_V1 if prompt_version() == "v1" else DRAFT_V2
    prompt = template.format(
        studio=studio["studio_name"],
        url=studio["website_url"],
        email=email_block(state),
        feedback=feedback,
    )
    draft = message_text(get_llm().invoke(prompt)).strip()
    return {"draft": draft, "attempts": state.get("attempts", 0) + 1}


def check_draft(state: EmailState) -> dict:
    url = load_studio()["website_url"]
    problems = []

    # 1) deterministic checks in code: the link is there, and no prices were written
    if not has_website_link(state["draft"]):
        problems.append(f"The website link is missing. Include exactly: {url}")
    prices = find_prices(state["draft"])
    if prices:
        problems.append(f"The draft contains prices {prices}. Remove them - prices are only on the website.")

    # 2) LLM review: tone, personal touch, sends to the website
    review = get_llm().with_structured_output(DraftReview).invoke(
        CHECK_PROMPT.format(url=url, email=email_block(state), draft=state["draft"])
    )
    if not review.ok and review.problems:
        problems.append(review.problems)

    return {"feedback": "\n".join(problems)}


def human_review(state: EmailState) -> dict:
    """Stops the graph and waits for: {"decision": "send"|"edit"|"cancel", "draft": "..."}"""
    answer = interrupt({
        "sender": state["sender"],
        "subject": state["subject"],
        "draft": state["draft"],
        "attempts": state["attempts"],
        "open_problems": state.get("feedback", ""),
    })
    return {
        "decision": answer["decision"],
        "draft": answer.get("draft") or state["draft"],
    }


def send_email(state: EmailState) -> dict:
    """Dev stage: 'send' = save the email to the outbox folder."""
    if state.get("decision") == "cancel":
        return {}
    OUTBOX_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_sender = re.sub(r"[^\w.@-]", "_", state["sender"])
    path = OUTBOX_DIR / f"{stamp}_{safe_sender}.txt"
    path.write_text(
        f"To: {state['sender']}\nSubject: Re: {state['subject']}\n\n{state['draft']}\n",
        encoding="utf-8",
    )
    return {}


# ---------- routers (conditional edges) ----------

def route_after_classify(state: EmailState) -> str:
    return "draft" if state["is_price_inquiry"] else "end"


def route_after_check(state: EmailState) -> str:
    if not state["feedback"] or state["attempts"] >= MAX_ATTEMPTS:
        return "ok"
    return "retry"
