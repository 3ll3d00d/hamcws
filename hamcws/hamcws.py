"""Implementation of a MCWS inteface."""
from __future__ import annotations

import datetime
import time
import logging
from collections.abc import Sequence
from enum import Enum, StrEnum, IntEnum
from typing import Callable, TypeVar, Union
from xml.etree import ElementTree
from dataclasses import dataclass, field
from aiohttp import ClientSession, ClientResponseError, BasicAuth, ClientResponse, ClientConnectionError

ONE_DAY_IN_SECONDS = 60 * 60 * 24

_LOGGER = logging.getLogger(__name__)


class MediaServerInfo:

    def __init__(self, resp_dict: dict):
        self.version = resp_dict.get('ProgramVersion', 'Unknown')
        self.name = resp_dict.get('FriendlyName', 'Unknown')
        self.platform = resp_dict.get('Platform', 'Unknown')
        self.updated_at = datetime.datetime.utcnow()

    def __str__(self):
        return f'{self.name} [{self.version}]'

    def __eq__(self, other):
        if isinstance(other, MediaServerInfo):
            return self.name == other.name and self.version == other.version
        return False


class PlaybackInfo:

    def __init__(self, resp_info: dict, extra_fields: list[str]):
        self.zone_id = int(resp_info.get('ZoneID', -1))
        self.zone_name: str = resp_info.get('ZoneName', '')
        self.state: PlaybackState = PlaybackState(int(resp_info.get('State', -1)))
        self.file_key: int = int(resp_info.get('FileKey', -1))
        self.next_file_key: int = int(resp_info.get('NextFileKey', -1))
        self.position_ms: int = int(resp_info.get('PositionMS', 0))
        self.duration_ms: int = int(resp_info.get('DurationMS', 0))
        self.volume: float = float(resp_info.get('Volume', 0.0))
        self.muted: bool = resp_info.get('VolumeDisplay', '') == 'Muted'
        self.image_url: str = resp_info.get('ImageURL', '')
        self.name: str = resp_info.get('Name', '')
        self.live_input: bool = self.name == 'Ipc'
        # music only
        self.artist: str = resp_info.get('Artist', '')
        self.album: str = resp_info.get('Album', '')
        self.album_artist: str = resp_info.get('Album Artist (auto)', '')
        # TV only
        self.series: str = resp_info.get('Series', '')
        self.season: str = resp_info.get('Season', '')
        self.episode: str = resp_info.get('Episode', '')
        # custom fields
        self.extra_fields = {f: resp_info.get(f, '') for f in extra_fields}

        # noinspection PyBroadException
        try:
            self.media_type = MediaType(resp_info['Media Type'])
        except:
            self.media_type = MediaType.NOT_AVAILABLE

        # noinspection PyBroadException
        try:
            self.media_sub_type = MediaSubType(resp_info['Media Sub Type'])
        except:
            self.media_sub_type = MediaSubType.NOT_AVAILABLE

        if 'Playback Info' in resp_info:
            # TODO parse into a nested dict
            self.playback_info: str = resp_info.get('Playback Info', '')

    def as_dict(self) -> dict:
        """ converts the available info to a dict. """
        return {
            'name': self.name,
            'zone_id': self.zone_id,
            'zone_name': self.zone_name,
            'playback_state': self.state.name,
            'position_ms': self.position_ms,
            'duration_ms': self.duration_ms,
            'volume': self.volume,
            'muted': self.muted,
            'live_input': self.live_input,
            'artist': self.artist,
            'album': self.album,
            'album_artist': self.album_artist,
            'series': self.series,
            'season': self.season,
            'episode': self.episode,
            'media_type': self.media_type.name,
            'media_sub_type': self.media_sub_type.name,
            **self.extra_fields
        }

    def __str__(self):
        val = f'[{self.zone_name} : {self.state.name}]'
        if self.file_key != -1:
            val = f'{val} {self.file_key} ({self.media_type.name} / {self.media_sub_type.name})'
        return val


class ServerAddress:
    def __init__(self, content: dict):
        self.key_id = content.get('keyid', None)
        self.ip = content.get('ip', None)
        self.port = int(content.get('port', -1))
        self.local_ip_list = content.get('localiplist', '').split(',')
        self.remote_ip = content.get('ip', None)
        self.http_port = int(content.get('port', -1))
        self.https_port = int(content.get('https_port', -1))
        self.mac_address_list = content.get('macaddresslist', '').split(',')


