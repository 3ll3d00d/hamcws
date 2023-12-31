"""Implementation of a MCWS inteface."""
from typing import Tuple, List
from xml.etree import ElementTree as et

from aiohttp import ClientSession, ClientResponseError, BasicAuth


class Zone:
    def __init__(self, content: dict, zone_index: int, active_zone_id: int):
        self.index = zone_index
        self.id = int(content[f"ZoneID{self.index}"])
        self.name = content[f"ZoneName{self.index}"]
        self.guid = content[f"ZoneGUID{self.index}"]
        self.is_dlna = True if (content[f"ZoneDLNA{self.index}"] == "1") else False
        self.active = self.id == active_zone_id

    def __identifier(self):
        if self.id is not None:
            return self.id
        if self.name is not None:
            return self.name
        if self.index is not None:
            return self.index

    def __identifier_type(self):
        if self.id is not None:
            return "ID"
        if self.name is not None:
            return "Name"
        if self.index is not None:
            return "Index"

    def as_query_params(self) -> dict:
        return {
            'Zone': self.__identifier(),
            'ZoneType': self.__identifier_type()
        }

    def __str__(self):
        return self.name


def get_mcws_connection(host: str, port: int, username: str | None = None, password: str | None = None,
                        ssl: bool = False, timeout: int = 5, session: ClientSession = None):
    """Returns a MCWS connection."""
    return MediaServerConnection(host, port, username, password, ssl, timeout, session)


class MediaServerConnection:
    """A connection to MCWS."""

    def __init__(self, host: str, port: int, username: str | None, password: str | None, ssl: bool, timeout: int,
                 session: ClientSession | None):
        self._session = session
        self._close_session_on_exit = False
        if self._session is None:
            self._session = ClientSession()
            self._close_session_on_exit = True

        self._timeout = timeout
        self._auth = BasicAuth(username, password) if username is not None else None
        self._base_url = f"http{'s' if ssl else ''}://{host}:{port}/MCWS/v1"

    async def get(self, path: str, params: dict | None = None) -> Tuple[bool, dict]:
        async with self._session.get(f'{self._base_url}/{path}', params=params, timeout=self._timeout,
                                     auth=self._auth) as resp:
            try:
                resp.raise_for_status()
                return self.__to_dict(await resp.text())
            except ClientResponseError as e:
                if e.status == 401:
                    raise InvalidAuthError from e
                else:
                    raise CannotConnectError from e

    async def close(self):
        """Close the connection if necessary."""
        if self._close_session_on_exit and self._session is not None:
            await self._session.close()
            self._session = None
            self._close_session_on_exit = False

    @staticmethod
    def __to_dict(content: str, try_int_cast: bool = False) -> Tuple[bool, dict]:
        """
        Converts the relatively unstructured XML responses from MCWS into a dictionary with a flag to indicate
        if the response was "OK".
        """
        result: dict = {}
        root = et.fromstring(content)
        for child in root:
            result[child.attrib["Name"]] = child.text
        if try_int_cast:
            for key in result:
                if key:
                    try:
                        result[key] = int(result[key])
                    except ValueError:
                        pass  # passing is ok: If untranslatable, leave alone
        return root.attrib['Status'] == 'OK', result


