from media.manager import MediaManager


def test_media_search_opens_the_selected_search_provider():
    opened = []
    manager = MediaManager(opener=lambda url: opened.append(url) or True)

    assert manager.search("música clássica", kind="music")
    assert "music.youtube.com/search" in opened[0]
    assert "%C3%A1" in opened[0]

    assert manager.search("python tutorial", kind="video")
    assert "youtube.com/results" in opened[1]


def test_media_controls_send_mapped_windows_virtual_keys():
    pressed = []
    manager = MediaManager(key_sender=pressed.append)

    manager.control("play_pause")
    manager.control("next")
    manager.control("previous")
    manager.control("volume_up")
    manager.control("volume_down")

    assert pressed == [0xB3, 0xB0, 0xB1, 0xAF, 0xAE]