import schedule, time
import re
import os
import cPickle as pickle
import argparse
from praw.helpers import flatten_tree
from praw.objects import MoreComments
from connections import reddit, youtube
from apiclient.errors import HttpError
import logging

# Regex identifying a youtube link
YOUTUBE_REGEX = re.compile("(?:https?:\/\/)?(?:www\.)?youtu\.?be(?:\.com)?\/?.*(?:watch|embed)?(?:.*v=|v\/|\/)([\w\-_]+)\&?")

def has_video_content(submission):
    """ Return boolean based on whether submission is viable to have a youtube playlist made """

    logging.info("--- EXECUTING FUNCTION HAS_VIDEO_CONTENT ---")
    logging.info("submission title: " + submission.title)

    all_comments = submission.comments
    # imported from praw.helpers
    flat_comments = flatten_tree(all_comments)

    video_count = 0
    video_threshold = 1
    for comment in flat_comments:
        if type(comment) != MoreComments and comment.score >= 5:
            links_in_comment = YOUTUBE_REGEX.findall(comment.body)
            if links_in_comment:
                logging.debug("found youtube links in a comment")
                video_count = video_count + len(links_in_comment)
        if video_count >= video_threshold:
            logging.debug("video_count greater than threshold: " + str(video_threshold))
            return True
    logging.debug("video_count: " + str(video_count) + " less than threshold: " + str(video_threshold))
    return False

class Playlist(object):
    """ A youtube playlist based off of a reddit submission """
    def __init__(self, submission):
        super(Playlist, self).__init__()
        logging.info("--- INITIALIZING NEW PLAYLIST INSTANCE ---")
        logging.info("submission title: " + submission.title)
        if len(submission.title) <= 60:
            self.title = submission.title
        else:
            self.title = submission.title[0:57] + "..."
        self.description = """
A playlist for askreddit submission %s

submission body:
%s

Created automatically by playlist-bot
        """ % (submission.url, submission.selftext)

        logging.info("using youtube api to insert playlist information")
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
        logging.debug("got playlist insert response:")
        logging.debug(playlist_insert_response)

        submission.has_playlist = True

        self.videos = []

    def add_video(self, video_id):
        """ For a video id, add it to the list of videos in the playlist """

        logging.info("--- EXECUTING FUNCTION ADD_VIDEO FOR CLASS PLAYLIST ---")
        logging.info("playlist_title: " + self.title + ", video_id: " + video_id)

        try:
            logging.info("using youtube api to insert a new playlistitem")
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
            logging.debug("got playlistitems insert response:")
            logging.debug(playlistitems_insert_response)

            self.videos.append(video_id)

        except HttpError:
            logging.error("video_id %s threw a http error" % video_id)

