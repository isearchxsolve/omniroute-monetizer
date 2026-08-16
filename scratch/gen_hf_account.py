"""Generate HF account credentials for the experiment (saved to state/, gitignored)."""
import json
import random
import string

with open(r"d:\omniroute-monetizer\state\hf_experiment_mail.json") as f:
    mail = json.load(f)

rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
account = {
    "email": mail["email"],
    "password": "OmniHf!" + ''.join(random.choices(string.ascii_letters + string.digits, k=12)),
    "username": f"omniroute-hf-{rand}",
    "fullName": f"OmniRoute HF {rand[:4]}",
}
with open(r"d:\omniroute-monetizer\state\hf_experiment_account.json", "w") as f:
    json.dump(account, f, indent=2)
print("username:", account["username"])
print("email:", account["email"])
print("password: <saved to state/hf_experiment_account.json>")
