#!/usr/bin/env python3

import os
import json
import subprocess
import re
from utils import logger
try:
    import xml.etree.cElementTree as et
except ImportError:
    import xml.etree.ElementTree as et

MIN_MOVIE_DURATION = 600
VIDEO_EXTENSIONS = ['.mkv', '.iso', '.wmv', '.avi', '.mp4', '.m4v', '.img', '.divx', '.mov', '.flv', '.m2ts']
NFO_EXTENSIONS = ['.nfo', '.xml']
ID_TAGS = ['imdb', 'tmdb', 'imdbid', 'tmdbid', 'tmdb_id', 'imdb_id', 'id']
IMDB_ID_PATTERN = re.compile(r'ev\d{7,8}\/\d{4}(-\d)?|(ch|co|ev|nm|tt)\d{7,8}')
TMDB_ID_PATTERN = re.compile(r'[1-9]\d{1,10}')
YEAR_PATTERN = re.compile(r'\d{4}')

log = logger.get_log(__name__)

class File():
    def __init__(self, path):
        self.path = path

    @property
    def fileName(self):
        return os.path.basename(self.path)

    @property
    def fileSize(self):
        return os.path.getsize(self.path)

class Video(File):
    def __init__(self, path, skip_processing=False, is_trailer=False):
        super().__init__(path)
        if skip_processing:
            if is_trailer:
                self.duration = MIN_MOVIE_DURATION - 1
            else:
                self.duration = MIN_MOVIE_DURATION + 1
        else:
            self.duration = self.get_duration()

    @property
    def isMovie(self):
        return self.duration >= MIN_MOVIE_DURATION

    def get_duration(self):
        result = subprocess.run([
            'ffprobe', '-v', 'fatal', '-show_entries',
            'format=duration', '-of',
            'default=noprint_wrappers=1:nokey=1',
            self.path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
            )
        try:
            duration = float(result.stdout)
        except ValueError:
            if os.path.splitext(self.fileName)[0].endswith('-trailer'):
                duration = 1
            else:
                duration = MIN_MOVIE_DURATION + 1
        return duration

class NFO(File):
    def __init__(self, path):
        super().__init__(path)
        self.__originaltitle = None
        self.__title = None
        self.__localtitle = None
        self.__year = None
        self.__releasedate = None
        self.__premiered = None
        self.__productionyear = None
        self.__imdb = None
        self.__tmdb = None
        self.__unique_id_imdb = None
        self.__unique_id_tmdb = None
        self.__id = None
        self.__parse_nfo()

    @property
    def is_complete(self):
        if self.imdb or self.tmdb:
            return True
        elif self.title and self.year:
            return True
        else:
            return False

    @property
    def title(self):
        if isinstance(self.__originaltitle, str):
            return self.__originaltitle
        elif isinstance(self.__title, str):
            return self.__title
        elif isinstance(self.__localtitle, str):
            return self.__localtitle
        else:
            return None

    @property
    def year(self):
        if self.__premiered:
            year = self.__parse_releaseDate(self.__premiered)
            match = re.match(YEAR_PATTERN, year)
            if match:
                return year
        
        if self.__releasedate:
            year = self.__parse_releaseDate(self.__parse_releaseDate)
            match = re.match(YEAR_PATTERN, year)
            if match:
                return year
        
        if self.__year:
            match = re.match(YEAR_PATTERN, self.__year)
            if match:
                return self.__year

        if self.__productionyear:
            match = re.match(YEAR_PATTERN, self.__productionyear)
            if match:
                return self.__productionyear

        return None

    @property
    def imdb(self):
        if self.__unique_id_imdb and re.match(IMDB_ID_PATTERN, self.__unique_id_imdb):
            return self.__unique_id_imdb
        if self.__imdb and re.match(IMDB_ID_PATTERN, self.__imdb):
            return self.__imdb
        if self.__id and re.match(IMDB_ID_PATTERN, self.__id):
            return self.__id
        return None

    @property
    def tmdb(self):
        if self.__unique_id_tmdb and re.match(TMDB_ID_PATTERN, self.__unique_id_tmdb):
            return self.__unique_id_tmdb
        if self.__tmdb and re.match(TMDB_ID_PATTERN, self.__tmdb):
            return self.__tmdb
        if self.__id and re.match(TMDB_ID_PATTERN, self.__id):
            return self.__id
        return None

    def __parse_nfo(self):
        try:
            nfo = et.parse(self.path)
            root  = nfo.getroot()
        except (IOError, et.ParseError):
            return


        for item in root:
            # Parse uniqueid
            if item.tag.lower() == 'uniqueid':
                if item.attrib['type'].lower() == 'tmdb':
                    self.__unique_id_tmdb = item.text
                elif item.attrib['type'].lower() == 'imdb':
                    self.__unique_id_imdb = item.text
            
            # Parse additional ids
            elif item.tag.lower() in ID_TAGS:
                self.__parse_id(item.text)
            
            # Parse release years
            elif item.tag.lower() == 'premiered':
                self.__premiered = self.__parse_releaseDate(item.text)
            elif item.tag.lower() == 'release_date':
                self.__releasedate = self.__parse_releaseDate(item.text)
            elif item.tag.lower() == 'year':
                self.__year = item.text
            elif item.tag.lower() == 'productionyear':
                self.__productionyear = item.text

            # Parse titles
            elif item.tag.lower() == 'title':
                self.__title = item.text
            elif item.tag.lower() == 'originaltitle':
                self.__originaltitle = item.text
            elif item.tag.lower() == 'localtitle':
                self.__localtitle = item.text

    def __parse_releaseDate(self, releaseDate):
        if releaseDate:
            if len(releaseDate) == 4 and releaseDate.isdigit():
                return releaseDate
            try:
                year = str(datetime.strptime(releaseDate, '%Y-%m-%d').year)
            except:
                return None
            return year
        else:
            return None

    def __parse_id(self, movie_id):
        if movie_id:
            if movie_id.lower().startswith('tt'):
                self.__imdb = movie_id
            elif movie_id.isdigit():
                self.__tmdb = movie_id
        return None

class MovieFolder():
    def __init__(self, directory):
        self.rootDir = os.path.abspath(directory)
        self.movie = None
        self.trailer = None
        self.nfo = None
        self.scan()

    @property
    def trailerName(self):
        if self.hasMovie:
            return os.path.splitext(self.movie.fileName)[0] + '-trailer.mp4'

    @property
    def trailerDirectory(self):
        if self.hasMovie:
            return os.path.dirname(self.movie.path)

    @property
    def hasTrailer(self):
        return not self.trailer == None

    @property
    def hasMovie(self):
        return not self.movie == None

    def scan(self):
        for item in os.scandir(self.rootDir):
            if os.path.isfile(item.path):
                ext = os.path.splitext(item.path)[-1]
                if ext in VIDEO_EXTENSIONS:
                    video = Video(item.path)
                    if video.isMovie:
                        self.movie = video
                        log.debug('Movie Found: {}'.format(self.movie.fileName))
                    else:
                        self.trailer = video
                        log.debug('Trailer Found: {}'.format(self.trailer.fileName))
                elif ext in NFO_EXTENSIONS:
                    nfo = NFO(item.path)
                    if (nfo.is_complete and not self.nfo) or (nfo.is_complete and nfo.fileSize > self.nfo.fileSize):
                        self.nfo = nfo
                        log.debug('NFO Found: {}'.format(self.nfo.fileName))
            
            elif os.path.isdir(item.path):
    
                # Handle bdmv folders
                if 'bdmv' in item.path.lower() and os.path.isdir(item.path):
                    log.debug('Encountered a BluRay folder structure "{}"'.format(item.path))
                    bd_file = os.path.join(item.path, 'index.bdmv')
                    if os.path.isfile(bd_file):
                        video = Video(bd_file, skip_processing=True, is_trailer=False)
                        log.debug('Movie Found: {}'.format(video.fileName))
                        self.movie = video
                        # Find the trailer in the BDMV folder
                        for entry in os.listdir(item.path):
                            if 'index-trailer' in entry.lower():
                                video = Video(os.path.join(item.path, entry))
                                if not video.isMovie:
                                    log.debug('Found trailer: {}'.format(video.fileName))
                                    self.trailer = video
                
                # Handle video_ts folders
                elif 'video_ts' in item.path.lower() and os.path.isdir(item.path):
                    log.debug('Encountered a DVD folder structure "{}"'.format(item.path))
                    dvd_file = os.path.join(item.path, 'VIDEO_TS.IFO')
                    if os.path.isfile(dvd_file):
                        video = Video(dvd_file, skip_processing=True, is_trailer=False)
                        log.debug('Movie Found: {}'.format(video.fileName))
                        self.movie = video
                        # Find the trailer in the VIDEO_TS folder
                        for entry in os.listdir(item.path):
                            if 'video_ts-trailer' in entry.lower():
                                video = Video(os.path.join(item.path, entry))
                                if not video.isMovie:
                                    log.debug('Trailer Found: {}'.format(video.fileName))
                                    self.trailer = video