class Zone:
    def __init__(self, content: dict, zone_index: int, active_zone_id: int):
        self.index = zone_index
        self.id = int(content.get(f"ZoneID{self.index}", -1))
        self.name = content.get(f"ZoneName{self.index}", '')
        self.guid = content.get(f"ZoneGUID{self.index}", '')
        self.is_dlna = True if (content.get(f"ZoneDLNA{self.index}", '0') == "1") else False
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


class PlaybackState(Enum):
    UNKNOWN = -1
    STOPPED = 0
    PAUSED = 1
    PLAYING = 2
    WAITING = 3


class MediaType(StrEnum):
    NOT_AVAILABLE = ''
    VIDEO = 'Video'
    AUDIO = 'Audio'
    DATA = 'Data'
    IMAGE = 'Image'
    TV = 'TV'
    PLAYLIST = 'Playlist'


class MediaSubType(StrEnum):
    NOT_AVAILABLE = ''
    ADULT = 'Adult'
    ANIMATION = 'Animation'
    AUDIOBOOK = 'Audiobook'
    BOOK = 'Book'
    CONCERT = 'Concert'
    EDUCATIONAL = 'Educational'
    ENTERTAINMENT = 'Entertainment'
    EXTRAS = 'Extras'
    HOME_VIDEO = 'Home Video'
    KARAOKE = 'Karaoke'
    MOVIE = 'Movie'
    MUSIC = 'Music'
    MUSIC_VIDEO = 'Music Video'
    OTHER = 'Other'
    PHOTO = 'Photo'
    PODCAST = 'Podcast'
    RADIO = 'Radio'
    RINGTONE = 'Ringtone'
    SHORT = 'Short'
    SINGLE = 'Single'
    SPORTS = 'Sports'
    STOCK = 'Stock'
    SYSTEM = 'System'
    TEST_CLIP = 'Test Clip'
    TRAILER = 'Trailer'
    TV_SHOW = 'TV Show'
    WORKOUT = 'Workout'


class KeyCommand(StrEnum):
    UP = 'Up'
    DOWN = 'Down'
    LEFT = 'Left'
    RIGHT = 'Right'
    ENTER = 'Enter'
    HOME = 'Home'
    END = 'End'
    PAGE_UP = 'Page Up'
    PAGE_DOWN = 'Page Down'
    CTRL = 'Ctrl'
    SHIFT = 'Shift'
    ALT = 'Alt'
    INSERT = 'Insert'
    MENU = 'Menu'
    DELETE = 'Delete'
    PLUS = '+'
    MINUS = '-'
    BACKSPACE = 'Backspace'
    ESCAPE = 'Escape'
    APPS = 'Apps'
    SPACE = 'Space'
    PRINT_SCREEN = 'Print Screen'
    TAB = 'Tab'


class ViewMode(IntEnum):
    """ From https://wiki.jriver.com/index.php/Media_Center_Core_Commands UIModes. """
    UNKNOWN = -2000
    NO_UI = -1000
    STANDARD = 0
    MINI = 1
    DISPLAY = 2
    THEATER = 3
    COVER = 4
    COUNT = 5


@dataclass
class LibraryField:
    name: str
    data_type: str
    edit_type: str
    display_name: str


@dataclass(order=True)
class BrowseRule:
    name: str
    categories: str
    search: str

    def get_names(self) -> list[str]:
        return [n for n in self.name.split('\\') if n]

    def get_categories(self) -> list[str]:
        return [c for c in self.categories.split('\\') if c]


@dataclass
class BrowsePath:
    name: str
    is_field: bool = False
    parent: BrowsePath | None = None
    children: list[BrowsePath] = field(default_factory=list)
    media_types: list[MediaType] = field(default_factory=list)
    media_sub_types: list[MediaSubType] = field(default_factory=list)

    @property
    def full_path(self) -> str:
        return f'{self.parent.full_path}/{self.name}' if self.parent else self.name

    @property
    def descendents(self) -> list[BrowsePath]:
        descendents = []
        for child in self.children:
            descendents.append(child)
            descendents += child.descendents
        return descendents

    @property
    def effective_media_types(self) -> list[MediaType]:
        if self.media_types:
            return self.media_types
        if self.parent:
            return self.parent.effective_media_types
        return []

    @property
    def effective_media_sub_types(self) -> list[MediaSubType]:
        if self.media_sub_types:
            return self.media_sub_types
        if self.parent:
            return self.parent.effective_media_sub_types
        return []


