from inkpulse_hub.collectors.market import MarketService, REFRESH_S

NOW = 1749880000.0
SYMS = [{"type": "cn", "code": "sh000001"}, {"type": "crypto", "code": "BTC-USDT"}]


def _fake_cn(codes):
    return [{"type": "cn", "code": c, "name": c, "price": 1.0, "change_pct": 1.0} for c in codes]


def _fake_crypto(code):
    return {"type": "crypto", "code": code, "name": code.split("-")[0], "price": 2.0, "change_pct": -1.0}


def _svc(tmp_path):
    return MarketService(str(tmp_path / "m.json"))


def test_current_empty_when_no_cache(tmp_path):
    assert _svc(tmp_path).current() == []


def test_refresh_now_writes_and_current_reads(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=_fake_crypto)
    q = s.current()
    assert [x["code"] for x in q] == ["sh000001", "BTC-USDT"]   # 保持 symbols 顺序


def test_needs_refresh_logic(tmp_path):
    s = _svc(tmp_path)
    assert s._needs_refresh(SYMS, NOW) is True                          # 无缓存
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=_fake_crypto)
    assert s._needs_refresh(SYMS, NOW + 10) is False                    # 新鲜
    assert s._needs_refresh(SYMS, NOW + REFRESH_S + 1) is True          # 过期
    assert s._needs_refresh(SYMS + [{"type": "cn", "code": "sz000002"}], NOW + 10) is True  # 标的变更


def test_single_symbol_failure_skipped(tmp_path):
    s = _svc(tmp_path)
    def boom_crypto(code):
        raise RuntimeError("okx down")
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=boom_crypto)
    assert [x["code"] for x in s.current()] == ["sh000001"]   # 加密失败跳过, A股仍在


def test_total_failure_keeps_old_cache(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=_fake_crypto)
    def boom_cn(codes):
        raise RuntimeError("tencent down")
    def boom_crypto(code):
        raise RuntimeError("okx down")
    s.refresh_now(SYMS, NOW + 5, fetch_cn=boom_cn, fetch_crypto=boom_crypto)
    assert len(s.current()) == 2   # 旧缓存保留(没被空覆盖)


def test_clear(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=_fake_crypto)
    s.clear()
    assert s.current() == []


def test_maybe_refresh_noop_when_fresh(tmp_path):
    s = _svc(tmp_path)
    s.refresh_now(SYMS, NOW, fetch_cn=_fake_cn, fetch_crypto=_fake_crypto)
    def boom(*a):
        raise AssertionError("不应刷新")
    s.maybe_refresh(SYMS, NOW + 10, fetch_cn=boom, fetch_crypto=boom)
    assert len(s.current()) == 2
