"""Create a mail.tm disposable inbox for the HuggingFace experiment.
Uses the framework's TempMailVerifier. Saves inbox creds to state/hf_experiment_mail.json.
"""
import json
import sys

sys.path.insert(0, r"C:\god_ai\api_money_bot_complete\universal_harvester")
from utils.email_verifier import TempMailVerifier  # noqa: E402

tv = TempMailVerifier()
email = tv.create_inbox()

out = {
    "email": email,
    "mail_tm_password": tv.password,
    "mail_tm_token": tv.token,
    "account_id": tv.account_id,
}
with open(r"d:\omniroute-monetizer\state\hf_experiment_mail.json", "w") as f:
    json.dump(out, f, indent=2)
print("inbox created:", email)
print("saved to state/hf_experiment_mail.json")
