from inkpulse_hub.collectors.market import parse_tencent, parse_okx, is_stale, REFRESH_S

# 一行腾讯返回(已 GBK 解码的字符串形态)
TENCENT_LINE = ('v_sh000001="1~上证指数~000001~4031.51~3987.01~4017.86~743131092'
                + "~0" * 24 + '~44.50~1.12' + "~x" * 53 + '";')


def test_parse_tencent_basic():
    q = parse_tencent(TENCENT_LINE)
    assert q["type"] == "cn" and q["code"] == "sh000001"
    assert q["name"] == "上证指数" and q["price"] == 4031.51 and q["change_pct"] == 1.12


def test_parse_tencent_malformed_returns_none():
    assert parse_tencent('v_x="1~只有~几个~字段";') is None
    assert parse_tencent("garbage no equals") is None


def test_parse_okx_basic():
    obj = {"data": [{"last": "64544.6", "open24h": "63879.2"}]}
    q = parse_okx(obj, "BTC-USDT")
    assert q["type"] == "crypto" and q["code"] == "BTC-USDT" and q["name"] == "BTC"
    assert q["price"] == 64544.6
    assert abs(q["change_pct"] - (64544.6 - 63879.2) / 63879.2 * 100) < 1e-6


def test_parse_okx_malformed_returns_none():
    assert parse_okx({"data": []}, "BTC-USDT") is None
    assert parse_okx({}, "BTC-USDT") is None
    assert parse_okx({"data": [{"last": "1", "open24h": "0"}]}, "X") is None   # 除零


def test_is_stale_boundary():
    assert is_stale(1000.0, 1000.0 + REFRESH_S) is True
    assert is_stale(1000.0, 1000.0 + REFRESH_S - 1) is False
