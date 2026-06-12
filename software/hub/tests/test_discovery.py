import socket
from inkpulse_hub.discovery import build_service_info


def test_service_info_type_port_name_address():
    info = build_service_info(port=8080, host_ip="192.168.10.64")
    # 设备端按服务类型 _inkpulse._tcp 做 mDNS PTR 发现
    assert info.type == "_inkpulse._tcp.local."
    assert info.port == 8080
    # 实例名可读, 含 inkpulse
    assert "inkpulse" in info.name.lower()
    # 广播本机局域网 IP, 设备据此拼 hub base URL
    assert socket.inet_aton("192.168.10.64") in info.addresses


def test_service_info_autodetect_ip_when_none():
    # 不传 host_ip 时自动探测本机 IP, 至少要有一个非空地址
    info = build_service_info(port=9000, host_ip=None)
    assert info.port == 9000
    assert len(info.addresses) >= 1
    assert len(info.addresses[0]) == 4  # IPv4 packed


def test_pick_lan_ip_prefers_private_lan_over_vpn():
    from inkpulse_hub.discovery import _pick_lan_ip
    # VPN/CGNAT 网段应被排除: 198.18.x(clash-tun benchmark), 100.x(tailscale CGNAT)
    assert _pick_lan_ip(["198.18.0.1", "192.168.10.64", "127.0.0.1"]) == "192.168.10.64"
    assert _pick_lan_ip(["100.64.0.1", "10.1.1.1"]) == "10.1.1.1"
    # 多个合法私有地址时, 192.168 优先于 10/172
    assert _pick_lan_ip(["10.0.0.5", "192.168.1.2"]) == "192.168.1.2"
    # 全是被排除网段时不崩, 返回一个候选兜底
    assert _pick_lan_ip(["169.254.1.1"]) == "169.254.1.1"


def test_register_mdns_is_discoverable_then_unregistered():
    import time
    from zeroconf import Zeroconf, ServiceBrowser
    from inkpulse_hub.discovery import register_mdns, SERVICE_TYPE

    handle = register_mdns(port=8080)
    browser_zc = Zeroconf()
    events = {"added": set(), "removed": set()}

    class _L:
        def add_service(self, zc, type_, name): events["added"].add(name)
        def update_service(self, zc, type_, name): pass
        def remove_service(self, zc, type_, name): events["removed"].add(name)

    try:
        ServiceBrowser(browser_zc, SERVICE_TYPE, _L())
        # 注册后应被发现
        deadline = time.time() + 5
        while time.time() < deadline and not events["added"]:
            time.sleep(0.1)
        assert any("inkpulse" in n.lower() for n in events["added"]), \
            f"未发现已注册服务: {events['added']}"
        # 注销后应收到移除
        handle.close()
        deadline = time.time() + 5
        while time.time() < deadline and not events["removed"]:
            time.sleep(0.1)
        assert events["removed"], "注销后未收到 remove 事件"
    finally:
        browser_zc.close()
        handle.close()
