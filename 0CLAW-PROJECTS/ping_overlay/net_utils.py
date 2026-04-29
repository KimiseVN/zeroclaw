"""Lấy các kết nối ESTABLISHED của 1 process, geolocation IP, ping.

Hỗ trợ network accelerator (ExitLag, Gearup Booster, WTFast, NoPing, ...):
khi accelerator chạy, traffic của game thường bị tunnel — IP psutil thấy của
process game có thể là local proxy (127.x, 10.x) hoặc IP game server thật
nhưng route đi qua tunnel. Trong cả hai case, IP outbound của accelerator
service mới đại diện cho route thực tế tới máy chủ game.
"""
import ipaddress
import math
import subprocess
import time

import psutil
import ping3
import requests

ping3.EXCEPTIONS = False

_geo_cache: dict[str, dict] = {}


# Keyword -> friendly name. Match SUBSTRING sau khi normalize tên process
# (lowercase, bỏ '_', '-', ' ', '.exe'). Cách này bắt được mọi biến thể tên:
# 'gearup_booster.exe', 'GearUp Booster.exe', 'gearupboosterservice.exe',
# 'gearup-booster-service.exe' đều match keyword 'gearup'.
ACCELERATOR_KEYWORDS: dict[str, str] = {
    "exitlag": "ExitLag",
    "gearup": "Gearup Booster",
    "wtfast": "WTFast",
    "noping": "NoPing",
    "pingbooster": "PingBooster",
    "battleping": "BattlePing",
    "haste": "Haste",
    "outfox": "Outfox",
    "lagofast": "LagoFast",
    "killping": "Kill Ping",
    "smarttele": "SmartTele",
    "wangsu": "Wangsu",       # 网宿/迅游 - China gaming accelerator
    "xunyou": "迅游 (Xunyou)",
    "uuboost": "UU Booster",
    "tencentgsboost": "Tencent NetSpeed",
    "tgnboost": "Tencent NetSpeed",
    "qqlive4game": "QQ Live for Game",
    "lol-gameaccel": "LoL Gameaccel",
}


def _normalize_proc_name(raw: str) -> str:
    """Lowercase + strip separators + bỏ '.exe' để match keyword bền vững
    với mọi biến thể naming."""
    n = (raw or "").lower().strip()
    if n.endswith(".exe"):
        n = n[:-4]
    for sep in ("_", "-", " ", "."):
        n = n.replace(sep, "")
    return n


def _accelerator_friendly_name(proc_name: str) -> str | None:
    """Trả friendly name nếu proc_name match một keyword accelerator."""
    norm = _normalize_proc_name(proc_name)
    if not norm:
        return None
    for kw, friendly in ACCELERATOR_KEYWORDS.items():
        if kw in norm:
            return friendly
    return None


_accelerator_warned: set[int] = set()


def list_exe_processes() -> list[tuple[int, str]]:
    """Trả về list (pid, exe_name) của các process có .exe."""
    out = []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = p.info["name"] or ""
            if name.lower().endswith(".exe"):
                out.append((p.info["pid"], name))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # unique by name, giữ pid đầu
    seen = {}
    for pid, name in out:
        seen.setdefault(name, pid)
    return sorted([(pid, n) for n, pid in seen.items()], key=lambda x: x[1].lower())


def established_remote_ips(pid: int | None = None) -> list[str]:
    """Chạy `netstat -ano | findstr ESTABLISHED`, lấy IP ở cột thứ 3
    (Foreign Address), loại bỏ 127.0.0.1. Nếu truyền `pid` thì chỉ giữ
    các dòng có PID tương ứng, nếu không thì lấy toàn bộ.
    """
    try:
        CREATE_NO_WINDOW = 0x08000000
        res = subprocess.run(
            'netstat -ano | findstr ESTABLISHED',
            shell=True, capture_output=True, text=True,
            creationflags=CREATE_NO_WINDOW, timeout=5,
        )
        lines = res.stdout.splitlines()
    except Exception:
        lines = []

    ips: list[str] = []
    seen: set[str] = set()
    for line in lines:
        parts = line.split()
        # Proto  Local  Foreign(cột 3)  State  PID
        if len(parts) < 5:
            continue
        if pid is not None:
            try:
                if int(parts[-1]) != pid:
                    continue
            except ValueError:
                continue
        foreign = parts[2]
        if foreign.startswith("["):
            ip = foreign[1:foreign.rfind("]")]
        else:
            ip = foreign.rsplit(":", 1)[0]
        if ip == "127.0.0.1" or ip in seen:
            continue
        seen.add(ip)
        ips.append(ip)
    return ips