INPUT = TypeVar("INPUT", bound=Union[str, dict])
OUTPUT = TypeVar("OUTPUT", bound=Union[list, dict])


def get_mcws_connection(host: str, port: int, username: str | None = None, password: str | None = None,
                        ssl: bool = False, timeout: int = 5, session: ClientSession = None):
    """Returns a MCWS connection."""
    return MediaServerConnection(host, port, username, password, ssl, timeout, session)


async def _get(session: ClientSession, url: str, parser: Callable[[INPUT], tuple[bool, OUTPUT]],
               reader: Callable[[ClientResponse], INPUT], params: dict | None = None, timeout: int = 5,
               auth=None) -> tuple[bool, OUTPUT]:
    try:
        async with session.get(url, params=params, timeout=timeout, auth=auth) as resp:
            try:
                resp.raise_for_status()
                content = await reader(resp)
                return parser(content)
            except ClientResponseError as e:
                if e.status == 401:
                    raise InvalidAuthError from e
                elif e.status == 400:
                    raise InvalidRequestError from e
                elif e.status == 500:
                    t = resp.text()
                    import re
                    if re.fullmatch(r'<Response Status="Failure" Information="Function \'.*\' not found."/>', t):
                        raise UnsupportedRequestError from e
                    else:
                        raise MediaServerError from e
                else:
                    raise CannotConnectError from e
    except ClientConnectionError as e:
        raise CannotConnectError from e


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
        self._protocol = f'http{"s" if ssl else ""}'
        self._host = host
        self._port = port
        self._host_port = f'{host}:{port}'
        self._host_url = f'{self._protocol}://{self._host_port}'
        self._base_url = f"{self._host_url}/MCWS/v1"

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> str:
        return self._port

    @property
    def host_url(self) -> str:
        return self._host_url

    async def get(self, path: str, parser: Callable[[INPUT], tuple[bool, OUTPUT]],
                  reader: Callable[[ClientResponse], INPUT] = lambda r: r.text(),
                  params: dict | None = None) -> tuple[bool, OUTPUT]:
        """ Custom parsing of content returned from MCWS. """
        return await _get(self._session, self.get_mcws_url(path), parser, reader, params, timeout=self._timeout,
                          auth=self._auth)

    async def get_as_dict(self, path: str, params: dict | None = None) -> tuple[bool, dict]:
        """ parses MCWS XML Item list as a dict taken where keys are Item.@name and value is Item.text """
        return await _get(self._session, self.get_mcws_url(path), _to_dict, lambda r: r.text(), params,
                          timeout=self._timeout, auth=self._auth)

    async def get_as_json_list(self, path: str, params: dict | None = None) -> tuple[bool, list[dict]]:
        """ returns a json response as is (response must supply a list) """
        return await _get(self._session, self.get_mcws_url(path), lambda d: (True, d), lambda r: r.json(), params,
                          timeout=self._timeout, auth=self._auth)

    async def get_as_json_dict(self, path: str, params: dict | None = None) -> tuple[bool, dict]:
        """ returns a json response as is (response must supply a dict) """
        return await _get(self._session, self.get_mcws_url(path), lambda d: (True, d), lambda r: r.json(), params,
                          timeout=self._timeout, auth=self._auth)

    async def get_as_list(self, path: str, params: dict | None = None) -> tuple[bool, list]:
        """ parses MCWS XML Item list as a list of values taken from the element text """
        return await _get(self._session, self.get_mcws_url(path), _to_list, lambda r: r.text(), params,
                          timeout=self._timeout, auth=self._auth)

    def get_url(self, path: str) -> str:
        return f'{self._host_url}/{path}'

    def get_mcws_url(self, path: str) -> str:
        return f'{self._base_url}/{path}'

    async def close(self):
        """Close the connection if necessary."""
        if self._close_session_on_exit and self._session is not None:
            await self._session.close()
            self._session = None
            self._close_session_on_exit = False


