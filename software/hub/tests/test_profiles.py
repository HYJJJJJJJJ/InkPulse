from inkpulse_hub.render.profiles import get_profile, PROFILES, DEFAULT_PROFILE


def test_known_profiles_exist():
    assert set(PROFILES) >= {"bwr_750", "bw_426"}


def test_bwr_750_shape():
    p = PROFILES["bwr_750"]
    assert (p.w, p.h, p.color, p.rotate) == (800, 480, "bwr", 0)
    assert (p.cols, p.rows, p.frame_bytes) == (8, 6, 96000)


def test_bw_426_shape():
    p = PROFILES["bw_426"]
    assert (p.w, p.h, p.color, p.rotate) == (480, 800, "bw", 90)
    assert (p.cols, p.rows, p.frame_bytes) == (4, 8, 48000)


def test_unknown_panel_falls_back_to_default():
    assert get_profile("nope") is DEFAULT_PROFILE
    assert get_profile(None) is DEFAULT_PROFILE
    assert DEFAULT_PROFILE.id == "bwr_750"


def test_known_panel_resolves():
    assert get_profile("bw_426").id == "bw_426"
