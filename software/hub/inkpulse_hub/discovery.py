# mDNS 服务注册: 让设备开机自动发现 hub, 无需写死 IP。
# 设备端按服务类型 _inkpulse._tcp 做 PTR 发现, 取 IP+端口拼 hub base URL。
import os
import socket
import subprocess
from zeroconf import ServiceInfo, Zeroconf

SERVICE_TYPE = "_inkpulse._tcp.local."
INSTANCE = "inkpulse-hub"


def _ip_rank(ip: str) -> int:
    """IP 优先级: 越小越优先; >=90 表示排除(VPN/CGNAT/回环/链路本地)。"""
    if ip.startswith("192.168."):
        return 0
    if ip.startswith("172."):
        try:
            if 16 <= int(ip.split(".")[1]) <= 31:
                return 1
        except (IndexError, ValueError):
            pass
    if ip.startswith("10."):
        return 2
    # 排除: 回环 / 链路本地 / tailscale CGNAT(100.64-127) / clash-tun benchmark(198.18-19)
    if ip.startswith(("127.", "169.254.", "100.", "198.18.", "198.19.")):
        return 90
    return 50  # 其他(公网等), 不排除但低于私有局域网


def _pick_lan_ip(candidates) -> str:
    """从候选 IP 里挑设备最可能能访问的局域网地址。"""
    cands = [c for c in candidates if c]
    if not cands:
        return "127.0.0.1"
    best = sorted(cands, key=_ip_rank)[0]
    if _ip_rank(best) >= 90:
        return cands[0]   # 全是被排除网段, 兜底返回第一个, 不崩
    return best


def _candidate_ips():
    ips = []
    # 枚举所有接口 IPv4(覆盖 VPN/镜像网卡共存: connect 出口可能是 VPN 网段)
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show"],
                             capture_output=True, text=True, timeout=2).stdout
        for line in out.splitlines():
            parts = line.split()
            if "inet" in parts:
                ip = parts[parts.index("inet") + 1].split("/")[0]
                if ip not in ips:
                    ips.append(ip)
    except Exception:
        pass
    # 默认路由出口(ip 命令不可用时的兜底)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # 只设路由, 不真正发包
        if s.getsockname()[0] not in ips:
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    finally:
        s.close()
    return ips


def _detect_ip() -> str:
    """选本机局域网 IP。INKPULSE_HOST_IP 可显式覆盖(多网卡/VPN 环境兜底)。"""
    env = os.environ.get("INKPULSE_HOST_IP")
    if env:
        return env
    return _pick_lan_ip(_candidate_ips())


def build_service_info(port: int, host_ip: str | None = None) -> ServiceInfo:
    ip = host_ip or _detect_ip()
    return ServiceInfo(
        type_=SERVICE_TYPE,
        name=f"{INSTANCE}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={"path": "/frame"},
    )


class MdnsRegistration:
    """mDNS 注册句柄, close() 注销并释放(幂等)。"""

    def __init__(self, zc: Zeroconf, info: ServiceInfo):
        self._zc = zc
        self._info = info
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._zc.unregister_service(self._info)
        finally:
            self._zc.close()


def register_mdns(port: int, host_ip: str | None = None) -> MdnsRegistration:
    """注册 _inkpulse._tcp 服务, 让设备开机自动发现 hub。"""
    info = build_service_info(port, host_ip)
    zc = Zeroconf()
    zc.register_service(info)
    return MdnsRegistration(zc, info)
