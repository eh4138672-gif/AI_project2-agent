"""Create the LangSmith dataset: each example = email (inputs) + correct answer (outputs).

    python -m eval.create_dataset
"""
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import agent  # noqa: E402,F401  (sets up certificates, see agent/__init__.py)
from langsmith import Client  # noqa: E402

DATASET_NAME = "photo-price-emails"

# is_price_inquiry label for each email in sample_emails/
SAMPLE_LABELS = {
    "01_wedding_price": True,
    "02_family_shoot": True,
    "03_bar_mitzvah": True,
    "04_maternity_newborn": True,
    "05_business": True,
    "06_availability_only": False,
    "07_thanks": False,
    "08_invoice": False,
    "09_job_application": False,
    "10_extra_album": True,
}

# extra examples that exist only in the dataset
EXTRA_EXAMPLES = [
    ({"sender": "promo@courses-example.com", "subject": "מבצע!",
      "body": "קורס צילום למתחילים ב-50% הנחה! רק 499 ש\"ח במקום 998. הירשמו עכשיו."}, False),
    ({"sender": "lior.d@example.com", "subject": "צילומי כלבים",
      "body": "היי, אתם מצלמים גם כלבים? כמה עולה סשן לכלב שלי?"}, True),
    ({"sender": "john.smith@example.com", "subject": "Family session",
      "body": "Hi, how much does a family photo session cost? We are 2 adults and 2 kids."}, True),
    ({"sender": "eran.s@example.com", "subject": "מאוכזב",
      "body": "התמונות הגיעו באיחור של חודש. אני מאוד מאוכזב מהשירות."}, False),
    ({"sender": "maya.t@example.com", "subject": "20/3",
      "body": "יש לכם פנוי ב-20/3? ואם כן, כמה עולה חבילת החתונה הפרימיום?"}, True),
]


def build_examples() -> list[dict]:
    examples = []
    for name, is_price in SAMPLE_LABELS.items():
        email = json.loads(Path("sample_emails", f"{name}.json").read_text(encoding="utf-8"))
        examples.append({"inputs": email, "outputs": {"is_price_inquiry": is_price}})
    for email, is_price in EXTRA_EXAMPLES:
        examples.append({"inputs": email, "outputs": {"is_price_inquiry": is_price}})
    return examples


def main():
    client = Client()
    if client.has_dataset(dataset_name=DATASET_NAME):
        print(f"Dataset '{DATASET_NAME}' already exists - delete it in LangSmith to recreate.")
        return
    dataset = client.create_dataset(DATASET_NAME, description="Emails to a photography studio")
    examples = build_examples()
    client.create_examples(dataset_id=dataset.id, examples=examples)
    print(f"Created '{DATASET_NAME}' with {len(examples)} examples.")


if __name__ == "__main__":
    main()
