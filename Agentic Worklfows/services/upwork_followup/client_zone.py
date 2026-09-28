"""The client's time zone for Upwork call times (U3 drafts).

    from services.upwork_followup import client_zone
    zone, source = client_zone.resolve(room)      # (ZoneInfo, "location" | "timezone" | "default")
    client_zone.label(dt, zone)                   # "ET", "CT", "MT", "PT", "BST", "Bogota time"

Where the location comes from (no new API call): the collector already reads
each job folder's ``jd.txt``, whose summary line (Lorenzo's own, written from
the job page) says where the client is: "Client in Virginia, US
(America/New_York).", "Client in Nevada (US), timezone Chicago.", "Client
timezone Europe/Berlin, country not shown." ``collect.parse_jd`` keeps those
sentences as ``job["client_location"]``. A room may also carry
``client_timezone`` (an IANA name) or ``client_location`` directly, for when
the room or proposal pull starts returning one; those are read first.

Order (the rule says "the client's location"):
1. a place in the location text: a US state or big US city, a Canadian
   province, an Australian state, a big world city, or a country with one
   main zone;
2. a stated time zone: an IANA name ("America/New_York") or a zone city
   ("timezone Bogota", "timezone Sao Paulo");
3. Central time.
A location wins over a conflicting account time zone ("Client in California
(US), timezone America/New_York" is PT): Upwork account zones are often left
at a default. The United States, Canada and Australia with no state named are
not places here; they fall through to step 2, then CT.
"""
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

try:  # Python 3.9+
    from zoneinfo import ZoneInfo, available_timezones
except ImportError:  # pragma: no cover - the engine runs on 3.9
    from backports.zoneinfo import ZoneInfo, available_timezones  # type: ignore

CENTRAL = "America/Chicago"
DEFAULT_SOURCE = "default"

# North American zones get the short US labels.
_LABELS = {
    "America/New_York": "ET", "America/Detroit": "ET", "America/Toronto": "ET", "America/Montreal": "ET",
    "America/Indiana/Indianapolis": "ET", "America/Kentucky/Louisville": "ET",
    "America/Chicago": "CT", "America/Winnipeg": "CT", "America/Regina": "CT",
    "America/Denver": "MT", "America/Boise": "MT", "America/Edmonton": "MT", "America/Phoenix": "MT",
    "America/Los_Angeles": "PT", "America/Vancouver": "PT", "America/Halifax": "AT",
    "Asia/Kolkata": "IST",
}
# Abbreviations that name one zone only. Anything else ("PST" is also
# Manila, "CST" also Shanghai, "IST" also Dublin and Jerusalem, "+04" is a
# number) is written as "<city> time".
_CLEAR_ABBRS = {"BST", "GMT", "CET", "CEST", "EET", "EEST", "WET", "WEST", "MSK", "AEST", "AEDT", "ACST",
                "ACDT", "AWST", "NZST", "NZDT", "JST", "KST", "HKT", "PKT", "SAST", "WAT", "EAT", "HST",
                "AKST", "AKDT"}

_ET, _CT, _MT, _PT = "America/New_York", CENTRAL, "America/Denver", "America/Los_Angeles"

