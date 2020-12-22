#!/usr/bin/env python3

import sys
import os
import concurrent.futures
import time

from utils import config, logger, env, updater, args
from media.movieFolder import MovieFolder
from providers.tmdb import Tmdb
from providers.apple import Apple
from downloaders.downloader import Downloader

log = logger.get_log('TrailerTech')

class TrailerTech():
    def __init__(self):
        self.directoriesScanned = 0
        self.trailersDownloaded = 0
        self.trailersFound = 0
        self.startTime = time.perf_counter()
        self.tmdb = Tmdb(config.tmdb_API_key)
        self.apple = Apple(config.min_resolution)
        self.downloader = Downloader()

    def printStats(self):
        secondsElapsed = time.perf_counter() - self.startTime
        missingTrailers = self.directoriesScanned - (self.trailersDownloaded + self.trailersFound)
        statsStr = '''
        #################################################
        |   Stats:                                      |
        |   Movie Directories Scanned: {}\t\t|
        |   Trailers Downloaded:       {}\t\t|
        |   Missing Trailers:          {}\t\t|
        |   Completed In:              {}s\t\t|
        #################################################
        '''.format(self.directoriesScanned, self.trailersDownloaded, missingTrailers, int(secondsElapsed))
        print(statsStr)

    def get_Trailer(self, movieDir, tmdbid=None, imdbid=None, title=None, year=None):
        if not os.path.isdir(os.path.abspath(movieDir)):
            log.warning('Invalid path: {}'.format(movieDir))
            return

        folder = MovieFolder(movieDir)
        if not folder.hasMovie:
            log.warning('Unable to determin Movie file in: {}'.format(movieDir))
            return

        self.directoriesScanned += 1
        
        if folder.hasTrailer:
            log.debug('Trailer found: {}'.format(folder.trailer.path))
            self.trailersFound += 1
            return

        log.debug('No trailer found in "{}"'.format(folder.trailerDirectory))
        if (tmdbid or imdbid) or (title and year):
            self.tmdb.get_movie_details(tmdbid, imdbid, title, year)
            appleLinks = self.apple.getLinks(title, year)
        else:
            self.tmdb.get_movie_details(folder.nfo.tmdb, folder.nfo.imdb, folder.nfo.title, folder.nfo.year)
            appleLinks = self.apple.getLinks(folder.nfo.title, folder.nfo.year)
        ytLinks = self.tmdb.get_trailer_links(config.languages, config.min_resolution)
        
        log.debug('Found {} trailer Links.'.format(len(appleLinks) + len(ytLinks)))

        for link in appleLinks:
            if self.downloader.downloadApple(folder.trailerName, folder.trailerDirectory, link):
                log.info('Downloaded trailer from {}'.format(link))
                self.trailersDownloaded += 1
                return
            else:
                log.info('Failed to download trailer for {} at {}'.format(folder.trailerDirectory, link))

        for link in ytLinks:
            if self.downloader.downloadYouTube(folder.trailerName, folder.trailerDirectory, link):
                log.info('Downloaded trailer from {}'.format(link))
                self.trailersDownloaded += 1
                return
            else:
                log.info('Failed to download trailer for {} at {}'.format(folder.trailerDirectory, link))

        log.info('No trailer found for "{}"'.format(folder.trailerDirectory))

    def scanLibrary(self, directory):
        libraryDir = os.path.abspath(directory)
        if not os.path.isdir(libraryDir):
            log.critical('"{}" is not a valid path. Exiting.'.format(libraryDir))
            return

        for item in os.listdir(libraryDir):
            path = os.path.abspath(os.path.join(libraryDir, item))
            if os.path.isdir(path):
                log.info('Scanning: {}'.format(path))
                self.get_Trailer(path)

    def scanLibraryThreaded(self, directory):
        libraryDir = os.path.abspath(directory)
        if not os.path.isdir(libraryDir):
            log.critical('"{}" is not a valid path. Exiting.'.format(libraryDir))
            return
        log.info('Building list of directories to scan for trailers.')
        movieDirs = [os.path.join(libraryDir, subDir) for subDir in os.listdir(libraryDir) if os.path.isdir(os.path.join(libraryDir, subDir))]
        log.info('Starting threads for {} movie directories.'.format(len(movieDirs)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=None) as executer:
            executer.map(self.get_Trailer, movieDirs)

    def main(self):
        log.info('Starting TrailerTech')
        # Check if any args were parsed from user
        if args.directory:
            if args.recursive:
                # Parse entire library
                if args.threads:
                    log.info('Parsing "{}" in recursive mode. Threads enabled.'.format(args.directory))
                    self.scanLibraryThreaded(args.directory)
                else:
                    log.info('Parsing "{}" in recursive mode.'.format(args.directory))
                    self.scanLibrary(args.directory)
            else:
                # Parse single movie directory
                log.info('Parsing "{}" in single movie mode.'.format(args.directory))
                self.get_Trailer(args.directory, args.tmdb, args.imdb, args.title, args.year)

            # Cleanup the temp download directory
            log.info('Cleaning up temp directory.')
            self.downloader.cleanUp()

        # Check environment variables
        elif env.event == 'download' and env.movieDirectory:
            log.info('Called from Radarr Parsing "{}"'.format(env.movieDirectory))
            self.get_Trailer(env.movieDirectory, env.tmdbid, env.imdbid, env.movieTitle, env.year) # parse imdb and tmdb from environment vars

            # Cleanup the temp download directory
            log.info('Cleaning up temp directory.')
            self.downloader.cleanUp()

        elif env.event == 'test':
            log.info('Radarr called with event: {}'.format(env.event))
            sys.exit(0)

        elif env.event:
            log.info('Exiting. Radarr called with unsupported EVENT: {}'.format(env.event))
            sys.exit(0)

        else:
            log.info('Exiting. Not enough data collected from arguments or environment variables.')
            sys.exit(1)



if __name__ == '__main__':
    app = TrailerTech()
    try:
        app.main()
    except KeyboardInterrupt:
        log.info('User terminated script.')
        app.printStats()
        sys.exit(0)

    log.info('Script Completed Successfully!')
    app.printStats()