def _to_dict(content: str) -> tuple[bool, dict]:
    """
    Converts the MCWS XML response into a dictionary with a flag to indicate if the response was "OK".
    Used where the child Item elements represent different fields (aka have the Name attribute) providing data about a
    single entity.
    """
    result: dict = {}
    root = ElementTree.fromstring(content)
    for child in root:
        result[child.attrib["Name"]] = child.text
    return root.attrib['Status'] == 'OK', result


def _to_list(content: str) -> tuple[bool, list]:
    """
    Converts the MCWS XML response into a list of values with a flag to indicate if the response was "OK".
    Used where the child Item elements have no name attribute and are just providing a list of distinct string values
    which are typically values from the same library field.
    """
    result: list = []
    root = ElementTree.fromstring(content)
    for child in root:
        result.append(child.text)
    return root.attrib['Status'] == 'OK', result


class MediaServer:
    """A high level interface for MCWS."""

    def __init__(self, connection: MediaServerConnection):
        self._conn = connection
        self._token = None
        self._token_obtained_at = 0
        self._media_server_info: MediaServerInfo | None = None

    @property
    def media_server_info(self) -> MediaServerInfo | None:
        return self._media_server_info

    @property
    def host(self) -> str:
        return self._conn.host

    @property
    def port(self) -> str:
        return self._conn.port

    async def close(self):
        await self._conn.close()

    def make_url(self, path: str) -> str:
        return self._conn.get_url(path)

    async def get_file_image_url(self, file_key: int) -> str:
        """ Get image URL for a file given the key. """
        await self._ensure_token()
        params = f'File={file_key}&Type=Thumbnail&ThumbnailSize=Large&Format=png&Token={self._token}'
        return f'{self._conn.get_mcws_url("File/GetImage")}?{params}'

    async def _ensure_token(self) -> None:
        now = time.time()
        if now - self._token_obtained_at > ONE_DAY_IN_SECONDS:
            await self.get_auth_token()

    async def get_browse_thumbnail_url(self, base_id: int = -1):
        """ the image thumbnail for the browse node id """
        await self._ensure_token()
        return f'{self._conn.get_mcws_url("Browse/Image")}?UseStackedImages=1&Format=jpg&ID={base_id}&Token={self._token}'

    async def alive(self) -> MediaServerInfo:
        """ returns info about the instance, no authentication required. """
        ok, resp = await self._conn.get_as_dict('Alive')
        self._media_server_info = MediaServerInfo(resp)
        return self._media_server_info

    async def get_auth_token(self) -> str:
        """ Get an authenticated token. """
        ok, resp = await self._conn.get_as_dict('Authenticate')
        self._token = resp['Token']
        self._token_obtained_at = time.time()
        return self._token

    async def get_zones(self) -> list[Zone]:
        """ all known zones """
        ok, resp = await self._conn.get_as_dict("Playback/Zones")
        num_zones = int(resp["NumberZones"])
        active_zone_id = int(resp['CurrentZoneID'])
        return [Zone(resp, i, active_zone_id) for i in range(num_zones)]

    async def get_library_fields(self) -> list[LibraryField]:
        def _parse(text: str) -> tuple[bool, list[LibraryField]]:
            result: list[LibraryField] = []
            root = ElementTree.fromstring(text)
            is_ok = root.attrib['Status'] == 'OK'
            if not is_ok or not root:
                return False, []
            if root[0].tag == 'Fields':
                for child in root[0]:
                    result.append(LibraryField(child.attrib['Name'], child.attrib['DataType'], child.attrib['EditType'],
                                               child.attrib['DisplayName']))
            return is_ok, result

        ok, resp = await self._conn.get('Library/Fields', _parse)
        if ok:
            return resp
        return []

    async def get_playback_info(self, zone: Zone | str | None = None,
                                extra_fields: list[str] | None = None) -> PlaybackInfo:
        """ info about the current state of playback in the specified zone. """
        params = self.__zone_params(zone)
        if not extra_fields:
            extra_fields = []
        default_fields = ['Media Type', 'Media Sub Type', 'Series', 'Season', 'Episode', 'Album Artist (auto)']
        params['Fields'] = ';'.join(set(extra_fields + default_fields))
        ok, resp = await self._conn.get_as_dict("Playback/Info", params=params)
        info = PlaybackInfo(resp, extra_fields)
        if info.image_url:
            await self._ensure_token()
            if self._token:
                info.image_url = f'{info.image_url}&Token={self._token}'
        return info

    @staticmethod
    def __zone_params(zone: Zone | str | None = None) -> dict:
        if isinstance(zone, str):
            return {
                'Zone': zone,
                'ZoneType': 'Name'
            }
        if isinstance(zone, Zone):
            return zone.as_query_params()
        return {}

    async def volume_up(self, step: float = 0.1, zone: Zone | str | None = None) -> float:
        """Send volume up command."""
        ok, resp = await self._conn.get_as_dict('Playback/Volume',
                                                params={'Level': step, 'Relative': 1, **self.__zone_params(zone)})
        return float(resp['Level'])

    async def volume_down(self, step: float = 0.1, zone: Zone | str | None = None) -> float:
        """Send volume down command."""
        ok, resp = await self._conn.get_as_dict('Playback/Volume',
                                                params={'Level': f'{"-" if step > 0 else ""}{step}', 'Relative': 1,
                                                        **self.__zone_params(zone)})
        return float(resp['Level'])

    async def set_volume_level(self, volume: float, zone: Zone | str | None = None) -> float:
        """Set volume level, range 0-1."""
        if volume < 0:
            raise ValueError(f'{volume} not in range 0-1')
        if volume > 1:
            raise ValueError(f'{volume} not in range 0-1')
        ok, resp = await self._conn.get_as_dict('Playback/Volume', params={'Level': volume, **self.__zone_params(zone)})
        return float(resp['Level'])

    async def mute(self, mute: bool, zone: Zone | str | None = None) -> bool:
        """Send (un)mute command."""
        ok, resp = await self._conn.get_as_dict('Playback/Mute',
                                                params={'Set': '1' if mute else '0', **self.__zone_params(zone)})
        return bool(int(resp['State']))

    async def play_pause(self, zone: Zone | str | None = None) -> bool:
        """Send play/pause command."""
        ok, resp = await self._conn.get_as_dict('Playback/PlayPause', params=self.__zone_params(zone))
        return ok

    async def play(self, zone: Zone | str | None = None) -> bool:
        """Send play command."""
        ok, resp = await self._conn.get_as_dict('Playback/Play', params=self.__zone_params(zone))
        return ok

    async def pause(self, zone: Zone | str | None = None) -> bool:
        """Send pause command."""
        ok, resp = await self._conn.get_as_dict('Playback/Pause', params=self.__zone_params(zone))
        return ok

    async def stop(self, zone: Zone | str | None = None) -> bool:
        """Send stop command."""
        ok, resp = await self._conn.get_as_dict('Playback/Stop', params=self.__zone_params(zone))
        return ok

    async def stop_all(self) -> bool:
        """Send stopAll command."""
        ok, resp = await self._conn.get_as_dict('Playback/StopAll')
        return ok

    async def next_track(self, zone: Zone | str | None = None) -> bool:
        """Send next track command."""
        ok, resp = await self._conn.get_as_dict('Playback/Next', params=self.__zone_params(zone))
        return ok

    async def previous_track(self, zone: Zone | str | None = None) -> bool:
        """Send previous track command."""
        # TODO does it go to the start of the current track?
        ok, resp = await self._conn.get_as_dict('Playback/Previous', params=self.__zone_params(zone))
        return ok

    async def media_seek(self, position: int, zone: Zone | str | None = None) -> bool:
        """seek to a specified position in ms."""
        ok, resp = await self._conn.get_as_dict('Playback/Position',
                                                params={'Position': position, **self.__zone_params(zone)})
        return ok

    async def play_item(self, item: str, zone: Zone | str | None = None) -> bool:
        ok, resp = await self._conn.get_as_dict('Playback/PlayByKey', params={'Key': item, **self.__zone_params(zone)})
        return ok

    async def play_playlist(self, playlist_id: str, playlist_type: str = 'Path',
                            zone: Zone | str | None = None) -> bool:
        """Play the given playlist."""
        ok, resp = await self._conn.get_as_dict('Playback/PlayPlaylist',
                                                params={'Playlist': playlist_id, 'PlaylistType': playlist_type,
                                                        **self.__zone_params(zone)})
        return ok

    async def play_file(self, file: str, zone: Zone | str | None = None) -> bool:
        """Play the given file."""
        ok, resp = await self._conn.get_as_dict('Playback/PlayByFilename',
                                                params={'Filenames': file, **self.__zone_params(zone)})
        return ok

    async def set_shuffle(self, shuffle: bool, zone: Zone | str | None = None) -> bool:
        """Set shuffle mode, for the first player."""
        ok, resp = await self._conn.get_as_dict('Control/MCC',
                                                params={'Command': '10005', 'Parameter': '4' if shuffle else '3',
                                                        **self.__zone_params(zone)})
        return ok

    async def clear_playlist(self, zone: Zone | str | None = None) -> bool:
        """Clear default playlist."""
        ok, resp = await self._conn.get_as_dict('Playback/ClearPlaylist', params=self.__zone_params(zone))
        return ok

    async def browse_children(self, base_id: int = -1) -> dict:
        """ get the nodes under the given browse id """
        ok, resp = await self._conn.get_as_dict('Browse/Children',
                                                params={'Version': 2, 'ErrorOnMissing': 0, 'ID': base_id})
        return resp

    async def browse_files(self, base_id: int = -1, fields: list[str] = None) -> list[dict]:
        """ get the files under the given browse id """
        field_list = ','.join(
            ['Key', 'Name', 'Media Type', 'Media Sub Type', 'Series', 'Season', 'Episode', 'Artist', 'Album', 'Track #',
             'Dimensions', 'HDR Format'] + (fields if fields else []))
        ok, resp = await self._conn.get_as_json_list('Browse/Files',
                                                     params={'ID': base_id, 'Action': 'JSON', 'Fields': field_list})
        return resp

    async def play_browse_files(self, base_id: int = -1, zone: Zone | str | None = None, play_next: bool | None = None):
        """ play the files under the given browse id """
        params = {
            'ID': base_id,
            'Action': 'Play',
            **self.__zone_params(zone)
        }
        if play_next is not None:
            params['PlayMode'] = 'NextToPlay' if play_next else 'Add'
        ok, resp = await self._conn.get_as_dict('Browse/Files', params=params)
        return resp

    async def play_search(self, query: str, zone: Zone | str | None = None, play_next: bool | None = None):
        """ play the files located by the query string. """
        if not query:
            raise ValueError('No query supplied')
        params = {
            'Query': query,
            'Action': 'Play',
            **self.__zone_params(zone)
        }
        if play_next is not None:
            params['PlayMode'] = 'NextToPlay' if play_next else 'Add'
        ok, resp = await self._conn.get_as_dict('Files/Search', params=params)
        return resp

    async def send_key_presses(self, keys: Sequence[KeyCommand | str], focus: bool = True) -> bool:
        """ send a sequence of key presses """
        if not keys:
            raise ValueError('No keys')
        ok, resp = await self._conn.get_as_dict('Control/Key', params={
            'Key': ';'.join((str(k) if isinstance(k, Enum) else ';'.join(k) for k in keys if k)),
            'Focus': 1 if focus else 0
        })
        return ok

    async def send_mcc(self, command: int, param: int | None = None, zone: Zone | str | None = None,
                       block: bool = True) -> bool:
        """ send the MCC command """
        params = {
            'Command': command,
            'Block': 1 if block else 0,
            **self.__zone_params(zone)
        }
        if param is not None:
            params['Parameter'] = param
        ok, resp = await self._conn.get_as_dict('Control/MCC', params=params)
        return ok

    async def set_active_zone(self, zone: Zone | str) -> bool:
        """ set the active zone """
        if not zone:
            raise ValueError('zone is required')
        ok, resp = await self._conn.get_as_dict('Playback/SetZone', params=self.__zone_params(zone))
        return ok

    async def get_view_mode(self) -> ViewMode:
        """ Get the current UI mode. """
        ok, resp = await self._conn.get_as_dict('UserInterface/Info')
        # noinspection PyBroadException
        try:
            return ViewMode(int(resp['Mode']))
        except:
            return ViewMode.UNKNOWN

    async def get_browse_rules(self, view_type: str = 'Remote') -> list[BrowseRule]:
        """ Get the configured BrowseRule list. Only supported from 32.0.6 onwards. view_type is only honoured from 32.0.7 onwards."""

        def _parse(text: str) -> tuple[bool, list[BrowseRule]]:
            result: list[BrowseRule] = []
            root = ElementTree.fromstring(text)
            is_ok = root.attrib['Status'] == 'OK'
            if not is_ok or not root:
                return False, []
            for child in root:
                result.append(BrowseRule(child.attrib['Name'], child.attrib['Categories'], child.attrib['Search']))
            return is_ok, result

        try:
            ok, resp = await self._conn.get('Browse/Rules', _parse, params={'Type': view_type})
            return resp
        except UnsupportedRequestError:
            return []


