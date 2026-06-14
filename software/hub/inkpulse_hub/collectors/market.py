# inkpulse_hub/collectors/market.py
REFRESH_S = 300   # 行情缓存 5 分钟过期


def is_stale(fetched_at, now) -> bool:
    return (now - fetched_at) >= REFRESH_S


def parse_tencent(line: str):
    """入参: 一行已 GBK 解码的腾讯返回 v_<code>="1~名称~..~现价~..~涨跌幅~..";
    返回归一 quote 或 None(格式异常)。字段: [1]=名称, [3]=现价, [32]=涨跌幅%。"""
    try:
        head, body = line.split("=", 1)
        code = head.strip()
        if code.startswith("v_"):
            code = code[2:]
        body = body.strip().rstrip(";").strip('"')
        f = body.split("~")
        if len(f) < 33:
            return None
        return {"type": "cn", "code": code, "name": f[1],
                "price": float(f[3]), "change_pct": float(f[32])}
    except (ValueError, IndexError):
        return None


def parse_okx(obj: dict, code: str):
    """入参: OKX ticker JSON + 标的代码。返回归一 quote 或 None。"""
    try:
        d = obj["data"][0]
        last = float(d["last"])
        open24h = float(d["open24h"])
        if open24h == 0:
            return None
        return {"type": "crypto", "code": code, "name": code.split("-")[0],
                "price": last, "change_pct": (last - open24h) / open24h * 100}
    except (KeyError, IndexError, ValueError, TypeError):
        return None
