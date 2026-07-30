import os
import requests
import geoip2.database
import geoip2.errors
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List

app = FastAPI(
    title="Weather API",
    version="1.0.0",
    description="Provides current conditions and a 5-day daily forecast using Open-Meteo.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEOIP_DB_PATH = os.environ.get("GEOIP_DB_PATH", "/geoip/GeoLite2-City.mmdb")
_geoip_reader: Optional[geoip2.database.Reader] = None

try:
    _geoip_reader = geoip2.database.Reader(GEOIP_DB_PATH)
except Exception:
    pass  # falls back to ip-api.com at runtime


class CurrentWeather(BaseModel):
    time: str
    temperature: float = Field(..., description="Current air temperature")
    wind_speed: float = Field(..., description="Current wind speed")
    temperature_unit: str
    wind_speed_unit: str = "km/h"


class DailyForecast(BaseModel):
    date: str = Field(..., description="Forecast date (YYYY-MM-DD)")
    temperature_max: float
    temperature_min: float
    precipitation_mm: float = Field(..., description="Total precipitation in mm")
    wind_speed_max: float
    temperature_unit: str
    wind_speed_unit: str = "km/h"


class WeatherResponse(BaseModel):
    location: str = Field(..., description="Resolved city and country")
    latitude: float
    longitude: float
    timezone: str
    current: CurrentWeather
    daily_forecast: List[DailyForecast] = Field(..., description="5-day daily forecast")


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
IP_API_URL = "http://ip-api.com/json/{ip}?fields=status,lat,lon,city,country,countryCode"
IP_API_SELF_URL = "http://ip-api.com/json/?fields=status,lat,lon,city,country,countryCode"
FAHRENHEIT_COUNTRIES = {"US", "LR", "MM"}

PRIVATE_PREFIXES = (
    "10.", "127.", "::1",
    "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.",
    "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
    "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.",
)


def _is_private(ip: str) -> bool:
    return any(ip.startswith(p) for p in PRIVATE_PREFIXES)


def _geoip_lookup(ip: str) -> Optional[dict]:
    if not _geoip_reader:
        return None
    try:
        rec = _geoip_reader.city(ip)
        return {
            "lat": rec.location.latitude,
            "lon": rec.location.longitude,
            "city": rec.city.name or "",
            "country": rec.country.name or "",
            "country_code": rec.country.iso_code or "",
        }
    except (geoip2.errors.AddressNotFoundError, Exception):
        return None


def _ipapi_lookup(ip: str) -> Optional[dict]:
    try:
        url = IP_API_SELF_URL if _is_private(ip) else IP_API_URL.format(ip=ip)
        resp = requests.get(url, timeout=3)
        data = resp.json()
        if data.get("status") == "success":
            return {
                "lat": data["lat"],
                "lon": data["lon"],
                "city": data.get("city", ""),
                "country": data.get("country", ""),
                "country_code": data.get("countryCode", ""),
            }
    except Exception:
        pass
    return None


def resolve_geo_from_ip(ip: str) -> Optional[dict]:
    if not _is_private(ip) and _geoip_reader:
        result = _geoip_lookup(ip)
        if result:
            return result
    return _ipapi_lookup(ip)


def geocode_city(city: str, country: Optional[str] = None) -> Optional[dict]:
    """Resolve a city name to lat/lon/country via Open-Meteo geocoding."""
    query = f"{city}, {country}" if country else city
    try:
        resp = requests.get(
            OPEN_METEO_GEO_URL,
            params={"name": query, "count": 1, "language": "en", "format": "json"},
            timeout=5,
        )
        resp.raise_for_status()
        results = resp.json().get("results")
        if results:
            r = results[0]
            return {
                "lat": r["latitude"],
                "lon": r["longitude"],
                "city": r.get("name", city),
                "country": r.get("country", ""),
                "country_code": r.get("country_code", ""),
            }
    except Exception:
        pass
    return None


def extract_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@app.get("/forecast", response_model=WeatherResponse, summary="Get current weather and 5-day forecast", operation_id="get_weather_forecast")
def get_weather_forecast(
    request: Request,
    city_name: Optional[str] = Query(None, alias="city", description="City name (e.g., 'Sydney', 'London'). Takes precedence over latitude/longitude."),
    country_name: Optional[str] = Query(None, alias="country", description="Country name to disambiguate the city (e.g., 'Australia'). Used only with city."),
    latitude: Optional[float] = Query(None, description="Latitude (e.g., -37.81). Auto-detected from IP when omitted."),
    longitude: Optional[float] = Query(None, description="Longitude (e.g., 144.96). Auto-detected from IP when omitted."),
):
    """
    Returns current conditions and a 5-day daily forecast (high/low temp, precipitation, max wind).
    Provide a city name (with optional country) OR latitude+longitude. When all are omitted, location is auto-detected from the caller's IP.
    Temperature unit is Celsius except for US, Liberia, and Myanmar where Fahrenheit is used.
    """
    city = country = country_code = ""

    if city_name:
        geo = geocode_city(city_name, country_name)
        if not geo:
            raise HTTPException(status_code=400, detail=f"Could not geocode city: {city_name}")
        latitude, longitude = geo["lat"], geo["lon"]
        city, country, country_code = geo["city"], geo["country"], geo["country_code"]
    elif latitude is None or longitude is None:
        ip = extract_client_ip(request)
        if ip:
            geo = resolve_geo_from_ip(ip)
            if geo:
                latitude = geo["lat"]
                longitude = geo["lon"]
                city = geo["city"]
                country = geo["country"]
                country_code = geo["country_code"]
        if latitude is None or longitude is None:
            raise HTTPException(
                status_code=400,
                detail="Could not determine location automatically. Please provide a city name or latitude and longitude.",
            )

    temperature_unit = "fahrenheit" if country_code in FAHRENHEIT_COUNTRIES else "celsius"
    temp_symbol = "°F" if temperature_unit == "fahrenheit" else "°C"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "timezone": "auto",
        "temperature_unit": temperature_unit,
        "forecast_days": 5,
    }

    try:
        resp = requests.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Error connecting to Open-Meteo API: {e}")

    if "current" not in data or "daily" not in data:
        raise HTTPException(status_code=500, detail="Unexpected response format from Open-Meteo API")

    current = CurrentWeather(
        time=data["current"]["time"],
        temperature=data["current"]["temperature_2m"],
        wind_speed=data["current"]["wind_speed_10m"],
        temperature_unit=temp_symbol,
    )

    daily = data["daily"]
    forecast = [
        DailyForecast(
            date=daily["time"][i],
            temperature_max=daily["temperature_2m_max"][i],
            temperature_min=daily["temperature_2m_min"][i],
            precipitation_mm=daily["precipitation_sum"][i],
            wind_speed_max=daily["wind_speed_10m_max"][i],
            temperature_unit=temp_symbol,
        )
        for i in range(len(daily["time"]))
    ]

    location_str = f"{city}, {country}" if city else f"{latitude:.2f}, {longitude:.2f}"

    return WeatherResponse(
        location=location_str,
        latitude=data["latitude"],
        longitude=data["longitude"],
        timezone=data.get("timezone", ""),
        current=current,
        daily_forecast=forecast,
    )