class CannotConnectError(Exception):
    """Exception to indicate an error in connection."""


class InvalidAuthError(Exception):
    """Exception to indicate an error in authentication."""


class MediaServerError(Exception):
    """Exception to indicate a failure internal to the server. """


class InvalidRequestError(Exception):
    """Exception to indicate a malformed request. """


class InvalidAccessKeyError(Exception):
    """Exception to indicate the access key is invalid. """


class UnsupportedRequestError(MediaServerError):
    """ Exception to indicate a request for an MCWS function not supported by the server. """


async def try_connect(
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        session: ClientSession,
        ssl: bool = False,
        timeout: int = 5,
) -> MediaServer:
    """Try to connect to the given host/port."""
    _LOGGER.debug("Connecting to %s:%s", host, port)
    conn = get_mcws_connection(
        host,
        port,
        username=username,
        password=password,
        ssl=ssl,
        timeout=timeout,
        session=session,
    )
    ms = MediaServer(conn)
    if not await ms.get_auth_token():
        raise CannotConnect("Unexpected response")
    await ms.alive()
    return ms


async def load_media_server(access_key: str | None = None, host: str | None = None, port: int = 0,
                            username: str | None = None, password: str | None = None, use_ssl: bool = False,
                            session: ClientSession | None = None, timeout: int = 5) -> tuple[MediaServer, list[str]]:
    """Use the supplied details to obtain a MediaServer connection."""
    close_it = False
    if session is None:
        session = ClientSession()
        close_it = True

    try:
        if access_key:
            _LOGGER.debug("Looking up access key %s", access_key)
            server_info: ServerAddress | None = await resolve_access_key(
                access_key, session
            )
            if server_info:
                for ip in server_info.local_ip_list:
                    try:
                        ms = await try_connect(
                            ip,
                            server_info.https_port if use_ssl else server_info.http_port,
                            username,
                            password,
                            session,
                            ssl=use_ssl,
                            timeout=timeout,
                        )
                    except CannotConnectError:
                        continue
                    if ms:
                        _LOGGER.debug(
                            "Access key %s resolved to %s:%s",
                            access_key,
                            ip,
                            server_info.port,
                        )
                        return ms, server_info.mac_address_list
            else:
                raise InvalidAccessKeyError()
        ms = await try_connect(
            host, port, username, password, session, ssl=use_ssl, timeout=timeout
        )
        return ms, []
    finally:
        if close_it:
            session.close()


