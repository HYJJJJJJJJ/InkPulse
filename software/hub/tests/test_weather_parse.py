from inkpulse_hub.collectors.weather import parse_weather, is_stale, WMO_CN, REFRESH_S

SAMPLE_RAW = {
    "current": {"time": "2026-06-14T10:00", "temperature_2m": 23.4, "weather_code": 2},
    "daily": {"time": ["2026-06-14", "2026-06-15", "2026-06-16", "2026-06-17"],
              "weather_code": [2, 0, 3, 61],
              "temperature_2m_max": [26.0, 27.0, 24.0, 22.0],
              "temperature_2m_min": [18.0, 19.0, 17.0, 16.0]}
}
# 2026-06-14 是周日; 故 06-15=明(周一), 06-16=周二, 06-17=周三
NOW = __import__("time").mktime((2026, 6, 14, 10, 0, 0, 0, 0, -1))


def test_parse_current_and_today():
    w = parse_weather(SAMPLE_RAW, NOW)
    assert w["cur_temp"] == 23.4 and w["cur_code"] == 2
    assert w["cur_cn"] == "多云" and w["cur_cat"] == "partly"
    assert w["today_hi"] == 26.0 and w["today_lo"] == 18.0


def test_parse_three_day_forecast():
    days = parse_weather(SAMPLE_RAW, NOW)["days"]
    assert len(days) == 3
    assert days[0] == {"label": "明", "cn": "晴", "cat": "sun", "hi": 27.0, "lo": 19.0}
    assert days[1]["label"] == "周二" and days[1]["cn"] == "阴" and days[1]["cat"] == "cloud"
    assert days[2]["label"] == "周三" and days[2]["cn"] == "小雨" and days[2]["cat"] == "rain"


def test_wmo_categories():
    assert WMO_CN[0] == ("晴", "sun")
    assert WMO_CN[45] == ("雾", "fog")
    assert WMO_CN[71] == ("小雪", "snow")
    assert WMO_CN[80] == ("阵雨", "rain")
    assert WMO_CN[95] == ("雷阵雨", "thunder")


def test_parse_unknown_code_falls_back():
    raw = {"current": {"temperature_2m": 10.0, "weather_code": 7},
           "daily": {"time": ["2026-06-14"], "weather_code": [7],
                     "temperature_2m_max": [11.0], "temperature_2m_min": [9.0]}}
    w = parse_weather(raw, NOW)
    assert w["cur_cn"] == "未知" and w["cur_cat"] == "cloud"
    assert w["days"] == []          # 无未来日


def test_is_stale_boundary():
    assert is_stale(1000.0, 1000.0 + REFRESH_S) is True       # 刚好到期
    assert is_stale(1000.0, 1000.0 + REFRESH_S - 1) is False  # 之内
    assert is_stale(1000.0, 1000.0 + REFRESH_S + 1) is True   # 之外