# US states (the zone most of the state is in) and DC.
_US_STATES = {
    "alabama": _CT, "alaska": "America/Anchorage", "arizona": "America/Phoenix", "arkansas": _CT,
    "california": _PT, "colorado": _MT, "connecticut": _ET, "delaware": _ET, "florida": _ET, "georgia": _ET,
    "hawaii": "Pacific/Honolulu", "idaho": _MT, "illinois": _CT, "indiana": _ET, "iowa": _CT, "kansas": _CT,
    "kentucky": _ET, "louisiana": _CT, "maine": _ET, "maryland": _ET, "massachusetts": _ET, "michigan": _ET,
    "minnesota": _CT, "mississippi": _CT, "missouri": _CT, "montana": _MT, "nebraska": _CT, "nevada": _PT,
    "new hampshire": _ET, "new jersey": _ET, "new mexico": _MT, "new york": _ET, "north carolina": _ET,
    "north dakota": _CT, "ohio": _ET, "oklahoma": _CT, "oregon": _PT, "pennsylvania": _ET,
    "rhode island": _ET, "south carolina": _ET, "south dakota": _CT, "tennessee": _CT, "texas": _CT,
    "utah": _MT, "vermont": _ET, "virginia": _ET, "washington": _PT, "west virginia": _ET,
    "wisconsin": _CT, "wyoming": _MT, "district of columbia": _ET, "washington dc": _ET,
    "washington d.c.": _ET, "puerto rico": "America/Puerto_Rico",
}
_US_ABBR = {
    "AL": _CT, "AK": "America/Anchorage", "AZ": "America/Phoenix", "AR": _CT, "CA": _PT, "CO": _MT,
    "CT": _ET, "DE": _ET, "FL": _ET, "GA": _ET, "HI": "Pacific/Honolulu", "ID": _MT, "IL": _CT, "IN": _ET,
    "IA": _CT, "KS": _CT, "KY": _ET, "LA": _CT, "ME": _ET, "MD": _ET, "MA": _ET, "MI": _ET, "MN": _CT,
    "MS": _CT, "MO": _CT, "MT": _MT, "NE": _CT, "NV": _PT, "NH": _ET, "NJ": _ET, "NM": _MT, "NY": _ET,
    "NC": _ET, "ND": _CT, "OH": _ET, "OK": _CT, "OR": _PT, "PA": _ET, "RI": _ET, "SC": _ET, "SD": _CT,
    "TN": _CT, "TX": _CT, "UT": _MT, "VT": _ET, "VA": _ET, "WA": _PT, "WV": _ET, "WI": _CT, "WY": _MT,
    "DC": _ET,
}
# Big US cities.
_US_CITIES = {
    "new york city": _ET, "nyc": _ET, "brooklyn": _ET, "boston": _ET, "miami": _ET, "atlanta": _ET,
    "philadelphia": _ET, "orlando": _ET, "tampa": _ET, "charlotte": _ET, "houston": _CT, "dallas": _CT,
    "austin": _CT, "san antonio": _CT, "nashville": _CT, "minneapolis": _CT, "st. louis": _CT,
    "kansas city": _CT, "salt lake city": _MT, "las vegas": _PT, "seattle": _PT, "portland": _PT,
    "san francisco": _PT, "san diego": _PT, "san jose": _PT, "sacramento": _PT, "chicago": _CT,
    "denver": _MT, "phoenix": "America/Phoenix", "los angeles": _PT, "detroit": _ET,
}
# Big cities elsewhere (a place, so they are read before "timezone").
_WORLD_CITIES = {
    "london": "Europe/London", "manchester": "Europe/London", "dublin": "Europe/Dublin",
    "paris": "Europe/Paris", "berlin": "Europe/Berlin", "munich": "Europe/Berlin",
    "amsterdam": "Europe/Amsterdam", "madrid": "Europe/Madrid", "barcelona": "Europe/Madrid",
    "lisbon": "Europe/Lisbon", "rome": "Europe/Rome", "milan": "Europe/Rome", "zurich": "Europe/Zurich",
    "vienna": "Europe/Vienna", "stockholm": "Europe/Stockholm", "warsaw": "Europe/Warsaw",
    "kyiv": "Europe/Kiev", "kiev": "Europe/Kiev", "istanbul": "Europe/Istanbul", "tel aviv": "Asia/Jerusalem",
    "dubai": "Asia/Dubai", "abu dhabi": "Asia/Dubai", "riyadh": "Asia/Riyadh", "doha": "Asia/Qatar",
    "cairo": "Africa/Cairo", "lagos": "Africa/Lagos", "nairobi": "Africa/Nairobi",
    "johannesburg": "Africa/Johannesburg", "cape town": "Africa/Johannesburg", "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata", "bangalore": "Asia/Kolkata", "bengaluru": "Asia/Kolkata",
    "karachi": "Asia/Karachi", "lahore": "Asia/Karachi", "dhaka": "Asia/Dhaka", "manila": "Asia/Manila",
    "kuala lumpur": "Asia/Kuala_Lumpur", "jakarta": "Asia/Jakarta", "bangkok": "Asia/Bangkok",
    "ho chi minh city": "Asia/Ho_Chi_Minh", "tokyo": "Asia/Tokyo", "seoul": "Asia/Seoul",
    "shanghai": "Asia/Shanghai", "beijing": "Asia/Shanghai", "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne", "brisbane": "Australia/Brisbane", "perth": "Australia/Perth",
    "adelaide": "Australia/Adelaide", "auckland": "Pacific/Auckland", "toronto": "America/Toronto",
    "montreal": "America/Toronto", "ottawa": "America/Toronto", "vancouver": "America/Vancouver",
    "calgary": "America/Edmonton", "edmonton": "America/Edmonton", "winnipeg": "America/Winnipeg",
    "halifax": "America/Halifax", "mexico city": "America/Mexico_City", "bogota": "America/Bogota",
    "lima": "America/Lima", "santiago": "America/Santiago", "buenos aires": "America/Argentina/Buenos_Aires",
    "sao paulo": "America/Sao_Paulo", "rio de janeiro": "America/Sao_Paulo",
}
_OTHER_REGIONS = {
    "ontario": "America/Toronto", "quebec": "America/Toronto", "british columbia": "America/Vancouver",
    "alberta": "America/Edmonton", "manitoba": "America/Winnipeg", "saskatchewan": "America/Regina",
    "nova scotia": "America/Halifax", "new brunswick": "America/Halifax",
    "new south wales": "Australia/Sydney", "victoria, australia": "Australia/Melbourne",
    "queensland": "Australia/Brisbane", "western australia": "Australia/Perth",
    "south australia": "Australia/Adelaide", "tasmania": "Australia/Hobart",
    "england": "Europe/London", "scotland": "Europe/London", "wales": "Europe/London",
}
# Countries with one main zone. Several spellings of the same country.
_COUNTRIES = {
    "united kingdom": "Europe/London", "uk": "Europe/London", "great britain": "Europe/London",
    "ireland": "Europe/Dublin", "germany": "Europe/Berlin", "france": "Europe/Paris", "spain": "Europe/Madrid",
    "italy": "Europe/Rome", "netherlands": "Europe/Amsterdam", "belgium": "Europe/Brussels",
    "switzerland": "Europe/Zurich", "austria": "Europe/Vienna", "sweden": "Europe/Stockholm",
    "norway": "Europe/Oslo", "denmark": "Europe/Copenhagen", "finland": "Europe/Helsinki",
    "poland": "Europe/Warsaw", "portugal": "Europe/Lisbon", "greece": "Europe/Athens",
    "ukraine": "Europe/Kiev", "moldova": "Europe/Chisinau", "romania": "Europe/Bucharest", "czech republic": "Europe/Prague",
    "czechia": "Europe/Prague", "hungary": "Europe/Budapest", "turkey": "Europe/Istanbul",
    "israel": "Asia/Jerusalem", "united arab emirates": "Asia/Dubai", "uae": "Asia/Dubai",
    "saudi arabia": "Asia/Riyadh", "qatar": "Asia/Qatar", "egypt": "Africa/Cairo", "nigeria": "Africa/Lagos",
    "kenya": "Africa/Nairobi", "south africa": "Africa/Johannesburg", "india": "Asia/Kolkata",
    "pakistan": "Asia/Karachi", "bangladesh": "Asia/Dhaka", "philippines": "Asia/Manila",
    "singapore": "Asia/Singapore", "malaysia": "Asia/Kuala_Lumpur", "vietnam": "Asia/Ho_Chi_Minh",
    "thailand": "Asia/Bangkok", "hong kong": "Asia/Hong_Kong", "japan": "Asia/Tokyo",
    "south korea": "Asia/Seoul", "china": "Asia/Shanghai", "new zealand": "Pacific/Auckland",
    "mexico": "America/Mexico_City", "colombia": "America/Bogota", "peru": "America/Lima",
    "chile": "America/Santiago", "argentina": "America/Argentina/Buenos_Aires", "brazil": "America/Sao_Paulo",
    "jamaica": "America/Jamaica",
}
_PLACES = dict(_WORLD_CITIES)
_PLACES.update(_US_CITIES)
_PLACES.update(_OTHER_REGIONS)
_PLACES.update(_US_STATES)
_PLACES.update(_COUNTRIES)
# Longest first, so "west virginia" wins over "virginia", "new york city" over "new york".
_PLACE_NAMES = sorted(_PLACES, key=len, reverse=True)

