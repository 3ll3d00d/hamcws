import datetime

import pytest
from aiohttp import web
from aiohttp.web_response import Response

from hamcws import get_mcws_connection, MediaServer, MediaServerInfo, MediaType, KeyCommand, ViewMode, PlaybackState, \
    MediaSubType, BrowseRule, convert_browse_rules, parse_browse_paths_from_text, search_for_path, AudioPath


def make_handler(text: str, ctype: str = 'text/xml'):
    async def handler(request: web.Request) -> web.Response:
        return Response(
            text=text,
            content_type=ctype,
            charset='utf-8'
        )

    return handler


async def make_ms(func: str, aiohttp_server, handler, prefix: str = 'MCWS/v1/'):
    app = web.Application()
    routes = [web.get(f"/{prefix}{func}", handler)]
    if func != 'Authenticate':
        routes.append(web.get(f"/{prefix}Authenticate", make_handler('''<Response Status="OK">
<Item Name="Token">1234567</Item>
<Item Name="ReadOnly">0</Item>
<Item Name="PreLicensed">0</Item>
</Response>''')))
    app.add_routes(routes)
    server = await aiohttp_server(app)
    return MediaServer(get_mcws_connection('localhost', server.port))


@pytest.fixture
async def alive_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="RuntimeGUID">{123456-7890-1234-5678-90123456789}</Item>
<Item Name="LibraryVersion">24</Item>
<Item Name="ProgramName">JRiver Media Center</Item>
<Item Name="ProgramVersion">31.0.83</Item>
<Item Name="FriendlyName">MyServer</Item>
<Item Name="ProductVersion">31 Linux</Item>
<Item Name="Platform">Linux</Item>
</Response>''')
    ms = await make_ms('Alive', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_alive(alive_stub):
    start = datetime.datetime.utcnow()
    assert not alive_stub.media_server_info
    resp = await alive_stub.alive()
    assert resp
    assert resp.name == 'MyServer'
    assert resp.version == '31.0.83'
    assert resp.platform == 'Linux'
    assert resp.updated_at > start
    assert alive_stub.media_server_info
    assert alive_stub.media_server_info == resp


@pytest.fixture
async def auth_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="Token">ABCDEF</Item>
<Item Name="ReadOnly">1</Item>
<Item Name="PreLicensed">0</Item>
</Response>''')
    ms = await make_ms('Authenticate', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_authenticate(auth_stub):
    assert await auth_stub.get_auth_token() == 'ABCDEF'
    url = await auth_stub.get_file_image_url(123456)
    assert url == f'http://{auth_stub.host}:{auth_stub.port}/MCWS/v1/File/GetImage?File=123456&Type=Thumbnail&ThumbnailSize=Large&Format=png&Token=ABCDEF'

    url = await auth_stub.get_browse_thumbnail_url(654321)
    assert url == f'http://{auth_stub.host}:{auth_stub.port}/MCWS/v1/Browse/Image?UseStackedImages=1&Format=jpg&ID=654321&Token=ABCDEF'


@pytest.fixture
async def zones_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="NumberZones">3</Item>
<Item Name="CurrentZoneID">10081</Item>
<Item Name="CurrentZoneIndex">0</Item>
<Item Name="ZoneName0">Player</Item>
<Item Name="ZoneID0">10081</Item>
<Item Name="ZoneGUID0">{xxxx-xxxx}</Item>
<Item Name="ZoneDLNA0">0</Item>
<Item Name="ZoneName1">Family Room</Item>
<Item Name="ZoneID1">10074</Item>
<Item Name="ZoneGUID1">{xxxx-xxxx}</Item>
<Item Name="ZoneDLNA1">1</Item>
<Item Name="ZoneName2">Den</Item>
<Item Name="ZoneID2">10087</Item>
<Item Name="ZoneGUID2">{xxxx-xxxx}</Item>
<Item Name="ZoneDLNA2">1</Item>
</Response>''')
    ms = await make_ms('Playback/Zones', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_zones(zones_stub):
    zones = await zones_stub.get_zones()
    assert zones
    assert len(zones) == 3

    assert zones[0].index == 0
    assert zones[0].id == 10081
    assert zones[0].name == 'Player'
    assert not zones[0].is_dlna
    assert zones[0].active

    assert zones[1].index == 1
    assert zones[1].id == 10074
    assert zones[1].name == 'Family Room'
    assert zones[1].is_dlna
    assert not zones[1].active

    assert zones[2].index == 2
    assert zones[2].id == 10087
    assert zones[2].name == 'Den'
    assert zones[2].is_dlna
    assert not zones[2].active


@pytest.fixture
async def no_name_zones_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="NumberZones">1</Item>
<Item Name="CurrentZoneID">10081</Item>
<Item Name="CurrentZoneIndex">0</Item>
<Item Name="ZoneID0">10081</Item>
<Item Name="ZoneGUID0">{xxxx-xxxx}</Item>
<Item Name="ZoneDLNA0">0</Item>
</Response>''')
    ms = await make_ms('Playback/Zones', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_no_name_zones(no_name_zones_stub):
    zones = await no_name_zones_stub.get_zones()
    assert zones
    assert len(zones) == 1

    assert zones[0].index == 0
    assert zones[0].id == 10081
    assert zones[0].name == ''
    assert not zones[0].is_dlna
    assert zones[0].active


@pytest.fixture
async def library_fields_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Fields>
<Field Name="Filename" DataType="Path" EditType="Filename" DisplayName="Filename"/>
<Field Name="Name" DataType="String" EditType="Standard" DisplayName="Name"/>
<Field Name="Artist" DataType="List" EditType="Standard" DisplayName="Artist"/>
</Fields>
</Response>''')
    ms = await make_ms('Library/Fields', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_library_fields(library_fields_stub):
    fields = await library_fields_stub.get_library_fields()
    assert fields
    assert len(fields) == 3

    assert fields[0].name == 'Filename'
    assert fields[0].display_name == 'Filename'
    assert fields[0].data_type == 'Path'
    assert fields[0].edit_type == 'Filename'

    assert fields[1].name == 'Name'
    assert fields[1].display_name == 'Name'
    assert fields[1].data_type == 'String'
    assert fields[1].edit_type == 'Standard'

    assert fields[2].name == 'Artist'
    assert fields[2].display_name == 'Artist'
    assert fields[2].data_type == 'List'
    assert fields[2].edit_type == 'Standard'


@pytest.fixture
async def playback_info_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="ZoneID">10081</Item>
<Item Name="ZoneName">Player</Item>
<Item Name="State">0</Item>
<Item Name="FileKey">-1</Item>
<Item Name="NextFileKey">-1</Item>
<Item Name="PositionMS">0</Item>
<Item Name="DurationMS">1229000</Item>
<Item Name="ElapsedTimeDisplay">0:00</Item>
<Item Name="RemainingTimeDisplay">Live</Item>
<Item Name="TotalTimeDisplay">Live</Item>
<Item Name="PositionDisplay">0:00 / Live</Item>
<Item Name="PlayingNowPosition">-1</Item>
<Item Name="PlayingNowTracks">0</Item>
<Item Name="PlayingNowPositionDisplay">0 of 0</Item>
<Item Name="PlayingNowChangeCounter">2</Item>
<Item Name="Bitrate">0</Item>
<Item Name="Bitdepth">0</Item>
<Item Name="SampleRate">0</Item>
<Item Name="Channels">0</Item>
<Item Name="Chapter">0</Item>
<Item Name="Volume">0.44999</Item>
<Item Name="VolumeDisplay">45% (-27.5 dB)</Item>
<Item Name="ImageURL">MCWS/v1/File/GetImage?File=4294967295</Item>
<Item Name="Name">Media Center</Item>
</Response>''')
    ms = await make_ms('Playback/Info', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_playback_info(playback_info_stub):
    info = await playback_info_stub.get_playback_info()
    assert info
    assert info.name == 'Media Center'
    assert info.position_ms == 0
    assert info.duration_ms == 1229000
    assert info.volume == 0.44999
    assert info.zone_name == 'Player'
    assert info.zone_id == 10081
    assert info.state == PlaybackState.STOPPED
    assert info.image_url.endswith('MCWS/v1/File/GetImage?File=4294967295&Token=1234567')
    assert not info.episode
    assert not info.season
    assert not info.series
    assert not info.album_artist
    assert not info.album
    assert not info.artist
    assert info.as_dict() == {
        'name': 'Media Center',
        'zone_id': 10081,
        'zone_name': 'Player',
        'playback_state': PlaybackState.STOPPED.name,
        'position_ms': 0,
        'duration_ms': 1229000,
        'volume': 0.44999,
        'muted': False,
        'live_input': False,
        'artist': '',
        'album': '',
        'album_artist': '',
        'series': '',
        'season': '',
        'episode': '',
        'media_type': MediaType.NOT_AVAILABLE.name,
        'media_sub_type': MediaSubType.NOT_AVAILABLE.name,
    }
    assert str(info) == '[Player : STOPPED]'


@pytest.fixture
async def no_playback_info_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK"></Response>''')
    ms = await make_ms('Playback/Info', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_no_playback_info(no_playback_info_stub):
    info = await no_playback_info_stub.get_playback_info()
    assert info
    assert info.name == ''
    assert info.position_ms == 0
    assert info.duration_ms == 0
    assert info.volume == 0.0
    assert info.zone_name == ''
    assert info.zone_id == -1
    assert info.state == PlaybackState.UNKNOWN
    assert not info.episode
    assert not info.season
    assert not info.series
    assert not info.album_artist
    assert not info.album
    assert not info.artist


@pytest.fixture
async def volume_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="Level">0.54999</Item>
<Item Name="Display">55% (-22.5 dB)</Item>
</Response>''')
    ms = await make_ms('Playback/Volume', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_volume(volume_stub):
    assert await volume_stub.volume_up() == 0.54999
    assert await volume_stub.volume_down() == 0.54999
    assert await volume_stub.volume_up(0.2) == 0.54999
    assert await volume_stub.volume_down(0.3) == 0.54999
    assert await volume_stub.set_volume_level(0.54999) == 0.54999


@pytest.fixture
async def mute_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="State">1</Item>
</Response>''')
    ms = await make_ms('Playback/Mute', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_mute(mute_stub):
    assert await mute_stub.mute(True) is True


@pytest.fixture
async def unmute_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="State">0</Item>
</Response>''')
    ms = await make_ms('Playback/Mute', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_unmute(unmute_stub):
    assert await unmute_stub.mute(False) is False


@pytest.fixture
async def ok_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('<Response Status="OK"/>')
    ms = await make_ms('{tail:.*}', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_ok_commands(ok_stub):
    assert await ok_stub.play() is True
    assert await ok_stub.play_pause() is True
    assert await ok_stub.pause() is True
    assert await ok_stub.stop() is True
    assert await ok_stub.next_track() is True
    assert await ok_stub.previous_track() is True
    assert await ok_stub.stop_all() is True


@pytest.fixture
async def fail_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('<Response Status="Failure"/>')
    ms = await make_ms('{tail:.*}', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_fail_commands(fail_stub):
    assert await fail_stub.play() is False
    assert await fail_stub.play_pause() is False
    assert await fail_stub.pause() is False
    assert await fail_stub.stop() is False
    assert await fail_stub.next_track() is False
    assert await fail_stub.previous_track() is False
    assert await fail_stub.stop_all() is False


@pytest.fixture
async def unknown_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('<Response Status="Failure" Information="Function \'Browse/test\' not found."/>')
    ms = await make_ms('{tail:.*}', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_unsupported_command(fail_stub):
    assert await fail_stub.get_browse_rules() == []


@pytest.fixture
async def browse_rules_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="Images\Album" Categories="Album" Search=""/>
<Item Name="Audio\Genre" Categories="Genre\Album Artist (auto)\Album" Search=""/>
<Item Name="Audio\Highly Rated" Categories="" Search="[Rating]=>=4"/>
</Response>''')
    ms = await make_ms('Browse/Rules', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_browse_rules(browse_rules_stub):
    expected: list[BrowseRule] = [
        BrowseRule("Images\Album", "Album", ""),
        BrowseRule("Audio\Genre", "Genre\Album Artist (auto)\Album", ""),
        BrowseRule("Audio\Highly Rated", "", "[Rating]=>=4"),
    ]
    assert await browse_rules_stub.get_browse_rules() == expected
    br = BrowseRule("Images\Album", "Album", "")
    assert br.get_names() == ['Images', 'Album']
    assert br.get_categories() == ['Album']
    assert not br.search
    br = BrowseRule("Images\Album", "", "")
    assert br.get_names() == ['Images', 'Album']
    assert br.get_categories() == []
    assert not br.search
    br = BrowseRule("", "Images\Album", "")
    assert br.get_names() == []
    assert br.get_categories() == ['Images', 'Album']
    assert not br.search
    br = BrowseRule("", "Images\Album", "[go]")
    assert br.get_names() == []
    assert br.get_categories() == ['Images', 'Album']
    assert br.search == '[go]'

    assert sorted(expected) == [
        BrowseRule("Audio\Genre", "Genre\Album Artist (auto)\Album", ""),
        BrowseRule("Audio\Highly Rated", "", "[Rating]=>=4"),
        BrowseRule("Images\Album", "Album", ""),
    ]


def test_mediaserverinfo_eq():
    ms1 = MediaServerInfo({
        'ProgramVersion': '31.0.87',
        'FriendlyName': 'localhost',
        'Platform': 'Windows'
    })
    ms2 = MediaServerInfo({
        'ProgramVersion': '31.0.87',
        'FriendlyName': 'localhost',
        'Platform': 'Windows'
    })
    ms3 = MediaServerInfo({
        'ProgramVersion': '31.0.88',
        'FriendlyName': 'localhost',
        'Platform': 'Windows'
    })
    ms4 = MediaServerInfo({
        'ProgramVersion': '31.0.87',
        'FriendlyName': 'otherhost',
        'Platform': 'Windows'
    })
    ms5 = MediaServerInfo({
        'ProgramVersion': '31.0.87',
        'FriendlyName': 'localhost',
        'Platform': 'Linux'
    })
    ms_apd = [MediaServerInfo({
        'ProgramVersion': f'33.0.{v}',
        'FriendlyName': 'localhost',
        'Platform': 'Linux'
    }) for v in range(32,45)]

    assert ms1 != None
    assert ms1 == ms2
    assert ms1 != ms3
    assert ms1 != ms4
    assert ms1 == ms5
    assert str(ms1) == 'localhost [31.0.87]'
    assert not ms1.supports_audio_path_direct
    assert not ms_apd[0].supports_audio_path_direct
    for ms in ms_apd[1:]:
        assert ms.supports_audio_path_direct


def test_media_type():
    assert MediaType(MediaType.VIDEO) == MediaType.VIDEO
    assert 'Video' == MediaType.VIDEO
    assert MediaType('Video') == MediaType.VIDEO


def test_key_command():
    command_names = [e.name for e in KeyCommand]
    assert 'PAGE_DOWN' in command_names


def test_view_mode():
    assert ViewMode.STANDARD > ViewMode.NO_UI
    assert ViewMode.NO_UI < ViewMode.STANDARD


@pytest.fixture
async def many_browse_rules_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="Images\Album" Categories="Album" Search=""/>
<Item Name="Audio\Genre" Categories="Genre\Album Artist (auto)\Album" Search=""/>
<Item Name="Audio\Highly Rated" Categories="" Search="[Rating]=&gt;=4"/>
<Item Name="Audio\Recent" Categories="Album" Search="~sort="/>
<Item Name="Audio\Highly Rated\Recent Albums" Categories="Album" Search=""/>
<Item Name="Images\Highly Rated" Categories="" Search="[Rating]=&gt;=4"/>
<Item Name="Video\Recent" Categories="" Search="~sort=[Date Imported]-d ~n=250"/>
<Item Name="Images" Categories="" Search="[Media Type]=[Image]"/>
<Item Name="Audio\Artist" Categories="Album Artist (auto)\Album" Search=""/>
<Item Name="Images\Keyword" Categories="Keywords" Search=""/>
<Item Name="Video\Movies" Categories="" Search="[Media Sub Type]=[Movie] ~sort=[Name]"/>
<Item Name="Audiobooks\Books" Categories="Album" Search=""/>
<Item Name="Audiobooks\Authors" Categories="Artist\Album" Search=""/>
<Item Name="Video\Shows" Categories="Series\Season" Search="[Media Sub Type]=[TV Show] -[Episode]=[] -[Genre]=&quot;Family&quot; ~sort=[Series],[Season],[Episode]"/>
<Item Name="Video" Categories="" Search="[Media Type]=[Video]"/>
<Item Name="Audio" Categories="" Search="[Media Type]=[Audio]"/>
<Item Name="Video\Music" Categories="Artist\Album" Search="[Media Type]=[Video] [Media Sub Type]=[Music]"/>
<Item Name="Images\Disk" Categories="Location" Search=""/>
<Item Name="Video\Home Videos" Categories="Year" Search="[Media Sub Type]=[Home Video] ~sort=[Date Imported]-d"/>
<Item Name="Video\Disk" Categories="Location" Search=""/>
<Item Name="Radio" Categories="Publisher" Search="[Media Sub Type]=[Radio] ~sort=[Publisher],[Name]"/>
<Item Name="Audiobooks" Categories="" Search="[Media Type]=[Audio] [Genre]=[Audiobook]"/>
<Item Name="Audio\Podcast" Categories="" Search="[Media Sub Type]=[Podcast] ~sort=[Date]-d"/>
<Item Name="Images\Camera" Categories="Camera" Search=""/>
<Item Name="Video\Movies - Unwatched" Categories="Who\Length" Search="[Media Sub Type]=[Movie] [=Or(Compare([Last played,0],=,0),Compare([Rewatch],=,1))]=1 ~sort=[Who],[Duration]"/>
<Item Name="Video\Other" Categories="" Search="-[Media Sub Type]=[Home Video],[Movie],[TV Show]"/>
<Item Name="Images\Year" Categories="Year\Album" Search=""/>
<Item Name="Audio\Composer" Categories="Composer\Album" Search=""/>
<Item Name="Audio\Album" Categories="Album" Search=""/>
</Response>''')
    ms = await make_ms('Browse/Rules', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_parse_browse_rules(many_browse_rules_stub):
    rules = await many_browse_rules_stub.get_browse_rules()
    assert len(rules) == 29
    paths = convert_browse_rules(rules)
    assert len(paths) == 5
    for path in paths:
        assert path.name in ['Audio', 'Images', 'Video', 'Audiobooks', 'Radio', 'TV Show']
        if path.name == 'Audio':
            assert path.effective_media_types == [MediaType.AUDIO]
            assert not path.effective_media_sub_types
            assert len(path.children) == 7
            for c in path.children:
                assert not c.is_field
                assert c.parent == path

            assert path.children[0].name == 'Album'
            assert len(path.children[0].children) == 1
            assert path.children[0].children[0].name == 'Album'
            assert path.children[0].children[0].is_field
            assert path.children[0].children[0].effective_media_types == [MediaType.AUDIO]
            assert path.children[0].children[0].effective_media_sub_types == [MediaSubType.MUSIC]

            assert path.children[1].name == 'Artist'
            assert len(path.children[1].children) == 1
            assert path.children[1].children[0].name == 'Album Artist (auto)'
            assert path.children[1].children[0].is_field
            assert path.children[1].children[0].effective_media_types == [MediaType.AUDIO]
            assert path.children[1].children[0].effective_media_sub_types == [MediaSubType.MUSIC]
            assert len(path.children[1].children[0].children) == 1
            assert path.children[1].children[0].children[0].name == 'Album'
            assert path.children[1].children[0].children[0].is_field
            assert path.children[1].children[0].children[0].effective_media_types == [MediaType.AUDIO]
            assert path.children[1].children[0].children[0].effective_media_sub_types == [MediaSubType.MUSIC]
            assert not path.children[1].children[0].children[0].children

            assert path.children[2].name == 'Composer'
            assert path.children[3].name == 'Genre'

            assert path.children[4].name == 'Highly Rated'
            assert len(path.children[4].children) == 1
            assert path.children[4].children[0].name == 'Recent Albums'
            assert not path.children[4].children[0].is_field
            assert path.children[4].children[0].effective_media_types == [MediaType.AUDIO]
            assert not path.children[4].children[0].effective_media_sub_types
            assert path.children[4].children[0].children
            assert len(path.children[4].children[0].children) == 1
            assert path.children[4].children[0].children[0].name == 'Album'
            assert path.children[4].children[0].children[0].is_field
            assert path.children[4].children[0].children[0].effective_media_types == [MediaType.AUDIO]
            assert path.children[4].children[0].children[0].effective_media_sub_types == [MediaSubType.MUSIC]
            assert not path.children[4].children[0].children[0].children

            assert path.children[5].name == 'Podcast'
            assert path.children[6].name == 'Recent'

        elif path.name == 'Video':
            assert len(path.children) == 8
        elif path.name == 'Audiobooks':
            assert len(path.children) == 2
        elif path.name == 'Radio':
            assert len(path.children) == 1
        elif path.name == 'Images':
            assert len(path.children) == 6

    paths = [x.full_path for x in convert_browse_rules(rules, flat=True)]
    assert paths == [
        'Audio',
        'Audio/Album',
        'Audio/Artist',
        'Audio/Composer',
        'Audio/Genre',
        'Audio/Highly Rated',
        'Audio/Highly Rated/Recent Albums',
        'Audio/Podcast',
        'Audio/Recent',
        'Audiobooks',
        'Audiobooks/Authors',
        'Audiobooks/Books',
        'Images',
        'Images/Album',
        'Images/Camera',
        'Images/Disk',
        'Images/Highly Rated',
        'Images/Keyword',
        'Images/Year',
        'Radio',
        'Video',
        'Video/Disk',
        'Video/Home Videos',
        'Video/Movies',
        'Video/Movies - Unwatched',
        'Video/Music',
        'Video/Other',
        'Video/Recent',
        'Video/Shows'
    ]


def test_parse_browse_rules_from_text():
    input_rules = [
        "Images",
        "Radio,Channels",
        "Video,Shows|Series,Season",
        "Video,Movies",
        "Video,Music|Artist,Album",
    ]
    paths = parse_browse_paths_from_text(input_rules)
    assert paths
    assert len(paths) == 3

    def _require(n: str):
        return next(p for p in paths if p.name == n)

    images = _require('Images')
    assert not images.parent
    assert not images.children
    assert images.effective_media_types == [MediaType.IMAGE]
    assert not images.effective_media_sub_types

    radio = _require('Radio')
    assert not radio.parent
    assert len(radio.children) == 1
    assert radio.children[0].name == 'Channels'
    assert not radio.children[0].children
    assert radio.children[0].parent == radio
    assert not radio.effective_media_types
    assert not radio.effective_media_sub_types

    video = _require('Video')
    assert not video.parent
    assert video.effective_media_types == [MediaType.VIDEO]
    assert not video.effective_media_sub_types
    assert len(video.children) == 3

    assert video.children[0].name == 'Movies'
    assert video.children[0].effective_media_types == [MediaType.VIDEO]
    assert video.children[0].effective_media_sub_types == [MediaSubType.MOVIE]
    assert not video.children[0].children
    assert video.children[0].parent == video

    assert video.children[1].name == 'Music'
    assert video.children[1].parent == video
    assert video.children[1].effective_media_types == [MediaType.VIDEO]
    assert video.children[1].effective_media_sub_types == [MediaSubType.MUSIC_VIDEO]

    assert video.children[1].children[0].name == 'Artist'
    assert video.children[1].children[0].is_field
    assert video.children[1].children[0].parent == video.children[1]
    assert video.children[1].children[0].children[0].name == 'Album'
    assert video.children[1].children[0].children[0].parent == video.children[1].children[0]
    assert video.children[1].children[0].children[0].is_field
    assert video.children[1].children[0].children[0].effective_media_types == [MediaType.VIDEO]
    assert video.children[1].children[0].children[0].effective_media_sub_types == [MediaSubType.MUSIC_VIDEO]

    assert video.children[2].name == 'Shows'
    assert video.children[2].parent == video
    assert video.children[2].effective_media_types == [MediaType.VIDEO]
    assert video.children[2].effective_media_sub_types == [MediaSubType.TV_SHOW]

    assert video.children[2].children[0].name == 'Series'
    assert video.children[2].children[0].is_field
    assert video.children[2].children[0].parent == video.children[2]
    assert video.children[2].children[0].effective_media_types == [MediaType.VIDEO]
    assert video.children[2].children[0].effective_media_sub_types == [MediaSubType.TV_SHOW]
    assert video.children[2].children[0].children[0].name == 'Season'
    assert video.children[2].children[0].children[0].parent == video.children[2].children[0]
    assert video.children[2].children[0].children[0].is_field
    assert video.children[2].children[0].children[0].effective_media_types == [MediaType.VIDEO]
    assert video.children[2].children[0].children[0].effective_media_sub_types == [MediaSubType.TV_SHOW]


def test_search_for_path():
    input_rules = [
        "Images",
        "Radio,Channels",
        "Video,Shows|Series,Season",
        "Video,Movies",
        "Video,Music|Artist,Album",
        "Audiobooks,Books|Album",
        "Audiobooks,Authors|Artist,Album"
    ]
    paths = parse_browse_paths_from_text(input_rules)

    result = search_for_path(paths, ['Images'])
    assert result.full_path == 'Images'

    result = search_for_path(paths, ['My', 'Images'])
    assert not result

    result = search_for_path(paths, ['Radio', 'Channels'])
    assert result.full_path == 'Radio/Channels'

    result = search_for_path(paths, ['Radio', 'Stations'])
    assert not result

    result = search_for_path(paths, ['Video'])
    assert result.full_path == 'Video'

    result = search_for_path(paths, ['Video', 'Shows'])
    assert result.full_path == 'Video/Shows'

    result = search_for_path(paths, ['Video', 'Shows', 'The Wire'])
    assert result.full_path == 'Video/Shows/Series'

    result = search_for_path(paths, ['Video', 'Shows', 'The Wire', '2'])
    assert result.full_path == 'Video/Shows/Series/Season'

    result = search_for_path(paths, ['Video', 'Shows', 'Series', 'Season', 'Episodes'])
    assert not result

    result = search_for_path(paths, ['Audiobooks'])
    assert result.full_path == 'Audiobooks'

    result = search_for_path(paths, ['Audiobooks', 'Books'])
    assert result.full_path == 'Audiobooks/Books'

    result = search_for_path(paths, ['Audiobooks', 'Books', 'My Book'])
    assert result.full_path == 'Audiobooks/Books/Album'

    result = search_for_path(paths, ['Audiobooks', 'Authors'])
    assert result.full_path == 'Audiobooks/Authors'

    result = search_for_path(paths, ['Audiobooks', 'Authors', 'Me'])
    assert result.full_path == 'Audiobooks/Authors/Artist'


@pytest.fixture
async def ap_direct_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="AudioPath">No changes are being made</Item>
<Item Name="Direct">yes</Item>
<Item Name="AudioPath0">No changes are being made</Item>
</Response>''')
    ms = await make_ms('Playback/AudioPath', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_audio_path_direct(ap_direct_stub: MediaServer):
    resp = await ap_direct_stub.get_audio_path()
    assert resp
    assert isinstance(resp, AudioPath)
    assert resp.is_direct is True
    assert resp.paths == ['No changes are being made']


@pytest.fixture
async def is_direct_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="Direct">yes</Item>
</Response>''')
    ms = await make_ms('Playback/AudioPathDirect', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_is_direct(is_direct_stub: MediaServer):
    resp = await is_direct_stub.get_audio_path_direct()
    assert resp
    assert isinstance(resp, AudioPath)
    assert resp.is_direct is True
    assert not resp.paths


@pytest.fixture
async def ap_dsp_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('''<Response Status="OK">
<Item Name="AudioPath">Convert from 2 channels to 2 channels (in 6 channel container);--------------;Copy Left to U1;Add Right to U1;Add Centre to U1;Add SL to U1;Add SR to U1;Low-pass at 120 Hz (U1);Low-pass at 120 Hz (U1);Low-pass at 120 Hz (U1);Low-pass at 120 Hz (U1);--------------;Copy Sub to U2;High-pass at 120 Hz (U2);High-pass at 120 Hz (U2);High-pass at 120 Hz (U2);High-pass at 120 Hz (U2);Low-pass at 120 Hz (Sub);Low-pass at 120 Hz (Sub);Low-pass at 120 Hz (Sub);Low-pass at 120 Hz (Sub);Add U2 to Sub;Add U1 to Sub;--------------;High-pass at 120 Hz (Left,Right,Centre,SL,SR);High-pass at 120 Hz (Left,Right,Centre,SL,SR);High-pass at 120 Hz (Left,Right,Centre,SL,SR);High-pass at 120 Hz (Left,Right,Centre,SL,SR)</Item>
<Item Name="Direct">no</Item>
<Item Name="AudioPath0">Convert from 2 channels to 2 channels (in 6 channel container)</Item>
<Item Name="AudioPath1">--------------</Item>
<Item Name="AudioPath2">Copy Left to U1</Item>
<Item Name="AudioPath3">Add Right to U1</Item>
<Item Name="AudioPath4">Add Centre to U1</Item>
<Item Name="AudioPath5">Add SL to U1</Item>
<Item Name="AudioPath6">Add SR to U1</Item>
</Response>''')
    ms = await make_ms('Playback/AudioPath', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_audio_path_dsp(ap_dsp_stub: MediaServer):
    resp = await ap_dsp_stub.get_audio_path()
    assert resp
    assert isinstance(resp, AudioPath)
    assert resp.is_direct is False
    assert resp.paths == [
        'Convert from 2 channels to 2 channels (in 6 channel container)',
        '--------------',
        'Copy Left to U1',
        'Add Right to U1',
        'Add Centre to U1',
        'Add SL to U1',
        'Add SR to U1'
    ]


@pytest.fixture
async def playlist_stub(aiohttp_server) -> MediaServer:
    handler = make_handler('[{"Key": 1866769,"Filename":"Z:/JPEGMAFIA_x_Danny_Brown/SCARING_THE_HOES/01-Lean_Beef_Patty.flac","Name": "Lean Beef Patty","Artist": "JPEGMAFIA x Danny Brown","Album": "SCARING THE HOES","Genre": "Hip-Hop","Comment": "Visit https://jpegmafia.bandcamp.com","Date (readable)": "2023","Date": 44927,"Bitrate": 1752,"Image File": "INTERNAL","Duration": 107.586666699999995,"Track #": 1,"Media Type": "Audio","Album Artist": "JPEGMAFIA x Danny Brown","Bookmark": "92879","Date Imported": 1719697095,"Last Played": 1728975965,"Number Plays": 3,"File Type": "flac","File Size": 23891407,"Date Created": 1719696278,"Date Modified": 1720102351,"Compression": "FLAC","Peak Level (R128)": "+0.0 dBTP;+0.0 Left;-0.2 Right","Peak Level (Sample)": "-0.5 dB;-0.5 Left;-0.5 Right","BPM": 62,"Volume Level (R128)": -17.969289779663086,"Volume Level (ReplayGain)": -12.969289779663086,"Dynamic Range (R128)": 5.8563899993896484,"Dynamic Range (DR)": 2,"Sample Rate": 44100,"Channels": 2,"Bit Depth": 24,"Length In PCM Blocks": 4744572,"Total Tracks": 14,"Total Discs": 1,"Date Tagged": 1719697138,"Date Last Opened": 1728975960,"HDCD": "0","Zone Last Opened": "Player","Audio CRC": "0x7DCC0E83","Last Played (album)": 1728975965},{"Key": 1866770,"Filename": "Z:/JPEGMAFIA_x_Danny_Brown/SCARING_THE_HOES/02-Steppa_Pig.flac","Name": "Steppa Pig","Artist": "JPEGMAFIA x Danny Brown","Album": "SCARING THE HOES","Genre": "Hip-Hop","Comment": "Visit https://jpegmafia.bandcamp.com","Date (readable)": "2023","Date": 44927,"Bitrate": 1773,"Image File": "INTERNAL","Duration": 207.878775499999989,"Track #": 2,"Media Type": "Audio","Album Artist": "JPEGMAFIA x Danny Brown","Date Imported": 1719697095,"Last Played": 1728975576,"Number Plays": 2,"File Type": "flac","File Size": 46404155,"Date Created": 1719696279,"Date Modified": 1720102351,"Compression": "FLAC","Peak Level (R128)": "+0.3 dBTP;+0.3 Left;+0.0 Right","Peak Level (Sample)": "-0.5 dB;-0.5 Left;-0.5 Right","BPM": 98,"Volume Level (R128)": -18.7555007934570312,"Volume Level (ReplayGain)": -13.7554998397827148,"Dynamic Range (R128)": 3.8003299236297607,"Dynamic Range (DR)": 2,"Sample Rate": 44100,"Channels": 2,"Bit Depth": 24,"Length In PCM Blocks": 9167454,"Total Tracks": 14,"Date Tagged": 1719697147,"Date Last Opened": 1728975567,"HDCD": "0","Zone Last Opened": "Player","Audio CRC": "0xC0ED4149","Last Played (album)": 1728975965}]',
                           ctype='application/json')
    ms = await make_ms('Playback/Playlist', aiohttp_server, handler)
    yield ms
    await ms.close()


@pytest.mark.asyncio
async def test_current_playlist(playlist_stub: MediaServer):
    resp = await playlist_stub.get_current_playlist()
    assert resp
    assert len(resp) == 2
    assert isinstance(resp[0], dict)
    assert 'ImageURL' in resp[0]
    assert isinstance(resp[1], dict)
    assert 'ImageURL' in resp[1]