async def resolve_access_key(access_key: str, session: ClientSession | None) -> ServerAddress | None:
    """ Resolve an access key. """
    close_it = False
    if session is None:
        session = ClientSession()
        close_it = True

    def _parse(content: str) -> tuple[bool, dict]:
        result: dict = {}
        root = ElementTree.fromstring(content)
        for child in root:
            result[child.tag] = child.text
        return root.attrib['Status'] == 'OK', result

    try:
        ok, values = await _get(session, 'http://webplay.jriver.com/libraryserver/lookup', _parse, lambda r: r.text(),
                                {'id': access_key})
        return ServerAddress(values) if ok else None
    finally:
        if close_it:
            session.close()


def _parse_search(search: str) -> tuple[list[MediaType], list[MediaSubType]]:
    """Attempt to find MediaType and MediaSubType from the search query. """
    mt: list[MediaType] = []
    mst: list[MediaSubType] = []
    if '[Media Type]=' in search:
        def _safe_parse(t: str) -> MediaType | None:
            try:
                return MediaType(t[1:t.index(']')])
            except:
                return None

        mt = [_safe_parse(t) for t in search.split('[Media Type]=')[1].split(',')]

    if '[Media Sub Type]=' in search:
        def _safe_parse(t: str) -> MediaSubType | None:
            try:
                return MediaSubType(t[1:t.index(']')])
            except:
                return None

        mst = [_safe_parse(t) for t in search.split('[Media Sub Type]=')[1].split(',')]

    return [m for m in mt if m], [m for m in mst if m]


