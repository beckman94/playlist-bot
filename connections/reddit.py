import praw
import json
import requests
import requests.auth

LOGIN_DETAILS_FILE = "login_details.json"

with open(LOGIN_DETAILS_FILE) as ldf:
    login_details = json.load(ldf)

r = praw.Reddit(user_agent="Youtube Playlist Curator by beckman")
r.login(login_details["reddit_username"], login_details["reddit_password"])

def get_hot_submissions(subreddit_name, n=25):
    subreddit = r.get_subreddit(subreddit_name)
    return subreddit.get_hot(limit=n)