_TZ_SPLIT_RE = re.compile(r"\b(?:account\s+)?time\s?zone\b", re.I)
_IANA_RE = re.compile(r"\b([A-Z][A-Za-z_]+(?:/[A-Z][A-Za-z_\-]+){1,2})\b")
_ABBR_RE = re.compile(r"(?:,|\()\s*([A-Z]{2})\b")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z_ ]*[A-Za-z]")

_CITY_ZONES = None  # type: Optional[Dict[str, str]]
# Zone "cities" that are ordinary words in a sentence, never a place here.
_NOT_CITIES = {"center", "general", "universal", "zulu", "greenwich", "uct", "utc", "gmt", "south", "north",
               "west", "east", "acre", "continental"}


def _zone(name: str) -> Optional[ZoneInfo]:
    for candidate in (name, {"Europe/Kiev": "Europe/Kyiv", "Europe/Kyiv": "Europe/Kiev"}.get(name)):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except Exception:  # noqa: BLE001 - an unknown or malformed name is simply not a zone
            continue
    return None


def _city_zones() -> Dict[str, str]:
    """'sao paulo' -> 'America/Sao_Paulo', from the zone names themselves."""
    global _CITY_ZONES
    if _CITY_ZONES is None:
        out = {}  # type: Dict[str, str]
        for name in sorted(available_timezones()):
            if "/" not in name or name.startswith(("Etc/", "SystemV/", "posix/", "right/")):
                continue
            city = name.rsplit("/", 1)[1].replace("_", " ").lower()
            if city not in _NOT_CITIES:
                out.setdefault(city, name)
        _CITY_ZONES = out
    return _CITY_ZONES