def convert_browse_rules(rules: list[BrowseRule], flat: bool = False, infer_media_types: bool = True) -> list[BrowsePath]:
    """ Convert the rules into a tree of paths. """
    paths: list[BrowsePath] = []
    all_paths: list[BrowsePath] = []
    sorted_rules = sorted(rules, key=lambda r: (r.name, len(r.get_names()), len(r.get_categories())))
    for rule in sorted_rules:
        tokens = rule.get_names()
        mt, mst = _parse_search(rule.search)
        path = BrowsePath(tokens[-1])
        path.media_types = mt
        path.media_sub_types = mst
        if len(tokens) == 1:
            paths.append(path)
            all_paths.append(path)
        else:
            target_path = '/'.join(tokens[:-1])
            parent = next((p for p in all_paths if p.full_path == target_path), None)
            if parent:
                parent.children.append(path)
                all_paths.append(path)
                path.parent = parent
        if rule.categories:
            for category in rule.get_categories():
                parent = path
                path = BrowsePath(category, True)
                path.parent = parent
                parent.children.append(path)

    if infer_media_types is True:
        _infer_media_types(paths)
    return all_paths if flat else paths


def parse_browse_paths_from_text(input_rules: list[str]) -> list[BrowsePath]:
    """Convert user provided strings to BrowsePaths via a convertion to BrowseRule."""
    browse_rules: list[BrowseRule] = []
    for input_rule in input_rules:
        vals = input_rule.split('|', 2)
        names = vals[0].split(',')
        for idx, name in enumerate(names):
            full_name = '\\'.join(names[0: idx+1])
            match = next((rule for rule in browse_rules if rule.name == full_name), None)
            if not match:
                match = BrowseRule(full_name, "", "")
                browse_rules.append(match)
            if idx == len(names) - 1 and len(vals) > 1:
                match.categories = '\\'.join(vals[1].split(','))
    return convert_browse_rules(browse_rules)


