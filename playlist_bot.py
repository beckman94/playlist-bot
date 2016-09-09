import schedule, time
import re
import os
import cPickle as pickle
from praw.helpers import flatten_tree
from praw.objects import MoreComments
from connections import reddit, youtube
from apiclient.errors import HttpError

# Regex identifying a youtube link
YOUTUBE_REGEX = re.compile("(?:https?:\/\/)?(?:www\.)?youtu\.?be(?:\.com)?\/?.*(?:watch|embed)?(?:.*v=|v\/|\/)([\w\-_]+)\&?")

def has_video_content(submission):
    """ Return boolean based on whether submission is viable to have a youtube playlist made """

    all_comments = submission.comments
    # imported from praw.helpers
    flat_comments = flatten_tree(all_comments)

    video_count = 0
    for comment in flat_comments:
        if type(comment) != MoreComments and comment.score >= 20:
            links_in_comment = YOUTUBE_REGEX.findall(comment.body)
            if links_in_comment:
                video_count = video_count + len(links_in_comment)
        if video_count >= 10:
            return True
    return False

class Playlist(object):
    """ A youtube playlist based off of a reddit submission """
    def __init__(self, submission):
        super(Playlist, self).__init__()

        self.title = submission.title
        self.description = """
A playlist for askreddit submission %s

submission body:
%s

Created automatically by playlist-bot
        """ % (submission.url, submission.selftext)

        playlist_insert_response = youtube.youtube.playlists().insert(
          part="snippet,status",
          body=dict(
            snippet=dict(
              title=self.title,
              description=self.description
            ),
            status=dict(
              privacyStatus="public"
            )
          )
        ).execute()
        self.id = playlist_insert_response["id"]

        submission.has_playlist = True

        self.videos = []

    def add_video(self, video_id):
        """ For a video id, add it to the list of videos in the playlist """

        try:
            playlistitems_insert_response = youtube.youtube.playlistItems().insert(
              part="snippet,status",
              body=dict(
                snippet=dict(
                  playlistId="%s" % self.id,
                  resourceId=dict(
                    kind="youtube#video",
                    videoId="%s" % video_id
                  )
                )
              )
            ).execute()

            self.videos.append(video_id)

        except HttpError:
            print "%s threw a HttpError in youtube.py" % video_id

class PlaylistBot(object):
    """ A class which automates handling of submissions and playlists """
    def __init__(self):
        super(PlaylistBot, self).__init__()

        self.submissions = [] # list of submissions

        if os.path.isfile("playlists.p"):
            with open('playlists.p', 'rb') as fp:
                self.playlists = pickle.load(fp)
        else:
            self.playlists = {} # dict of playlists indexed by submission

    def run(self):
        """ Automatically execute a list of tasks at regular intervals """

        schedule.every(30).minutes.do(self.add_new_submissions)
        schedule.every(30).minutes.do(self.remove_old_submissions)
        schedule.every(60).minutes.do(self.create_playlists)
        schedule.every(180).minutes.do(self.update_playlists)
        schedule.every(30).minutes.do(self.save)

        while True:
            schedule.run_pending()
            time.sleep(600)

        # maintain counters for (addition/removal), (initial playlist creation), (submission/playlist update)

    def add_new_submissions(self):
        """ Add newly created reddit submissions to list of watched submissions """

        # submissions created before this shouldn't be watched
        # time now - 12h for timeout
        timeout = time.time() - 43200

        for submission in reddit.get_hot_submissions("AskReddit"):
            # if submission meets 'currentness' criteria, add to submissions
            if submission not in self.submissions and submission not in self.playlists.keys():
                if  timeout < submission.created:
                    self.submissions.append(submission)
                    print "Adding " + submission.name

    def remove_old_submissions(self):
        """ Remove old reddit submissions from list of watched submissions """

        # time now - 12h for timeout
        timeout = time.time() - 43200

        for submission in self.submissions:
            if timeout > submission.created:
                print "Removing " + submission.name
                self.submissions.remove(submission)

    def create_playlists(self):
        """ Called to check all submissions in watchlist to see if they should have a playlist created """

        for submission in [s for s in self.submissions if s not in self.playlists.keys() ]:
            if has_video_content(submission):
                new_playlist = self.create_playlist(submission)
                print "Created playlist for: " + new_playlist.title
                #submission.add_comment("comment text")
                self.playlists[submission] = new_playlist

    def create_playlist(self, submission):
        """ For a reddit submission, create an associated youtube playlist """

        youtube_links = []

        # submission.replace_more_comments(limit=None, threshold=0)
        all_comments = submission.comments
        # imported from praw.helpers
        flat_comments = flatten_tree(all_comments)

        for comment in flat_comments:
            if type(comment) != MoreComments and comment.score >= 20:
                links_in_comment = YOUTUBE_REGEX.findall(comment.body)
                if links_in_comment:
                    youtube_links = youtube_links + links_in_comment

        new_playlist = Playlist(submission)
        for video_id in youtube_links:
            new_playlist.add_video(video_id)

        return new_playlist

    def update_playlists(self, update_all=False):
        """ Checks all threads with playlists to see if their content should be updated """

        for submission, playlist in self.playlists.iteritems():
            youtube_links = []
            # if the thread is still being watched
            if submission in self.submissions or update_all:
                all_comments = submission.comments
                flat_comments = flatten_tree(all_comments)

                # keep a record of yt_links in comments
                for comment in flat_comments:
                    if type(comment) != MoreComments and comment.score >= 20:
                        links_in_comment = YOUTUBE_REGEX.findall(comment.body)
                        if links_in_comment:
                            youtube_links = youtube_links + links_in_comment

                # add new ones
                for video_id in youtube_links:
                    if video_id not in playlist.videos:
                        playlist.add_video(video_id)

    def save(self):
        with open('playlists.p', 'wb') as fp:
            pickle.dump(self.playlists, fp)

playlist_bot = PlaylistBot()
playlist_bot.run()