def gameplay_remote_ips(pid: int) -> list[str]:
    """UDP remote endpoints của process — đây là IP gameplay server candidate.
    Game online realtime hầu như luôn dùng UDP, nên những IP này đáng tin hơn
    nhiều so với TCP (thường là auth / telemetry / CDN ở xa).
    """
    try:
        conns = psutil.Process(pid).net_connections(kind="udp")
    except Exception:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for c in conns:
        if not c.raddr:
            continue
        ip = c.raddr.ip
        if ip == "127.0.0.1" or ip in seen or not _is_public(ip):
            continue
        seen.add(ip)
        out.append(ip)
    return out


def active_traffic_ips(pid: int, window_s: float = 4.0,
                        threshold: float = 0.6) -> list[str]:
    """Sample remote IPs N lần trong cửa sổ `window_s` giây, return IP
    xuất hiện trong >= `threshold` snapshots (default 60%). Sort theo độ
    ổn định giảm dần. Loại được transient connections (DNS, telemetry,
    CDN ping, auth handshake).
    Combine UDP gameplay (raddr non-null) + TCP established để cover các
    game không expose UDP raddr trên Windows.
    """
    interval = 0.5
    n_samples = max(2, int(round(window_s / interval)))
    counts: dict[str, int] = {}
    for _ in range(n_samples):
        try:
            conns = psutil.Process(pid).net_connections(kind="inet")
        except Exception:
            time.sleep(interval)
            continue
        seen_this: set[str] = set()
        for c in conns:
            if not c.raddr:
                continue
            try:
                ip = c.raddr.ip
            except Exception:
                continue
            if ip == "127.0.0.1" or not _is_public(ip):
                continue
            seen_this.add(ip)
        for ip in seen_this:
            counts[ip] = counts.get(ip, 0) + 1
        time.sleep(interval)
    min_count = max(2, int(round(n_samples * threshold)))
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return [ip for ip, c in ranked if c >= min_count]


def has_non_public_remote_ip(pid: int) -> bool:
    """True nếu process đang nói chuyện với loopback/private peer.
    Đây là tín hiệu mạnh cho local proxy / tunnel client của accelerator.
    """
    try:
        conns = psutil.Process(pid).net_connections(kind="inet")
    except Exception:
        return False
    for c in conns:
        if not c.raddr:
            continue
        try:
            ip = c.raddr.ip
        except Exception:
            continue
        if ip and not _is_public(ip):
            return True
    return False


def persistent_remote_ips(pid: int, delay: float = 2.0) -> list[str]:
    """Lấy 2 snapshot TCP/UDP cách nhau `delay` giây, giữ IP có mặt ở CẢ HAI.
    Dùng để loại các kết nối TCP thoáng qua (HTTPS auth, telemetry) và chỉ
    giữ lại những endpoint mà process đang thực sự gửi/nhận liên tục.
    """
    def snap() -> set[str]:
        try:
            conns = psutil.Process(pid).net_connections(kind="inet")
        except Exception:
            return set()
        s: set[str] = set()
        for c in conns:
            if not c.raddr:
                continue
            ip = c.raddr.ip
            if ip == "127.0.0.1" or not _is_public(ip):
                continue
            s.add(ip)
        return s

    a = snap()
    time.sleep(delay)
    b = snap()
    return list(a & b)


def _remote_ips_of_pid(pid: int) -> set[str]:
    """Tất cả public remote IP (TCP + UDP có raddr) của 1 PID qua psutil.
    LƯU Ý Windows: UDP raddr gần như luôn rỗng do kernel không track; tức
    tập này thực tế = TCP connections. Vẫn đủ để nhận biết lobby vì game
    online luôn có TCP backend (matchmaker/chat/auth) bền vững khi in-game.
    """
    try:
        conns = psutil.Process(pid).net_connections(kind="inet")
    except Exception:
        return set()
    out: set[str] = set()
    for c in conns:
        if not c.raddr:
            continue
        try:
            ip = c.raddr.ip
        except Exception:
            continue
        if ip == "127.0.0.1" or not _is_public(ip):
            continue
        out.add(ip)
    return out