def _infer_media_types(paths: list[BrowsePath]) -> list[BrowsePath]:
    for path in paths:
        if path.name == 'Audio':
            path.media_types = [MediaType.AUDIO]
            for descendant in path.descendents:
                if descendant.name == 'Podcasts':
                    descendant.media_sub_types = [MediaSubType.PODCAST]
                elif descendant.name in ['Album', 'Artist', 'Composer']:
                    descendant.media_sub_types = [MediaSubType.MUSIC]
                elif descendant.name in ['Audiobooks']:
                    descendant.media_sub_types = [MediaSubType.AUDIOBOOK]
        elif path.name == 'Images':
            path.media_types = [MediaType.IMAGE]
        elif path.name == 'Video':
            path.media_types = [MediaType.VIDEO]
            for descendant in path.descendents:
                if descendant.name.startswith('Movies'):
                    descendant.media_sub_types = [MediaSubType.MOVIE]
                elif descendant.name == 'Shows':
                    descendant.media_sub_types = [MediaSubType.TV_SHOW]
                elif descendant.name == 'Music':
                    descendant.media_sub_types = [MediaSubType.MUSIC_VIDEO]
        elif path.name == 'Playlists':
            path.media_types = [MediaType.PLAYLIST]
        elif path.name == 'Audiobooks':
            path.media_types = [MediaType.AUDIO]
            path.media_sub_types = [MediaSubType.AUDIOBOOK]
    return paths


def search_for_path(paths: list[BrowsePath], target_path: list[str]) -> BrowsePath | None:
    """
    Search the BrowsePath identified by the specified path provided a list of individual node names.
    Only non field tags are examined. """
    if not target_path:
        return None

    def _search(level: int, search_paths: list[BrowsePath] | None) -> BrowsePath | None:
        if not search_paths:
            return None
        for path in search_paths:
            if path.is_field:
                continue
            if path.name == target_path[level - 1]:
                if len(target_path) == level:
                    return path
                if path.descendents and all(c.is_field for c in path.descendents):
                    if len(path.descendents) + level >= len(target_path):
                        return path.descendents[len(target_path[level:]) - 1]
                return _search(level + 1, path.children)

    return _search(1, paths)
