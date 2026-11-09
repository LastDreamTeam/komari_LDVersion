#!/usr/bin/env python3
"""One-time init: panel host public IP -> geo -> miku39 default destination (auto).

Run on the Komari panel host after installing/moving the theme:
  python3 /opt/komari/data/theme/miku39/scripts/init-host-destination.py

Does NOT run on every page load. Writes:
  - dist/panel-host-geo.json  (audit trail)
  - komari-theme.json defaults for destination_* + default_destination=auto
  - theme_configurations.short=miku39 (managed runtime settings)

Re-run when the panel moves to another public IP.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

THEME_ROOT = Path(__file__).resolve().parents[1]
DIST = THEME_ROOT / "dist"
THEME_JSON = THEME_ROOT / "komari-theme.json"
GEO_JSON = DIST / "panel-host-geo.json"
DB_CANDIDATES = [
    Path("/opt/komari/data/komari.db"),
    THEME_ROOT.parents[1] / "komari.db",  # /opt/komari/data/komari.db via theme/../
]


def http_json(url: str, timeout: float = 12.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "miku39-init-host-destination/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def detect_public_ip() -> str:
    for url in (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
    ):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "miku39-init-host-destination/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                ip = resp.read().decode("utf-8", "replace").strip()
                if ip and ":" not in ip and ip.count(".") == 3:
                    return ip
        except Exception as exc:  # noqa: BLE001
            print(f"warn: public IP via {url}: {exc}", file=sys.stderr)
    raise SystemExit("failed to detect panel public IPv4")



def place_name(city: str, region: str = "", country: str = "") -> str:
    """Human place label only — no「面板主机 ·」prefix."""
    city = (city or "").strip()
    region = (region or "").strip()
    country = (country or "").strip()
    if city and region and region != city:
        label = f"{city}/{region}"
    elif city:
        label = city
    elif region:
        label = region
    elif country:
        label = country
    else:
        label = "Unknown"
    return label[:32]


def geolocate(ip: str) -> dict:
    """Prefer ipinfo (Komari default provider), fall back to ip-api."""
    errors = []
    try:
        info = http_json(f"https://ipinfo.io/{ip}/json")
        loc = str(info.get("loc") or "")
        if "," in loc:
            lat_s, lng_s = loc.split(",", 1)
            lat, lng = float(lat_s), float(lng_s)
            city = (info.get("city") or "").strip()
            region = (info.get("region") or "").strip()
            cc = (info.get("country") or "").strip()
            name = place_name(city, region, cc)
            return {
                "provider": "ipinfo",
                "ip": ip,
                "lat": lat,
                "lng": lng,
                "city": city,
                "region": region,
                "country": cc,
                "name": name[:32],
                "raw": info,
            }
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ipinfo: {exc}")
    try:
        info = http_json(f"http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,regionName,city,lat,lon,query")
        if info.get("status") == "success":
            city = (info.get("city") or "").strip()
            region = (info.get("regionName") or "").strip()
            name = place_name(city, region, (info.get("countryCode") or "").strip())
            return {
                "provider": "ip-api",
                "ip": ip,
                "lat": float(info["lat"]),
                "lng": float(info["lon"]),
                "city": city,
                "region": region,
                "country": (info.get("countryCode") or "").strip(),
                "name": name[:32],
                "raw": info,
            }
        errors.append(f"ip-api: {info}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ip-api: {exc}")
    raise SystemExit("geolocate failed: " + "; ".join(errors))


def patch_theme_json(geo: dict) -> None:
    data = json.loads(THEME_JSON.read_text(encoding="utf-8"))
    items = data.setdefault("configuration", {}).setdefault("data", [])
    by_key = {it.get("key"): it for it in items if isinstance(it, dict) and it.get("key")}
    dest = by_key.get("default_destination")
    if dest:
        opts = str(dest.get("options") or "")
        parts = [p for p in opts.split(",") if p]
        if "auto" not in parts:
            parts.append("auto")
        dest["options"] = ",".join(parts)
        dest["default"] = "auto"
        help_text = str(dest.get("help") or "")
        if "auto =" not in help_text:
            dest["help"] = (
                help_text.rstrip("。") + "；auto = 按面板主机公网 IP 一次性定位（scripts/init-host-destination.py），写入 destination_*。"
            ).strip()
    for key, value in (
        ("destination_name", geo["name"]),
        ("destination_lat", geo["lat"]),
        ("destination_lng", geo["lng"]),
    ):
        if key in by_key:
            by_key[key]["default"] = value
            if key == "destination_name":
                by_key[key]["help"] = "auto / custom 时使用；auto 由 init-host-destination.py 按面板公网 IP 写入。"
            else:
                by_key[key]["help"] = "auto / custom 时使用；−90..90 或 −180..180；由面板主机 IP 一次性定位写入。"
    # bump patch version lightly if semver-like
    ver = str(data.get("version") or "1.4.9")
    data["version"] = ver
    THEME_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_db() -> Path | None:
    for p in DB_CANDIDATES:
        if p.is_file():
            return p
    env = os.environ.get("KOMARI_DB")
    if env and Path(env).is_file():
        return Path(env)
    return None


def patch_theme_configurations(geo: dict, db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT data FROM theme_configurations WHERE short=?", ("miku39",)).fetchone()
        cfg = json.loads(row[0]) if row and row[0] else {}
        if not isinstance(cfg, dict):
            cfg = {}
        cfg["default_destination"] = "auto"
        cfg["destination_name"] = geo["name"]
        cfg["destination_lat"] = geo["lat"]
        cfg["destination_lng"] = geo["lng"]
        payload = json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))
        if row:
            conn.execute("UPDATE theme_configurations SET data=? WHERE short=?", (payload, "miku39"))
        else:
            conn.execute("INSERT INTO theme_configurations(short, data) VALUES(?, ?)", ("miku39", payload))
        conn.commit()
    finally:
        conn.close()


def write_geo_audit(geo: dict) -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    audit = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "note": "One-time panel-host geo for miku39 default_destination=auto. Not refreshed per page view.",
        "ip": geo["ip"],
        "provider": geo["provider"],
        "lat": geo["lat"],
        "lng": geo["lng"],
        "name": geo["name"],
        "city": geo.get("city"),
        "region": geo.get("region"),
        "country": geo.get("country"),
    }
    GEO_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    force_ip = os.environ.get("PANEL_PUBLIC_IP", "").strip()
    ip = force_ip or detect_public_ip()
    print(f"panel public IP: {ip}")
    geo = geolocate(ip)
    print(f"geo via {geo['provider']}: {geo['name']} ({geo['lat']}, {geo['lng']})")
    write_geo_audit(geo)
    print(f"wrote {GEO_JSON}")
    if THEME_JSON.is_file():
        patch_theme_json(geo)
        print(f"updated {THEME_JSON}")
    else:
        print(f"warn: missing {THEME_JSON}", file=sys.stderr)
    db = find_db()
    if db:
        patch_theme_configurations(geo, db)
        print(f"updated theme_configurations in {db}")
    else:
        print("warn: komari.db not found; skipped theme_configurations", file=sys.stderr)
    print("done: default_destination=auto (one-time init)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
