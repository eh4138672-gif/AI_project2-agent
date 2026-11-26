from typing import TypedDict


class EmailState(TypedDict, total=False):
    email_file: str          # path to the email json (dev stage input)
    sender: str
    subject: str
    body: str
    is_price_inquiry: bool
    draft: str
    attempts: int
    feedback: str            # what check_draft found missing ("" = draft is ok)
    decision: str            # send / edit / cancel
