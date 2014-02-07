#!/usr/bin/env python
import re
import sys
import os
import eyed3
import argparse
from gmusicapi import Musicmanager

# Used to hold a collection of Tracks
class TrackCollection(object):
    def __init__(self):
        self.tracks = {}

    # This method should be overriden
    def load_tracks(self):
        raise NotImplementedError('This method must be overridden and call AddTrack for each item')

    # Returns true or false if this collection has a specific track
    def has_track(self, key):
        return key in self.tracks

    # Returns the item with the given key
    def get_track(self, key):
        return self.tracks[key]

    # Adds a track to the collection
    def add_track(self, track, title, album, artist, info):
        re_track_no = re.compile('.+\s+')

        # create dictionary key
        key_items = []

        # first do the track number..
        # left this out for now, as if your local file doesn't
        # have a track number but google has matched it, it's detected
        # difference, don't know how best to handle this :s
        #track = self._clean_value(track)
        #track = re_track_no.sub('',track)
        #key_items.append(track)
        #key = '|'.join(key_items)

        for item in [artist, album, title]:
            # add to list
            key_items.append(self._clean_value(item))
            key = '|'.join(key_items)
        
        if self.has_track(key):
            print('Duplicate track found: {0}'.format(key))
        else:
            self.tracks[key] = info

    # returns a cleaned up value of the string
    def _clean_value(self, item):
        # stuff in brackets...
        # re_paren = re.compile('[[(][^)\]]*[)\]]')
        re_nonword = re.compile('[^\w\s]')
        re_mspace = re.compile('\s+')
        re_prespace = re.compile('^\s+')
        re_postspace = re.compile('\s+$')
        re_the = re.compile('^the\s+', re.I)

        # cast to unicode
        item = unicode(item)
        # lower case
        item = item.lower()
        # remove stuff in brackets
        # item = re_paren.sub('', item)
        # remove nonword junk
        item = re_nonword.sub('', item)
        # deal with leading, trailing, and multiple spaces
        item = re_mspace.sub(' ', item)
        item = re_prespace.sub('', item)
        item = re_postspace.sub('', item)
        # remove leading the
        item = re_the.sub('', item)
        return item
        
# Loads all local tracks
class LocalTrackCollection(TrackCollection):
    def __init__(self, path):
       self._root = path
       super(LocalTrackCollection, self).__init__()

    # Loads the local tracks from the file system
    def load_tracks(self):
        print("Loading Local Library...")
        for path, subdirs, files in os.walk(self._root):
            for name in files:
                if self._is_valid_file_name(name):
                    fullpath = os.path.join(path, name)
                    local_track = eyed3.load(fullpath)
                    if local_track.tag is None:
                        local_track.tag = eyed3.id3.Tag()
                        local_track.tag.file_info = eyed3.id3.FileInfo(fullpath)
                    self.add_track(local_track.tag.track_num, local_track.tag.title, local_track.tag.album, local_track.tag.artist, fullpath)
        print("Loaded {0} tracks from Local Library".format(len(self.tracks)))
    
    # Checks the file name is an mp3
    def _is_valid_file_name(self, name):
        return name.endswith('.mp3')

# Loads all tracks from google music
class GoogleTrackCollection(TrackCollection):
    def __init__(self, gc):
        super(GoogleTrackCollection, self).__init__()
        if gc is None:
            gc = GoogleClient()
            gc.Authenticate()
        self._gc = gc

    # Loads the tracks from GoogleMusic
    def load_tracks(self):
        print("Loading GoogleMusic library...")
        for gm_track in self._gc.MusicManager.get_all_songs():
            self.add_track(gm_track['track_number'], gm_track['title'], gm_track['album'], gm_track['artist'], gm_track)

        print("Loaded {0} tracks from GoogleMusic".format(len(self.tracks)))
    
# Handles a connection to Google
class GoogleClient():
    # Initiates the oAuth
    def Authenticate(self):
        self.MusicManager = Musicmanager(debug_logging=False)

        attempts = 0
        # Attempt to login. Perform oauth only when necessary.
        while attempts < 3:
                if self.MusicManager.login():
                        break
                self.MusicManager.perform_oauth()
                attempts += 1

        if not self.MusicManager.is_authenticated():
                print "Sorry, login failed."
                return False

        print "Successfully logged in.\n"
        return True

# Handles a comparison between your local files and google
class ComparisonManager():
    def __init__(self, local_path):
        self._root = local_path

    # Perform a comparison between your local files and google
    def do_comparison(self):
        # Create a connection to google
        self._gc = GoogleClient()
        if self._gc.Authenticate() is True:
            self._load_differences()

    # Loads the differences between the two collections
    def _load_differences(self):
        # Get the local tracks
        self._local_tracks = LocalTrackCollection(self._root)
        self._local_tracks.load_tracks()
        
        # Get the google tracks
        self._google_tracks = GoogleTrackCollection(self._gc)
        self._google_tracks.load_tracks()
        
        # Now go through your local tracks and see if they're on google
        # And build up a list of differences
        self._files_not_on_google = []
        for track in self._local_tracks.tracks:
            if not self._google_tracks.has_track(track):
                self._files_not_on_google.append(track)

        print("{0} differences found.".format(len(self._files_not_on_google)))
        self._files_not_on_google.sort()

    # upload the files that are on your computer, but aren't on google music
    def do_upload(self):
        # Loads the differences to google music
        if self._files_not_on_google is None:
            raise LookupError('Please run do_comparison before do_upload')
        else:
            filenum = 0
            total = len(self._files_not_on_google)
            for file in self._files_not_on_google:
                filenum += 1
                file_path = self._local_tracks.get_track(file)
                uploaded, matched, not_uploaded = self._gc.MusicManager.upload(file_path, transcode_quality="320k", enable_matching=False)
                if uploaded:
                        print "(%s/%s) " % (filenum, total), "Successfully uploaded ", file_path
                elif matched:
                        print "(%s/%s) " % (filenum, total), "Successfully scanned and matched ", file_path
                else:
                        if "ALREADY_EXISTS" or "this song is already uploaded" in not_uploaded[file_path]:
                                response = "ALREADY EXISTS"
                        else:
                                response = not_uploaded[file_path]
                        print "(%s/%s) " % (filenum, total), "Failed to upload ", file_path, " | ", response

def main():
    # Get the arguements
    parser = argparse.ArgumentParser(description='Google Music Library Sync.')
    parser.add_argument("-p", "--path", dest="local_path", required=True,
                        help="The local directory to scan")

    parser.add_argument("-s", "--sync", dest="should_sync",
                        default="false",
                        choices=['true','false'],
                        help="Sync your local files to google music")

    args = parser.parse_args()

    comparison_manager = ComparisonManager(args.local_path)
    comparison_manager.do_comparison()
    if args.should_sync == "true":
        comparison_manager.do_upload()

if __name__ == '__main__':
    main()