class MediaServer:
    """A high level interface for MCWS."""

    def __init__(self, connection: MediaServerConnection):
        self._conn = connection

    async def close(self):
        await self._conn.close()

    async def can_connect(self) -> bool:
        """ returns true if server allows the connection. """
        ok, resp = await self._conn.get('Authenticate')
        return 'Token' in resp.keys()

    async def get_zones(self) -> List[Zone]:
        """ all known zones """
        ok, resp = await self._conn.get("Playback/Zones")
        num_zones = int(resp["NumberZones"])
        active_zone_id = resp['CurrentZoneID']
        return [Zone(resp, i, active_zone_id) for i in range(num_zones)]

    async def get_playback_info(self, zone: Zone | None = None, extra_fields: List[str] | None = None) -> dict:
        params = self.__zone_params(zone)
        if extra_fields:
            params['Fields'] = ';'.join(extra_fields)
        ok, resp = await self._conn.get("Playback/Info")
        if 'Playback Info' in extra_fields:
            pass  # parse into a nested dict
        return resp

    @staticmethod
    def __zone_params(zone: Zone | None = None) -> dict:
        return zone.as_query_params() if zone else {}

    async def volume_up(self, step: float = 0.1, zone: Zone | None = None) -> None:
        """Send volume up command."""
        await self._conn.get('Playback/Volume', params={'Level': step, 'Relative': 1, **self.__zone_params(zone)})

    async def volume_down(self, step: float = 0.1, zone: Zone | None = None) -> None:
        """Send volume down command."""
        await self._conn.get('Playback/Volume', params={'Level': f'{"-" if step > 0 else ""}{step}', 'Relative': 1,
                                                        **self.__zone_params(zone)})

    async def set_volume_level(self, volume: float, zone: Zone | None = None) -> None:
        """Set volume level, range 0-100."""
        if volume < 0:
            raise ValueError(f'{volume} not in range 0-100')
        if volume > 100:
            raise ValueError(f'{volume} not in range 0-100')
        volume = volume / 100
        await self._conn.get('Playback/Volume', params={'Level': volume, **self.__zone_params(zone)})

    async def mute(self, mute: bool, zone: Zone | None = None) -> None:
        """Send (un)mute command."""
        await self._conn.get('Playback/Mute', params={'Set': '1' if mute else '0', **self.__zone_params(zone)})

    async def play_pause(self, zone: Zone | None = None) -> None:
        """Send play/pause command."""
        await self._conn.get('Playback/PlayPause', params=self.__zone_params(zone))

    async def play(self, zone: Zone | None = None) -> None:
        """Send play command."""
        await self._conn.get('Playback/Play', params=self.__zone_params(zone))

    async def pause(self, zone: Zone | None = None) -> None:
        """Send pause command."""
        await self._conn.get('Playback/Pause', params=self.__zone_params(zone))

    async def stop(self, zone: Zone | None = None) -> None:
        """Send stop command."""
        await self._conn.get('Playback/Stop', params=self.__zone_params(zone))

    async def next_track(self, zone: Zone | None = None) -> None:
        """Send next track command."""
        await self._conn.get('Playback/Next', params=self.__zone_params(zone))

    async def previous_track(self, zone: Zone | None = None) -> None:
        """Send previous track command."""
        # TODO does it go to the start of the current track?
        await self._conn.get('Playback/Previous', params=self.__zone_params(zone))

    async def media_seek(self, position: float, zone: Zone | None = None) -> None:
        """seek to a specified position in ms."""
        await self._conn.get('Playback/Position', params={'Position': position, **self.__zone_params(zone)})

    async def play_item(self, item: str, zone: Zone | None = None) -> None:
        await self._conn.get('Playback/PlayByKey', params={'Key': item, **self.__zone_params(zone)})

    async def play_playlist(self, playlist_id: str, zone: Zone | None = None) -> None:
        """Play the given playlist."""
        await self._conn.get('Playback/PlayPlaylist', params={'Playlist': playlist_id, **self.__zone_params(zone)})

    async def play_file(self, file: str, zone: Zone | None = None) -> None:
        """Play the given file."""
        await self._conn.get('Playback/PlayByFilename', params={'Filenames': file, **self.__zone_params(zone)})

    async def set_shuffle(self, shuffle: bool, zone: Zone | None = None) -> None:
        """Set shuffle mode, for the first player."""
        await self._conn.get('Control/MCC', params={'Command': '10005', 'Parameter': '4' if shuffle else '3',
                                                    **self.__zone_params(zone)})

    async def _add_item_to_playlist(self, item):
        # await self._server.Playlist.Add(**{"playlistid": 0, "item": item})
        raise NotImplementedError

    async def add_song_to_playlist(self, song_id):
        """Add song to default playlist (i.e. playlistid=0)."""
        # await self._add_item_to_playlist({"songid": song_id})
        raise NotImplementedError

    async def add_album_to_playlist(self, album_id):
        """Add album to default playlist (i.e. playlistid=0)."""
        # await self._add_item_to_playlist({"albumid": album_id})
        raise NotImplementedError

    async def add_artist_to_playlist(self, artist_id):
        """Add album to default playlist (i.e. playlistid=0)."""
        # await self._add_item_to_playlist({"artistid": artist_id})
        raise NotImplementedError

    async def clear_playlist(self, zone: Zone | None = None):
        """Clear default playlist."""
        await self._conn.get('Playback/ClearPlaylist', params=self.__zone_params(zone))

    async def get_artists(self, properties=None):
        """Get artists list."""
        # return await self._server.AudioLibrary.GetArtists(
        #     **_build_query(properties=properties)
        # )
        raise NotImplementedError

    async def get_artist_details(self, artist_id=None, properties=None):
        """Get artist details."""
        # return await self._server.AudioLibrary.GetArtistDetails(
        #     **_build_query(artistid=artist_id, properties=properties)
        # )
        raise NotImplementedError

    async def get_albums(self, artist_id=None, album_id=None, properties=None):
        """Get albums list."""
        # filter = {}
        # if artist_id:
        #     filter["artistid"] = artist_id
        # if album_id:
        #     filter["albumid"] = album_id
        #
        # return await self._server.AudioLibrary.GetAlbums(
        #     **_build_query(filter=filter, properties=properties)
        # )
        raise NotImplementedError

    async def get_album_details(self, album_id, properties=None):
        """Get album details."""
        # return await self._server.AudioLibrary.GetAlbumDetails(
        #     **_build_query(albumid=album_id, properties=properties)
        # )
        raise NotImplementedError

    async def get_songs(self, artist_id=None, album_id=None, properties=None):
        """Get songs list."""
        # filter = {}
        # if artist_id:
        #     filter["artistid"] = artist_id
        # if album_id:
        #     filter["albumid"] = album_id
        #
        # return await self._server.AudioLibrary.GetSongs(
        #     **_build_query(filter=filter, properties=properties)
        # )
        raise NotImplementedError

    async def get_movies(self, properties=None):
        """Get movies list."""
        # return await self._server.VideoLibrary.GetMovies(
        #     **_build_query(properties=properties)
        # )
        raise NotImplementedError

    async def get_movie_details(self, movie_id, properties=None):
        """Get movie details."""
        # return await self._server.VideoLibrary.GetMovieDetails(
        #     **_build_query(movieid=movie_id, properties=properties)
        # )
        raise NotImplementedError

    async def get_seasons(self, tv_show_id, properties=None):
        """Get seasons list."""
        # return await self._server.VideoLibrary.GetSeasons(
        #     **_build_query(tvshowid=tv_show_id, properties=properties)
        # )
        raise NotImplementedError

    async def get_season_details(self, season_id, properties=None):
        """Get songs list."""
        # return await self._server.VideoLibrary.GetSeasonDetails(
        #     **_build_query(seasonid=season_id, properties=properties)
        # )
        raise NotImplementedError

    async def get_episodes(self, tv_show_id, season_id, properties=None):
        """Get episodes list."""
        # return await self._server.VideoLibrary.GetEpisodes(
        #     **_build_query(tvshowid=tv_show_id, season=season_id, properties=properties)
        # )
        raise NotImplementedError

    async def get_tv_shows(self, properties=None):
        """Get tv shows list."""
        # return await self._server.VideoLibrary.GetTVShows(
        #     **_build_query(properties=properties)
        # )
        raise NotImplementedError

    async def get_tv_show_details(self, tv_show_id=None, properties=None):
        """Get songs list."""
        # return await self._server.VideoLibrary.GetTVShowDetails(
        #     **_build_query(tvshowid=tv_show_id, properties=properties)
        # )
        raise NotImplementedError


class CannotConnectError(Exception):
    """Exception to indicate an error in connection."""


class InvalidAuthError(Exception):
    """Exception to indicate an error in authentication."""
