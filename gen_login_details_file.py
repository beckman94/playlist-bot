import json
import sys

LOGIN_DETAILS_FILE = "login_details.json"

if len(sys.argv) == 3:
    login_details = {}
    login_details["reddit_username"] = sys.argv[1]
    login_details["reddit_password"] = sys.argv[2]

with open(LOGIN_DETAILS_FILE, "w") as ldf:
    json.dump(login_details, ldf)
