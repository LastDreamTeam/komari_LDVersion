#!/usr/bin/env python3
"""Minimal fleet TCP-flow sampler for miku39 globe「数据收发」mode.
Runs on the Komari host, writes /opt/komari/data/theme/miku39/dist/flows.json.
Does not modify Komari/NodeAgent. SSH failures are skipped.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("MIKU39_FLOW_ROOT", "/opt/miku39-flow"))
HOSTS_FILE = ROOT / "hosts.json"
KEY_FILE = ROOT / "id_ed25519"
CACHE_FILE = ROOT / "geoip-cache.json"
OUT_FILE = Path(
    os.environ.get(
        "MIKU39_FLOWS_OUT",
        "/opt/komari/data/theme/miku39/dist/flows.json",
    )
)
STATE_FILE = ROOT / "flows-state.json"
TTL_SEC = 420
MAX_PEERS_PER_HOST = 40
MAX_GEO_LOOKUPS = 40
GEO_MIN_INTERVAL = 1.2  # polite to public GeoIP

SS_CMD = "ss -Htn state established; echo '---LISTEN---'; ss -Htnl"

PREFAB_GEO = {
    # Intentionally empty: do not hardcode any address literals here.
    # Fleet / peer coordinates come from hosts.json (lat/lng/ips per entry).
}

# /8-ish prefab by first octet ranges for coarse fallback (optional later)
SS_LINE = re.compile(
    r"^(?:\S+\s+){3}(\S+):(\d+)\s+(\S+):(\d+)\s*$"
)
# ss -Htn may look like: Recv-Q Send-Q Local Address:Port Peer Address:Port
# With -H: no header. Format often: Recv-Q Send-Q Local:port Peer:port


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(ts: float | None = None) -> str:
    dt = utc_now() if ts is None else datetime.fromtimestamp(ts, timezone.utc)
    # JS Date.parse is happier with Z and millisecond precision
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(dt.microsecond/1000):03d}Z"


def is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, mode)
    tmp.replace(path)


def parse_ss(text: str):
    established, listen = [], set()
    part = "est"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "---LISTEN---":
            part = "listen"
            continue
        # strip optional columns: Recv-Q Send-Q Local Peer [Process]
        # Prefer last two host:port-looking tokens
        toks = line.split()
        if len(toks) < 2:
            continue
        # find two addr:port from the right, ignoring process
        addrs = []
        for t in toks:
            if t.startswith("users:("):
                break
            if ":" in t:
                # bracketed IPv6 host:port or dotted IPv4 host:port
                addrs.append(t)
        if len(addrs) < 2:
            continue
        local, peer = addrs[-2], addrs[-1]

        def split_ap(ap: str):
            # listen Peer can be wildcard any-address / *
            if ap in ("*", "*:*"):
                return "*", 0
            if ap.startswith("["):
                m = re.match(r"^\[([^\]]+)\]:(\*|\d+)$", ap)
                if m:
                    port = 0 if m.group(2) == "*" else int(m.group(2))
                    return m.group(1), port
            if ap.count(":") == 1:
                a, port_s = ap.rsplit(":", 1)
                if port_s == "*":
                    return a, 0
                return a, int(port_s)
            # bare ipv6 without brackets rare in ss
            return ap, 0

        try:
            lip, lport = split_ap(local)
            pip, pport = split_ap(peer)
        except Exception:
            continue
        if part == "listen":
            # only local listen port matters; skip wildcard/failed local
            if lport:
                listen.add(lport)
        else:
            established.append((lip, lport, pip, pport))
    return established, listen


def run_local_ss() -> str:
    return subprocess.check_output(
        ["bash", "-lc", SS_CMD], text=True, stderr=subprocess.DEVNULL, timeout=15
    )


def run_remote_ss(host: dict) -> str:
    ip = host["host"]
    port = int(host.get("port") or 22)
    user = host.get("user") or "root"
    timeout = int(host.get("timeout") or 12)
    base = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "GlobalKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-p",
        str(port),
    ]
    key = KEY_FILE
    host_key = host.get("key")
    if host_key:
        cand = Path(host_key)
        if not cand.is_absolute():
            cand = ROOT / cand
        if cand.exists():
            key = cand
    if key.exists():
        base += ["-i", str(key)]
    cmd = base + [f"{user}@{ip}", SS_CMD]
    try:
        return subprocess.check_output(
            cmd, text=True, stderr=subprocess.PIPE, timeout=timeout
        )
    except Exception as key_err:
        pw = host.get("pass")
        if not pw:
            raise key_err
        # password fallback via sshpass (hosts.json is root-only)
        env = os.environ.copy()
        env["SSHPASS"] = pw
        cmd2 = [
            "sshpass",
            "-e",
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "GlobalKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=8",
            "-o",
            "PreferredAuthentications=password",
            "-o",
            "PubkeyAuthentication=no",
            "-p",
            str(port),
            f"{user}@{ip}",
            SS_CMD,
        ]
        return subprocess.check_output(
            cmd2, text=True, stderr=subprocess.PIPE, timeout=timeout, env=env
        )


class GeoResolver:
    def __init__(self):
        self.cache = load_json(CACHE_FILE, {})
        self._last_fetch = 0.0

    def resolve(self, ip: str):
        if ip in PREFAB_GEO:
            lat, lng, label, cc = PREFAB_GEO[ip]
            return {
                "lat": lat,
                "lng": lng,
                "label": label,
                "city": label,
                "country": cc,
                "source": "prefab",
            }
        hit = self.cache.get(ip)
        if hit and hit.get("lat") is not None:
            return hit
        # rate-limit live lookups
        if getattr(self, "_lookups", 0) >= MAX_GEO_LOOKUPS:
            return None
        now = time.time()
        wait = GEO_MIN_INTERVAL - (now - self._last_fetch)
        if wait > 0:
            time.sleep(wait)
        self._last_fetch = time.time()
        self._lookups = getattr(self, "_lookups", 0) + 1
        url = f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,city,lat,lon,query"
        try:
            with urllib.request.urlopen(url, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as e:
            return None
        if data.get("status") != "success":
            return None
        entry = {
            "lat": float(data["lat"]),
            "lng": float(data["lon"]),
            "label": data.get("city") or data.get("country") or ip,
            "city": data.get("city") or "",
            "country": data.get("countryCode") or "",
            "source": "ip-api",
            "cached_at": iso(),
        }
        self.cache[ip] = entry
        return entry

    def flush(self):
        save_json(CACHE_FILE, self.cache, 0o644)


# Remote ports that usually mean "we dialed a service" (outbound client).
COMMON_SERVICE_PORTS = {
    21, 22, 25, 53, 80, 110, 143, 443, 465, 587, 853, 993, 995,
    1194, 1701, 1723, 3306, 5432, 6379, 8080, 8443, 9443,
}

def classify_dir(lport: int, pport: int, listen_ports: set[int]) -> str:
    """TCP direction from this host's view.
    - local port listening => inbound (peer connected to us)
    - exception: local listen port reused as outbound source toward a remote service port
    - otherwise outbound
    """
    if lport in listen_ports:
        if pport in COMMON_SERVICE_PORTS and pport != lport:
            return "out"
        return "in"
    return "out"


def sample_host(host: dict, geo: GeoResolver, now_ts: float):
    errors = []
    flows = []
    name = host.get("name") or host["host"]
    try:
        if host.get("local"):
            text = run_local_ss()
        else:
            text = run_remote_ss(host)
    except Exception as e:
        return [], f"{name}: {e.__class__.__name__}: {getattr(e, 'stderr', b'')[:200] or e}"

    established, listen = parse_ss(text)
    host_ips = set(host.get("ips") or [])
    host_ips.add(host["host"])
    # also treat common private as "local side"
    for lip, lport, pip, pport in established:
        if not is_public_ip(pip):
            continue
        # skip peer that is another fleet public IP? keep them — useful mesh view
        direction = classify_dir(lport, pport, listen)
        if len(flows) >= MAX_PEERS_PER_HOST:
            break
        geoinfo = geo.resolve(pip)
        if not geoinfo:
            continue
        # id ignores dir so a reclassified socket updates instead of stacking stale opposite arcs
        fid = f"{host.get('uuid') or host['host']}:{pip}:{lport}"
        flows.append(
            {
                "id": fid,
                "dir": direction,
                "host_uuid": host.get("uuid") or "",
                "host_name": host.get("komari") or name,
                "host_lat": host["lat"],
                "host_lng": host["lng"],
                "peer_ip": pip,
                "peer_lat": geoinfo["lat"],
                "peer_lng": geoinfo["lng"],
                "peer_label": geoinfo.get("label") or pip,
                "peer_city": geoinfo.get("city") or "",
                "peer_country": geoinfo.get("country") or "",
                "last_seen": iso(now_ts),
                "local_port": lport,
                "peer_port": pport,
            }
        )
    return flows, None


def merge_state(prev: dict, new_flows: list, now_ts: float) -> list:
    by_id = {}
    for f in prev.get("flows") or []:
        # drop legacy ids "uuid:dir:ip" that cannot update direction in place
        fid = str(f.get("id") or "")
        parts = fid.split(":")
        if len(parts) == 3 and parts[1] in ("in", "out"):
            continue
        by_id[fid] = f
    for f in new_flows:
        old = by_id.get(f["id"])
        if old:
            f = {**old, **f}
        by_id[f["id"]] = f
        # same host+peer+local_port must not keep an opposite-dir ghost under another id
        for oid in list(by_id):
            if oid == f["id"]:
                continue
            o = by_id[oid]
            if (
                o.get("host_uuid") == f.get("host_uuid")
                and o.get("peer_ip") == f.get("peer_ip")
                and o.get("local_port") == f.get("local_port")
                and o.get("dir") != f.get("dir")
            ):
                del by_id[oid]
    # drop expired
    kept = []
    for f in by_id.values():
        try:
            age = now_ts - datetime.fromisoformat(f["last_seen"]).timestamp()
        except Exception:
            age = TTL_SEC + 1
        if age <= TTL_SEC + 5:
            kept.append(f)
    kept.sort(key=lambda x: x.get("last_seen") or "", reverse=True)
    return kept[:200]


def main():
    hosts = load_json(HOSTS_FILE, [])
    if not hosts:
        print("no hosts.json", file=sys.stderr)
        return 2
    hosts = [h for h in hosts if not h.get("skip")]
    geo = GeoResolver()
    prev = load_json(STATE_FILE, {"flows": []})
    now_ts = time.time()
    collected = []
    errors = []
    for h in hosts:
        flows, err = sample_host(h, geo, now_ts)
        if err:
            errors.append(err)
            print("SKIP", err, file=sys.stderr)
        else:
            collected.extend(flows)
            print(f"OK {h.get('name') or h['host']}: {len(flows)} peers", file=sys.stderr)
    # stamp at write-time so last_seen is not aged by slow SSH/Geo rounds
    write_ts = time.time()
    for f in collected:
        f["last_seen"] = iso(write_ts)
    merged = merge_state(prev, collected, write_ts)
    out = {
        "updated_at": iso(write_ts),
        "ttl_sec": TTL_SEC,
        "flow_count": len(merged),
        "errors": errors[-20:],
        "flows": merged,
    }
    save_json(STATE_FILE, out, 0o600)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o644)
    # theme dist owned by komari
    try:
        import pwd, grp

        uid = pwd.getpwnam("komari").pw_uid
        gid = grp.getgrnam("komari").gr_gid
        os.chown(tmp, uid, gid)
    except Exception:
        pass
    tmp.replace(OUT_FILE)
    geo.flush()
    print(f"wrote {OUT_FILE} flows={len(merged)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
