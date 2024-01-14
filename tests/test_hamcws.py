import datetime

import pytest
from aiohttp import web
from aiohttp.web_response import Response

from hamcws import get_mcws_connection, MediaServer, MediaServerInfo, MediaType, KeyCommand, ViewMode, ServerAddress, \
    resolve_access_key


def make_handler(text: str):
    async def handler(request: web.Request) -> web.Response:
        return Response(
            text=text,
            content_type='text/xml',
            charset='utf-8'
        )
    return handler


async def make_ms(func: str, aiohttp_server, handler):
    app = web.Application()
    app.add_routes([web.get(f"/MCWS/v1/{func}", handler)])
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
    resp = await alive_stub.alive()
    assert resp
    assert resp.name == 'MyServer'
    assert resp.version == '31.0.83'
    assert resp.platform == 'Linux'
    assert resp.updated_at > start


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

    assert ms1 != None
    assert ms1 == ms2
    assert ms1 != ms3
    assert ms1 != ms4
    assert ms1 == ms5


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
