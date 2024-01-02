from hamcws import MediaServerInfo


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
