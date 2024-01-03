"""Implementation of a MCWS inteface."""
from collections.abc import Sequence
from typing import Callable, TypeVar, Union
from xml.etree import ElementTree

from aiohttp import ClientSession, ClientResponseError, BasicAuth, ClientResponse

from .domain import MediaServerInfo, PlaybackInfo, Zone, KeyCommand

INPUT = TypeVar("INPUT", bound=Union[str, dict])
OUTPUT = TypeVar("OUTPUT", bound=Union[list, dict])


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
        self._host_url = f"http{'s' if ssl else ''}://{host}:{port}"
        self._base_url = f"{self._host_url}/MCWS/v1"

    @property
    def host_url(self):
        return self._host_url

    async def get_as_dict(self, path: str, params: dict | None = None) -> tuple[bool, dict]:
        """ parses MCWS XML Item list as a dict taken where keys are Item.@name and value is Item.text """
        return await self.__get(path, _to_dict, lambda r: r.text(), params)

    async def get_as_json_list(self, path: str, params: dict | None = None) -> tuple[bool, list]:
        """ returns a json response as is (response must supply a list) """
        return await self.__get(path, lambda d: (True, d), lambda r: r.json(), params)

    async def get_as_json_dict(self, path: str, params: dict | None = None) -> tuple[bool, dict]:
        """ returns a json response as is (response must supply a dict) """
        return await self.__get(path, lambda d: (True, d), lambda r: r.json(), params)

    async def get_as_list(self, path: str, params: dict | None = None) -> tuple[bool, list]:
        """ parses MCWS XML Item list as a list of values taken from the element text """
        return await self.__get(path, _to_list, lambda r: r.text(), params)

    async def __get(self, path: str, parser: Callable[[INPUT], tuple[bool, OUTPUT]],
                    reader: Callable[[ClientResponse], INPUT], params: dict | None = None) -> tuple[bool, OUTPUT]:
        async with self._session.get(self.get_url(path), params=params, timeout=self._timeout, auth=self._auth) as resp:
            try:
                resp.raise_for_status()
                content = await reader(resp)
                return parser(content)
            except ClientResponseError as e:
                if e.status == 401:
                    raise InvalidAuthError from e
                else:
                    raise CannotConnectError from e

    def get_url(self, path: str) -> str:
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

    async def close(self):
        await self._conn.close()

    def image_url(self, path: str) -> str:
        return f'{self._conn.host_url}/{path}'

    async def alive(self) -> MediaServerInfo:
        """ returns true if server allows the connection. """
        ok, resp = await self._conn.get_as_dict('Alive')
        return MediaServerInfo(resp)

    async def get_zones(self) -> list[Zone]:
        """ all known zones """
        ok, resp = await self._conn.get_as_dict("Playback/Zones")
        num_zones = int(resp["NumberZones"])
        active_zone_id = resp['CurrentZoneID']
        return [Zone(resp, i, active_zone_id) for i in range(num_zones)]

    async def get_playback_info(self, zone: Zone | None = None, extra_fields: list[str] | None = None) -> PlaybackInfo:
        """ info about the current state of playback in the specified zone. """
        params = self.__zone_params(zone)
        if not extra_fields:
            extra_fields = []
        extra_fields.append('Media Type')
        extra_fields.append('Media Sub Type')
        extra_fields.append('Series')
        extra_fields.append('Season')
        extra_fields.append('Episode')
        extra_fields.append('Album Artist (auto)')
        params['Fields'] = ';'.join(set(extra_fields))
        ok, resp = await self._conn.get_as_dict("Playback/Info", params=params)
        return PlaybackInfo(resp)

    @staticmethod
    def __zone_params(zone: Zone | None = None) -> dict:
        return zone.as_query_params() if zone else {}

    async def volume_up(self, step: float = 0.1, zone: Zone | None = None) -> float:
        """Send volume up command."""
        ok, resp = await self._conn.get_as_dict('Playback/Volume',
                                                params={'Level': step, 'Relative': 1, **self.__zone_params(zone)})
        return float(resp['Level'])

    async def volume_down(self, step: float = 0.1, zone: Zone | None = None) -> float:
        """Send volume down command."""
        ok, resp = await self._conn.get_as_dict('Playback/Volume',
                                                params={'Level': f'{"-" if step > 0 else ""}{step}', 'Relative': 1,
                                                        **self.__zone_params(zone)})
        return float(resp['Level'])

    async def set_volume_level(self, volume: float, zone: Zone | None = None) -> float:
        """Set volume level, range 0-100."""
        if volume < 0:
            raise ValueError(f'{volume} not in range 0-100')
        if volume > 100:
            raise ValueError(f'{volume} not in range 0-100')
        volume = volume / 100
        ok, resp = await self._conn.get_as_dict('Playback/Volume', params={'Level': volume, **self.__zone_params(zone)})
        return float(resp['Level'])

    async def mute(self, mute: bool, zone: Zone | None = None) -> bool:
        """Send (un)mute command."""
        ok, resp = await self._conn.get_as_dict('Playback/Mute',
                                                params={'Set': '1' if mute else '0', **self.__zone_params(zone)})
        return ok

    async def play_pause(self, zone: Zone | None = None) -> bool:
        """Send play/pause command."""
        ok, resp = await self._conn.get_as_dict('Playback/PlayPause', params=self.__zone_params(zone))
        return ok

    async def play(self, zone: Zone | None = None) -> bool:
        """Send play command."""
        ok, resp = await self._conn.get_as_dict('Playback/Play', params=self.__zone_params(zone))
        return ok

    async def pause(self, zone: Zone | None = None) -> bool:
        """Send pause command."""
        ok, resp = await self._conn.get_as_dict('Playback/Pause', params=self.__zone_params(zone))
        return ok

    async def stop(self, zone: Zone | None = None) -> bool:
        """Send stop command."""
        ok, resp = await self._conn.get_as_dict('Playback/Stop', params=self.__zone_params(zone))
        return ok

    async def stop_all(self) -> bool:
        """Send stopAll command."""
        ok, resp = await self._conn.get_as_dict('Playback/StopAll')
        return ok

    async def next_track(self, zone: Zone | None = None) -> bool:
        """Send next track command."""
        ok, resp = await self._conn.get_as_dict('Playback/Next', params=self.__zone_params(zone))
        return ok

    async def previous_track(self, zone: Zone | None = None) -> bool:
        """Send previous track command."""
        # TODO does it go to the start of the current track?
        ok, resp = await self._conn.get_as_dict('Playback/Previous', params=self.__zone_params(zone))
        return ok

    async def media_seek(self, position: int, zone: Zone | None = None) -> bool:
        """seek to a specified position in ms."""
        ok, resp = await self._conn.get_as_dict('Playback/Position',
                                                params={'Position': position, **self.__zone_params(zone)})
        return ok

    async def play_item(self, item: str, zone: Zone | None = None) -> bool:
        ok, resp = await self._conn.get_as_dict('Playback/PlayByKey', params={'Key': item, **self.__zone_params(zone)})
        return ok

    async def play_playlist(self, playlist_id: str, zone: Zone | None = None) -> bool:
        """Play the given playlist."""
        ok, resp = await self._conn.get_as_dict('Playback/PlayPlaylist',
                                                params={'Playlist': playlist_id, **self.__zone_params(zone)})
        return ok

    async def play_file(self, file: str, zone: Zone | None = None) -> bool:
        """Play the given file."""
        ok, resp = await self._conn.get_as_dict('Playback/PlayByFilename',
                                                params={'Filenames': file, **self.__zone_params(zone)})
        return ok

    async def set_shuffle(self, shuffle: bool, zone: Zone | None = None) -> bool:
        """Set shuffle mode, for the first player."""
        ok, resp = await self._conn.get_as_dict('Control/MCC',
                                                params={'Command': '10005', 'Parameter': '4' if shuffle else '3',
                                                        **self.__zone_params(zone)})
        return ok

    async def clear_playlist(self, zone: Zone | None = None) -> bool:
        """Clear default playlist."""
        ok, resp = await self._conn.get_as_dict('Playback/ClearPlaylist', params=self.__zone_params(zone))
        return ok

    async def browse_children(self, base_id: int = -1) -> dict:
        """ get the nodes under the given browse id """
        ok, resp = await self._conn.get_as_dict('Browse/Children',
                                                params={'Version': 2, 'ErrorOnMissing': 0, 'ID': base_id})
        return resp

    async def browse_files(self, base_id: int = -1) -> list:
        """ get the files under the given browse id """
        ok, resp = await self._conn.get_as_json_list('Browse/Files', params={'ID': base_id, 'Action': 'JSON'})
        return resp

    async def play_browse_files(self, base_id: int = -1, zone: Zone | None = None, play_next: bool = True):
        """ play the files under the given browse id """
        ok, resp = await self._conn.get_as_dict('Browse/Files', params={
            'ID': base_id,
            'Action': 'Play',
            'PlayMode': 'NextToPlay' if play_next else 'Add',
            **self.__zone_params(zone)
        })
        return resp

    def get_browse_thumbnail_url(self, base_id: int = -1):
        """ the image thumbnail for the browse node id """
        return f'{self._conn.get_url("Browse/Image")}?UseStackedImages=1&Format=jpg&ID={base_id}'

    async def send_key_presses(self, keys: Sequence[KeyCommand | str], focus: bool = True) -> bool:
        """ send a sequence of key presses """
        ok, resp = await self._conn.get_as_dict('Command/Key', params={
            'Key': ';'.join((str(k) for k in keys)),
            'Focus': 1 if focus else 0
        })
        return ok

    async def send_mcc(self, command: int, param: int | None = None, zone: Zone | None = None,
                       block: bool = False) -> bool:
        """ send the MCC command """
        ok, resp = await self._conn.get_as_dict('Command/MCC', params={
            'Command': command,
            'Parameter': param if param else 0,
            'Block': 1 if block else 0,
            **self.__zone_params(zone)
        })
        return ok

    async def set_active_zone(self, zone: Zone) -> bool:
        """ set the active zone """
        if not zone:
            raise ValueError('zone is required')
        ok, resp = await self._conn.get_as_dict('Playback/SetZone', params=self.__zone_params(zone))
        return ok


class CannotConnectError(Exception):
    """Exception to indicate an error in connection."""


class InvalidAuthError(Exception):
    """Exception to indicate an error in authentication."""