def wait_for_lobby(pid: int, stop_event, required: int = 3,
                   interval: float = 2.0, timeout: float = 120.0) -> list[str]:
    """Chờ cho đến khi tập remote IP của process ỔN ĐỊNH:
    `required` snapshot liên tiếp (cách `interval` giây) có overlap với
    snapshot trước — dấu hiệu login/matchmaking đã xong và connection pool
    gameplay đã thiết lập (user đang ở lobby/in-game).
    Ưu tiên UDP gameplay nếu có (Linux); trên Windows sẽ dùng TCP raddr.
    """
    deadline = time.time() + timeout
    prev: set[str] = set()
    streak = 0
    while not stop_event.is_set() and time.time() < deadline:
        accel_ips, mode = gameplay_traffic_ips(pid, window_s=1.0, threshold=0.5)
        if accel_ips and mode.startswith("accelerator:"):
            ips = set(accel_ips)
        else:
            udp = set(gameplay_remote_ips(pid))
            ips = udp if udp else _remote_ips_of_pid(pid)
        if ips and (not prev or (ips & prev)):
            streak += 1
        else:
            streak = 1 if ips else 0
        prev = ips
        if streak >= required and ips:
            return list(ips)
        if stop_event.wait(interval):
            return []
    return []


def all_remote_ips_by_pid() -> dict[int, list[str]]:
    """Quét psutil.net_connections('inet') — bao phủ CẢ TCP ESTABLISHED và
    UDP connected (có raddr). Trả về map pid -> list public IP.
    Đây là hàm chính dùng cho detect_game_process vì nhiều game online
    chỉ dùng UDP cho gameplay, sẽ không hiện trong `netstat findstr ESTABLISHED`.
    """
    out: dict[int, list[str]] = {}
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        return out
    for c in conns:
        if c.pid is None or not c.raddr:
            continue
        try:
            ip = c.raddr.ip
        except Exception:
            continue
        if ip == "127.0.0.1" or not _is_public(ip):
            continue
        lst = out.setdefault(c.pid, [])
        if ip not in lst:
            lst.append(ip)
    return out


def all_established_by_pid() -> dict[int, list[str]]:
    """Parse toàn bộ netstat một lần, trả về map pid -> list public IP."""
    try:
        CREATE_NO_WINDOW = 0x08000000
        res = subprocess.run(
            'netstat -ano | findstr ESTABLISHED',
            shell=True, capture_output=True, text=True,
            creationflags=CREATE_NO_WINDOW, timeout=5,
        )
        lines = res.stdout.splitlines()
    except Exception:
        return {}

    out: dict[int, list[str]] = {}
    for line in lines:
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            line_pid = int(parts[-1])
        except ValueError:
            continue
        foreign = parts[2]
        if foreign.startswith("["):
            ip = foreign[1:foreign.rfind("]")]
        else:
            ip = foreign.rsplit(":", 1)[0]
        if ip == "127.0.0.1" or not _is_public(ip):
            continue
        lst = out.setdefault(line_pid, [])
        if ip not in lst:
            lst.append(ip)
    return out


def scan_cities(ips: list[str]) -> list[tuple[str, str, dict]]:
    """Geolocate danh sách IP, trả về list (city, ip, geo).
    Bỏ qua IP private/loopback và IP không geolocate được.
    """
    result: list[tuple[str, str, dict]] = []
    for ip in ips:
        if not _is_public(ip):
            continue
        geo = geolocate(ip)
        if not geo:
            continue
        city = (geo.get("city") or "").strip()
        if not city:
            continue
        result.append((city, ip, geo))
    return result


def _is_public(ip: str) -> bool:
    try:
        obj = ipaddress.ip_address(ip)
        return not (obj.is_private or obj.is_loopback or obj.is_link_local
                    or obj.is_multicast or obj.is_unspecified or obj.is_reserved)
    except ValueError:
        return False


