import datetime
from enum import Enum, StrEnum


class MediaServerInfo:

    def __init__(self, resp_dict: dict):
        self.version = resp_dict['ProgramVersion']
        self.name = resp_dict['FriendlyName']
        self.platform = resp_dict['Platform']
        self.updated_at = datetime.datetime.utcnow()

    def __str__(self):
        return f'{self.name} [{self.version}]'

    def __eq__(self, other):
        if isinstance(other, MediaServerInfo):
            return self.name == other.name and self.version == other.version
        return False


class PlaybackInfo:
    def __init__(self, resp_info: dict):
        self.zone_id = int(resp_info['ZoneID'])
        self.zone_name: str = resp_info['ZoneName']
        self.state: PlaybackState = PlaybackState(int(resp_info['State']))
        self.file_key: int = int(resp_info['FileKey'])
        self.next_file_key: int = int(resp_info['NextFileKey'])
        self.position_ms: int = int(resp_info['PositionMS'])
        self.duration_ms: int = int(resp_info['DurationMS'])
        self.volume: float = float(resp_info['Volume'])
        self.muted: bool = resp_info['VolumeDisplay'] == 'Muted'
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

    def __str__(self):
        val = f'[{self.zone_name} : {self.state.name}]'
        if self.file_key != -1:
            val = f'{val} {self.file_key} ({self.media_type.name} / {self.media_sub_type.name})'
        return val


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


class PlaybackState(Enum):
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
