"""Run an experiment on the LangSmith dataset.

    python -m eval.run_experiment v1    # before (basic prompts)
    python -m eval.run_experiment v2    # after (improved prompts)
"""
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

from langsmith import Client  # noqa: E402

from agent.graph import build_graph  # noqa: E402
from eval.create_dataset import DATASET_NAME  # noqa: E402
from eval.evaluators import answer_quality, classification, link_no_prices  # noqa: E402


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "v2"
    os.environ["PROMPT_VERSION"] = version
    graph = build_graph()

    def target(inputs: dict) -> dict:
        # runs until the interrupt in human_review (or until END for non price emails)
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        state = graph.invoke(dict(inputs), config)
        return {
            "is_price_inquiry": state.get("is_price_inquiry"),
            "draft": state.get("draft", ""),
            "attempts": state.get("attempts", 0),
        }

    Client().evaluate(
        target,
        data=DATASET_NAME,
        evaluators=[classification, link_no_prices, answer_quality],
        experiment_prefix=f"photo-agent-{version}",
        metadata={"prompt_version": version},
        max_concurrency=1,  # gentle on Gemini free-tier rate limits
    )


if __name__ == "__main__":
    main()
