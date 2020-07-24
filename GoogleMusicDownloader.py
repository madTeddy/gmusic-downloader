#!/usr/bin/env python

from gmusicapi import Mobileclient
from os import path, mkdir
from tqdm import tqdm
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TRCK, TPE1, TCON, APIC, TCOM, TYER, TAL
import requests
import re
import oauth2client

class GoogleMusicDownloader:

    LONG_FILE_DUR = 600000
    FILE_NAME_RE = re.compile(r'[\\/:"*?<>|]+')

    def __init__(self):
        self.client = Mobileclient()
        logged_in = self.client.oauth_login(Mobileclient.FROM_MAC_ADDRESS) if path.exists(Mobileclient.OAUTH_FILEPATH) else False

        if not logged_in:
            print('No oauth credentials found, please authenticate your account')
            self.client.perform_oauth(open_browser=True)
            self.client.oauth_login(Mobileclient.FROM_MAC_ADDRESS)
        else:
            print('Logged in!')

    def __ask(self, text):
        inpt = input(text + ' (y/n): ').lower()
        return inpt.startswith('y')

    def __update_metadata(self, path = str(), info = dict()):
        with open(path, 'r+b') as mp3f:
            mp3 = MP3(mp3f)
            id3 = ID3()

            track_num = info.get('trackNumber', 1)
            id3.add(TRCK(encoding=3, text=[track_num if track_num > 0 else 1]))

            id3.add(TIT2(encoding=3, text=info['title']))
            id3.add(TPE1(encoding=3, text=[info.get('artist', None)]))
            id3.add(TCOM(encoding=3, text=[info.get('composer', None)]))
            id3.add(TCON(encoding=3, text=[info.get('genre', None)]))
            id3.add(TAL(encoding=3, text=[info.get('album', None)]))

            year = info.get('year', 0)
            if year > 0:
                id3.add(TYER(encoding=3, text=[year]))
            
            if 'albumArtRef' in info and len(info['albumArtRef']) > 0:
                img_url = info['albumArtRef'][0]['url']
                if img_url:
                    req = requests.get(img_url, allow_redirects=True)
                    id3.add(APIC(encoding=3, mime='image/jpeg', type=3, data=req.content))
                    
            mp3.tags = id3
            mp3.save(mp3f)

    def __kill(self):
        self.client.logout()
        exit()

    def download_all_songs(self):

        print('Loading music library...')
        library = self.client.get_all_songs()
        print(len(library), 'tracks detected.')
        if len(library) == 0:
            self.__kill()

        current_path = path.dirname(path.realpath(__file__))
        include_long_files = self.__ask('Also download long files? (10+ min)')

        if not self.__ask('Begin downloading?'):
            self.__kill()

        long_skipped_count = 0
        errors_count = 0
        successful_count = 0
        song_num = 0

        folder_path = path.join(current_path, 'downloads')
        if not path.exists(folder_path):
            mkdir(folder_path)

        for song in library:
            song_num += 1
            song_id = song['id'] if song['id'] else song['storeId']
            song_name = song['artist'] + ' - ' + song['title']
            mp3_path = path.join(folder_path, self.FILE_NAME_RE.sub(' ', song_name) + '.mp3')
            song_name = '%d. %s' % (song_num, song_name) # song name with index number only for display

            if path.exists(mp3_path):
                print('Track', song_name, 'already exists! Updating metadata...')
                self.__update_metadata(mp3_path, song)
                continue

            if not include_long_files and int(song.get('durationMillis', 0)) >= self.LONG_FILE_DUR:
                long_skipped_count += 1
                continue

            song_url = self.client.get_stream_url(song_id)
            if not song_url:
                print('Warning:', song_name, 'url is empty! Skip...')
                errors_count += 1
                continue

            req = requests.get(song_url, allow_redirects=True, stream=True)
            if not req.ok:
                print(song_name, 'download error!')
                errors_count += 1
                req.raise_for_status()
                continue
            total_size = int(req.headers.get('content-length'))
            with open(mp3_path, 'wb') as mp3f:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=song_name + '.mp3') as pbar:
                    for chunk in req.iter_content(1024):
                        if chunk:
                            mp3f.write(chunk)
                            mp3f.flush()
                            pbar.update(len(chunk))
                successful_count += 1

            print('Filling metadata for', song_name)
            self.__update_metadata(mp3_path, song)

        status_text = 'Process complete! Downloaded: {downloaded}; '
        if not include_long_files:
            status_text += 'Long files skipped: {long_skipped}; '
        status_text += 'Errors count: {errors}'
        print(status_text.format(downloaded=successful_count, long_skipped=long_skipped_count, errors=errors_count))

        self.client.logout()

if __name__ == "__main__":
    downloader = GoogleMusicDownloader()
    downloader.download_all_songs()