def _find_place(text: str) -> Optional[str]:
    low = " " + re.sub(r"\s+", " ", text.lower()) + " "
    for name in _PLACE_NAMES:
        if re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(name), low):
            return _PLACES[name]
    abbr = _ABBR_RE.search(text)
    if abbr and abbr.group(1) in _US_ABBR:
        return _US_ABBR[abbr.group(1)]
    return None


def _find_iana(text: str) -> Optional[str]:
    for m in _IANA_RE.finditer(text):
        if _zone(m.group(1)):
            return m.group(1)
    return None


def _find_stated_zone(text: str) -> Optional[str]:
    """An IANA name, else a zone city ("Bogota", "Sao Paulo") in the text
    after "timezone"."""
    iana = _find_iana(text)
    if iana:
        return iana
    cities = _city_zones()
    for m in _WORD_RE.finditer(text):
        words = m.group(0).lower().split()
        # the longest run of words that names a zone city ("sao paulo", "new york")
        for size in range(min(3, len(words)), 0, -1):
            for i in range(0, len(words) - size + 1):
                name = cities.get(" ".join(words[i:i + size]))
                if name:
                    return name
    return None


def resolve_text(location: str) -> Tuple[Optional[str], str]:
    """Location text -> (IANA name or None, source)."""
    text = location or ""
    parts = _TZ_SPLIT_RE.split(text)
    place_text, stated_text = parts[0], " ".join(parts[1:])
    # "Client in the US (America/New_York)": the bracket is a stated zone, not a place.
    place_only = re.sub(r"\([^)]*/[^)]*\)", " ", place_text)
    place = _find_place(place_only)
    if place and _zone(place):
        return place, "location"
    # Zone cities are only read after the word "timezone"; before it, only a
    # full IANA name counts ("Client in the US (America/New_York)").
    stated = _find_stated_zone(stated_text) or _find_iana(place_text)
    if stated:
        return stated, "timezone"
    return None, DEFAULT_SOURCE


def resolve(room: Optional[Dict[str, Any]]) -> Tuple[ZoneInfo, str]:
    """The client's zone for a collected room, and where it came from."""
    room = room or {}
    explicit = room.get("client_timezone")
    if isinstance(explicit, str) and "/" in explicit and _zone(explicit.strip()):
        return _zone(explicit.strip()), "timezone"  # type: ignore[return-value]
    texts = [room.get("client_location")]
    job = room.get("job")
    if isinstance(job, dict):
        texts.append(job.get("client_location"))
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            continue
        name, source = resolve_text(text)
        zone = _zone(name) if name else None
        if zone is not None:
            return zone, source
    return ZoneInfo(CENTRAL), DEFAULT_SOURCE


def label(dt: datetime, zone: ZoneInfo) -> str:
    """The zone label a client reads: ET, CT, MT or PT for North America,
    the zone's own abbreviation elsewhere when it names only that zone (BST,
    CEST, AEST, IST for India), else "<city> time" ("Bogota time", "Manila
    time")."""
    key = getattr(zone, "key", "") or ""
    if key in _LABELS:
        return _LABELS[key]
    abbr = dt.astimezone(zone).strftime("%Z")
    if abbr in _CLEAR_ABBRS:
        return abbr
    city = key.rsplit("/", 1)[-1].replace("_", " ") if key else "local"
    return "%s time" % city
