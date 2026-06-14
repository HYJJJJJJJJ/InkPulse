import inkpulse_hub.collectors.market as M

TENCENT_LINE = ('v_sh000001="1~上证指数~000001~4031.51~3987.01~4017.86~743131092'
                + "~0" * 24 + '~44.50~1.12' + "~x" * 53 + '";')


def test_fetch_cn_batch_parses(monkeypatch):
    captured = {}
    def fake(url):
        captured["url"] = url
        return (TENCENT_LINE + "\n" + 'v_bad="1~少~字段";').encode("gbk")
    monkeypatch.setattr(M, "_get_bytes", fake)
    out = M.fetch_cn(["sh000001", "bad"])
    assert "q=sh000001,bad" in captured["url"]
    assert [q["code"] for q in out] == ["sh000001"]     # 坏行被跳过


def test_fetch_cn_empty_codes(monkeypatch):
    monkeypatch.setattr(M, "_get_bytes", lambda url: (_ for _ in ()).throw(AssertionError("不应请求")))
    assert M.fetch_cn([]) == []


def test_fetch_crypto_parses(monkeypatch):
    import json
    monkeypatch.setattr(M, "_get_bytes",
        lambda url: json.dumps({"data": [{"last": "1672.7", "open24h": "1674.46"}]}).encode("utf-8"))
    q = M.fetch_crypto("ETH-USDT")
    assert q["type"] == "crypto" and q["name"] == "ETH" and q["price"] == 1672.7
