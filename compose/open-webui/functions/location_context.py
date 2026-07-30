"""
Filter: Location Context Injector
Reads the client IP from X-Forwarded-For (set by Traefik), geolocates it via
ip-api.com, and prepends a system message with city/country/lat/lon/timezone
so the LLM can answer location-specific questions without being asked.

Private LAN IPs (192.168.x.x etc.) cannot be geolocated directly, so the
filter falls back to geolocating the server's own public egress IP — on a
single-site LAN this is the same public address as the user's.
"""

import time
import requests
from typing import Optional
from pydantic import BaseModel, Field
from starlette.requests import Request


IP_API_URL = "http://ip-api.com/json/{ip}?fields=status,city,country,countryCode,lat,lon,timezone"
IP_API_SELF_URL = "http://ip-api.com/json/?fields=status,city,country,countryCode,lat,lon,timezone"

PRIVATE_PREFIXES = (
    "10.", "127.", "::1",
    "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.",
    "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
    "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.",
)


class Filter:
    class Valves(BaseModel):
        enabled: bool = Field(default=True, description="Enable location context injection")
        cache_ttl_seconds: int = Field(default=3600, description="Seconds to cache each IP geolocation result")
        default_location: str = Field(
            default="",
            description="Fallback location string if geolocation fails entirely, e.g. 'Melbourne, Australia (lat: -37.81, lon: 144.96, timezone: Australia/Melbourne)'"
        )

    def __init__(self):
        self.valves = self.Valves()
        self._cache: dict = {}

    def _is_private(self, ip: str) -> bool:
        return any(ip.startswith(p) for p in PRIVATE_PREFIXES)

    def _fetch_geo(self, url: str) -> Optional[dict]:
        try:
            resp = requests.get(url, timeout=3)
            data = resp.json()
            if data.get("status") == "success":
                return {
                    "city": data.get("city", ""),
                    "country": data.get("country", ""),
                    "country_code": data.get("countryCode", ""),
                    "lat": data.get("lat"),
                    "lon": data.get("lon"),
                    "timezone": data.get("timezone", ""),
                }
        except Exception:
            pass
        return None

    def _geolocate(self, ip: str) -> Optional[dict]:
        now = time.time()

        cache_key = ip if not self._is_private(ip) else "__self__"

        if cache_key in self._cache:
            cached, ts = self._cache[cache_key]
            if now - ts < self.valves.cache_ttl_seconds:
                return cached

        if self._is_private(ip):
            result = self._fetch_geo(IP_API_SELF_URL)
        else:
            result = self._fetch_geo(IP_API_URL.format(ip=ip))

        if result:
            self._cache[cache_key] = (result, now)
        return result

    def _extract_ip(self, request: Request) -> Optional[str]:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return None

    async def inlet(
        self,
        body: dict,
        __request__: Request = None,
        __user__: Optional[dict] = None,
    ) -> dict:
        if not self.valves.enabled:
            return body

        loc_str = None

        if __request__:
            ip = self._extract_ip(__request__)
            if ip:
                loc = self._geolocate(ip)
                if loc:
                    loc_str = (
                        f"{loc['city']}, {loc['country']} "
                        f"(lat: {loc['lat']}, lon: {loc['lon']}, timezone: {loc['timezone']})"
                    )

        if not loc_str and self.valves.default_location:
            loc_str = self.valves.default_location

        if not loc_str:
            return body

        system_msg = {
            "role": "system",
            "content": (
                f"The user's current location is: {loc_str}. "
                "Use this when answering location-specific questions such as weather, "
                "local time, news, or nearby services. When calling the weather tool, "
                "use the latitude and longitude from this location unless the user specifies otherwise."
            ),
        }

        messages = body.get("messages", [])
        # Insert immediately after any existing system messages
        insert_at = 0
        for i, msg in enumerate(messages):
            if msg.get("role") == "system":
                insert_at = i + 1
            else:
                break
        messages.insert(insert_at, system_msg)
        body["messages"] = messages
        return body
