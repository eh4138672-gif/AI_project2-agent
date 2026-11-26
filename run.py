"""Run the agent on sample emails, with a human approval stop before sending.

    python run.py                                   # all emails in sample_emails/
    python run.py sample_emails/01_wedding_price.json
    python run.py --draw                            # save the graph diagram to graph.md
"""
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from langgraph.types import Command  # noqa: E402

from agent.graph import build_graph  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def ask_human(payload: dict) -> dict:
    print("\n" + "=" * 60)
    print(f"To: {payload['sender']}  |  Re: {payload['subject']}  |  attempts: {payload['attempts']}")
    if payload["open_problems"]:
        print(f"!! Checker still found problems: {payload['open_problems']}")
    print("-" * 60)
    print(payload["draft"])
    print("=" * 60)

    while True:
        choice = input("[s]end / [e]dit / [c]ancel: ").strip().lower()
        if choice in ("s", "send"):
            return {"decision": "send"}
        if choice in ("c", "cancel"):
            return {"decision": "cancel"}
        if choice in ("e", "edit"):
            print("Type the new text. Finish with a line containing only END:")
            lines = []
            while (line := input()) != "END":
                lines.append(line)
            return {"decision": "edit", "draft": "\n".join(lines)}


def process(graph, email_file: Path):
    # the run and the resume must use the same thread_id
    config = {
        "configurable": {"thread_id": str(uuid.uuid4())},
        "run_name": f"email:{email_file.stem}",
    }
    print(f"\n>>> {email_file.name}")
    result = graph.invoke({"email_file": str(email_file)}, config)

    if "__interrupt__" not in result:
        print("Not a price inquiry -> graph ended, nothing to send.")
        return

    answer = ask_human(result["__interrupt__"][0].value)
    result = graph.invoke(Command(resume=answer), config)
    if answer["decision"] == "cancel":
        print("Cancelled - nothing was sent.")
    else:
        print("Saved to outbox/.")


def main():
    graph = build_graph()

    if "--draw" in sys.argv:
        Path("graph.md").write_text(
            "```mermaid\n" + graph.get_graph().draw_mermaid() + "\n```\n", encoding="utf-8"
        )
        print("Graph saved to graph.md")
        return

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    files = [Path(a) for a in args] or sorted(Path("sample_emails").glob("*.json"))
    for f in files:
        process(graph, f)


if __name__ == "__main__":
    main()