class PlaylistBot(object):
    """ A class which automates handling of submissions and playlists """
    def __init__(self):
        super(PlaylistBot, self).__init__()

        logging.info("--- INITIALIZING NEW PLAYLISTBOT INSTANCE ---")

        self.submissions = [] # list of submissions

        if os.path.isfile("playlists.p"):
            logging.info("pickled playlists file exists")
            with open('playlists.p', 'rb') as fp:
                self.playlists = pickle.load(fp)
                logging.debug("contents of playlists.p:")
                logging.debug(self.playlists)
        else:
            logging.info("pickled playlists file doesn't exist")
            self.playlists = {} # dict of playlists indexed by submission

    def run(self):
        """ Automatically execute a list of tasks at regular intervals """

        logging.info("--- EXECUTING FUNCTION RUN FOR CLASS PLAYLISTBOT ---")

        schedule.every(3).minutes.do(self.add_new_submissions)
        schedule.every(3).minutes.do(self.remove_old_submissions)
        schedule.every(6).minutes.do(self.refresh_submissions)
        schedule.every(6).minutes.do(self.create_playlists)
        schedule.every(18).minutes.do(self.update_playlists)
        schedule.every(3).minutes.do(self.save)

        logging.info("starting main loop in playlistbot run function")
        while True:
            logging.info("*** SCHEDULE.RUN_PENDING() *** " + str(time.time()))
            schedule.run_pending()
            time.sleep(60)

        # maintain counters for (addition/removal), (initial playlist creation), (submission/playlist update)

    def add_new_submissions(self):
        """ Add newly created reddit submissions to list of watched submissions """

        logging.info("--- EXECUTING FUNCTION ADD_NEW_SUBMISSIONS FOR CLASS PLAYLISTBOT ---")

        # submissions created before this shouldn't be watched
        # time now - 12h for timeout
        timeout = time.time() - 43200
        logging.debug("timeout: " + str(timeout))

        logging.debug("starting main loop for adding new submissions")
        logging.debug(str(self.submissions))
        logging.debug(str(self.playlists.keys()))
        for submission in reddit.get_hot_submissions("AskReddit"):
            # if submission meets 'currentness' criteria, add to submissions
            logging.debug("name:" + submission.name)
            logging.debug("title:" + submission.title)
            if submission not in self.submissions and submission not in self.playlists.keys():
                if  timeout < submission.created:
                    self.submissions.append(submission)
                    logging.info("adding " + submission.title)
        logging.debug("finished adding new submissions")

    def remove_old_submissions(self):
        """ Remove old reddit submissions from list of watched submissions """

        logging.info("--- EXECUTING FUNCTION REMOVE_OLD_SUBMISSIONS FOR CLASS PLAYLIST_BOT ---")

        # time now - 12h for timeout
        timeout = time.time() - 43200
        logging.debug("timeout: " + str(timeout))

        for submission in self.submissions:
            if timeout > submission.created:
                self.submissions.remove(submission)
                logging.info("removing " + submission.title)

    def refresh_submissions(self):
        """ Update the submission information, which among other things gets the latest comments """

        logging.info("--- EXECUTING FUNCTION REFRESH_SUBMISSIONS FOR CLASS PLAYLISTBOT ---")

        for submission in self.submissions:
            submission.refresh()

    def create_playlists(self):
        """ Called to check all submissions in watchlist to see if they should have a playlist created """

        logging.info("--- EXECUTING FUNCTION CREATE_PLAYLISTS FOR CLASS PLAYLISTBOT ---")

        for submission in [s for s in self.submissions if s.name not in self.playlists.keys() ]:
            if has_video_content(submission):
                new_playlist = self.create_playlist(submission)
                logging.info("created playlist for: " + submission.title )
                #submission.add_comment("comment text")
                self.playlists[submission.name] = new_playlist
                logging.debug("self.playlists[" + submission.name + "] = " + str(self.playlists[submission.name]))

    def create_playlist(self, submission):
        """ For a reddit submission, create an associated youtube playlist """

        logging.info("--- EXECUTING FUNCTION CREATE_PLAYLIST FOR CLASS PLAYLISTBOT ---")

        youtube_links = []

        # submission.replace_more_comments(limit=None, threshold=0)
        all_comments = submission.comments
        # imported from praw.helpers
        flat_comments = flatten_tree(all_comments)

        for comment in flat_comments:
            if type(comment) != MoreComments and comment.score >= 5:
                links_in_comment = YOUTUBE_REGEX.findall(comment.body)
                if links_in_comment:
                    youtube_links = youtube_links + links_in_comment

        new_playlist = Playlist(submission)
        for video_id in youtube_links:
            new_playlist.add_video(video_id)

        return new_playlist

    def update_playlists(self, update_all=False):
        """ Checks all threads with playlists to see if their content should be updated """

        logging.info("--- EXECUTING FUNCTION UPDATE_PLAYLISTS FOR CLASS PLAYLISTBOT ---")

        for submission_name, playlist in self.playlists.iteritems():
            youtube_links = []
            # if the thread is still being watched
            submissions_with_name = [s for s in self.submissions if s.name == submission_name]
            if submissions_with_name or update_all:
                submission = submissions_with_name[0]
                all_comments = submission.comments
                flat_comments = flatten_tree(all_comments)

                # keep a record of yt_links in comments
                for comment in flat_comments:
                    if type(comment) != MoreComments and comment.score >= 5:
                        links_in_comment = YOUTUBE_REGEX.findall(comment.body)
                        if links_in_comment:
                            youtube_links = youtube_links + links_in_comment

                # add new ones
                for video_id in youtube_links:
                    if video_id not in playlist.videos:
                        logging.info("adding new video: " + video_id)
                        playlist.add_video(video_id)

    def save(self):
        """ Pickles the dictionary of playlist data for if execution of this program is restarted """

        logging.info("--- EXECUTING FUNCTION SAVE FOR CLASS PLAYLISTBOT ---")

        with open('playlists.p', 'wb') as fp:
            pickle.dump(self.playlists, fp)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-ro", "--run-once", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    args = parser.parse_args()

    logging.getLogger('').handlers = []
    logging.basicConfig(filename = "logs/playlist_bot_%d.log" % time.time(), filemode="w", level = logging.DEBUG if args.debug else logging.WARNING)

    playlist_bot = PlaylistBot()
    logging.info("--- STARTING PLAYLIST BOT ---")
    logging.info("--run-once: " + str(args.run_once) + ", --debug: " + str(args.debug))
    if args.run_once:
        playlist_bot.add_new_submissions()
        playlist_bot.remove_old_submissions()
        playlist_bot.refresh_submissions()
        playlist_bot.create_playlists()
        playlist_bot.update_playlists()
        playlist_bot.save()
    else:
        playlist_bot.run()