def geolocate(ip: str) -> dict | None:
    """ip-api.com free endpoint. Cache để tránh rate-limit (45 req/phút)."""
    if ip in _geo_cache:
        return _geo_cache[ip]
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,lat,lon,isp",
            timeout=3,
        )
        data = r.json()
        if data.get("status") == "success":
            _geo_cache[ip] = data
            return data
    except Exception:
        pass
    return None


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def find_accelerators() -> list[tuple[int, str]]:
    """Trả về list (pid, friendly_name) tất cả accelerator process đang chạy.
    ExitLag/Gearup thường chạy nhiều process (UI + service + ball/checker);
    tất cả đều cần xét vì service mới giữ tunnel connection.
    Match dùng keyword normalized -> bắt được mọi biến thể naming
    ('gearup_booster.exe', 'Gearup Booster.exe', 'gearupboosterservice.exe').
    """
    out: list[tuple[int, str]] = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            raw = (p.info.get("name") or "").strip()
        except Exception:
            continue
        friendly = _accelerator_friendly_name(raw)
        if friendly:
            out.append((p.info["pid"], friendly))
    return out


def accelerator_outbound_ips(accel_pid: int,
                              window_s: float = 1.5,
                              threshold: float = 0.66) -> list[str]:
    """IPs outbound public của 1 accelerator process — đây là tunnel exit
    nodes mà accelerator đang relay traffic của game tới."""
    return active_traffic_ips(accel_pid, window_s, threshold)


def gameplay_traffic_ips(
    pid: int,
    window_s: float = 1.5,
    threshold: float = 0.66,
) -> tuple[list[str], str]:
    """High-level: trả (ips, mode) đại diện route gameplay thực tế.

    Thứ tự thử:
    1. Direct: process có public IP → mode='direct', dùng IPs đó.
    2. Accelerator: process không có public IP NHƯNG có accelerator chạy
       → mode='accelerator:<Name>', dùng IPs outbound của accelerator
       service. Đây là trường hợp ExitLag/Gearup tunnel traffic.
    3. None: không tìm được → mode='none'.

    Lần đầu detect accelerator sẽ log 1 cảnh báo qua console.
    """
    accels = find_accelerators()
    direct = active_traffic_ips(pid, window_s, threshold)
    local_proxy = has_non_public_remote_ip(pid)

    accel_combined: list[str] = []
    chosen_name: str | None = None
    if accels:
        # Gộp IP của tất cả accelerator process (UI + service)
        for accel_pid, name in accels:
            ips = accelerator_outbound_ips(accel_pid, window_s, threshold)
            if ips:
                chosen_name = chosen_name or name
                for ip in ips:
                    if ip not in accel_combined:
                        accel_combined.append(ip)

    # Tunnel/local-proxy case: accelerator route mới là đường thật.
    if accel_combined and (local_proxy or not direct):
        key = hash(chosen_name or "accelerator")
        if key not in _accelerator_warned:
            _accelerator_warned.add(key)
            print(f"[net] {chosen_name or 'Accelerator'} detected — game traffic tunneled. "
                  f"Pinging accelerator exit node(s) for in-game latency.")
        return accel_combined, f"accelerator:{chosen_name or 'Accelerator'}"

    if direct:
        return direct, "direct"

    # Last fallback: accelerator vẫn tốt hơn không có gì nếu game route hoàn toàn
    # đi qua booster nhưng Windows không lộ được socket của process game.
    if accel_combined and chosen_name:
        key = hash(chosen_name)
        if key not in _accelerator_warned:
            _accelerator_warned.add(key)
            print(f"[net] {chosen_name} detected — using accelerator exit node fallback.")
        return accel_combined, f"accelerator:{chosen_name}"

    return [], "none"


def ping_ms(ip: str, samples: int = 5) -> tuple[float | None, float]:
    """ICMP ping trung bình (ms) và packet loss (%).
    Trả về (avg_ms hoặc None, loss_percent).
    """
    vals = []
    lost = 0
    for _ in range(samples):
        try:
            r = ping3.ping(ip, timeout=1, unit="ms")
            if r is not None and r is not False:
                vals.append(float(r))
            else:
                lost += 1
        except Exception:
            lost += 1
        time.sleep(0.05)
    loss = lost / samples * 100.0
    avg = sum(vals) / len(vals) if vals else None
    return avg, loss
