"""The client's time zone for Upwork call times (U3 drafts).

    from services.upwork_followup import client_zone
    zone, source = client_zone.resolve(room)      # (ZoneInfo, "location" | "timezone" | "default")
    client_zone.label(dt, zone)                   # "ET", "CT", "MT", "PT", "BST", "Bogota time", "Arizona time"

Where the location comes from (no new API call): the collector already reads
each job folder's ``jd.txt``, whose summary line (Lorenzo's own, written from
the job page) says where the client is: "Client in Virginia, US
(America/New_York).", "Client in Nevada (US), timezone Chicago.", "Client
timezone Europe/Berlin, country not shown." ``collect.parse_jd`` keeps those
sentences as ``job["client_location"]``. A room may also carry
``client_timezone`` (an IANA name) or ``client_location`` directly, for when
the room or proposal pull starts returning one.

Order (the rule says "the client's location"):
1. the place stated first, right after "Client in": the comma-separated
   pieces that follow, up to the first one that is not a place ("Ohio, US,
   a staffing agency that hires from the Philippines" reads "Ohio, US").
   Within them a US state, DC (with or without commas and periods) or a
   two-letter state code wins over any city ("Paris, TX", "Dublin, Ohio");
   a US marker (US, USA, United States) keeps US places only; else a
   province or other region, else the first city or one-zone country in the
   country named. An IANA zone in brackets in the same sentence wins when it
   is in the same country ("Client in Indiana, US (America/Chicago)");
2. a zone the room states (``client_timezone``);
3. a zone the text states: an IANA name ("America/New_York") or a zone city
   after "timezone" ("timezone Bogota", "timezone Sao Paulo");
4. Central time.
A location wins over a conflicting account time zone ("Client in California
(US), timezone America/New_York" is PT): Upwork account zones are often left
at a default. The United States, Canada and Australia with no state named are
not places here; they fall through to step 2, then CT.
"""
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
    "America/Chicago": "CT", "America/Winnipeg": "CT",
    "America/Denver": "MT", "America/Boise": "MT", "America/Edmonton": "MT",
    "America/Los_Angeles": "PT", "America/Vancouver": "PT", "America/Halifax": "AT",
    "Asia/Kolkata": "IST",
    # No DST: from March to November these match PT and MT, not MT and CT,
    # so they never borrow a DST region's label.
    "America/Phoenix": "Arizona time", "America/Regina": "Saskatchewan time",
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
_PLACE_NAME_RE = re.compile(r"(?<![a-z])(%s)(?![a-z])" % "|".join(re.escape(n) for n in _PLACE_NAMES))
# Country markers with no single zone: "US" says the place is in the US
# (so US places win), "Canada" and "Australia" likewise for theirs.
_COUNTRY_MARKERS = {"us": "US", "usa": "US", "united states": "US", "united states of america": "US",
                    "canada": "CA", "australia": "AU"}
_MARKER_RE = re.compile(r"(?<![a-z])(%s)(?![a-z])" % "|".join(
    re.escape(n) for n in sorted(_COUNTRY_MARKERS, key=len, reverse=True)))
# Words that may sit around a place name in a location ("South Florida",
# "Greater London", "Toronto area").
_QUALIFIERS = {"the", "south", "north", "east", "west", "southern", "northern", "eastern", "western",
               "central", "greater", "metro", "upstate", "downtown", "area", "region", "state", "city",
               "province", "county", "of"}
_CONNECTORS = {"of", "and", "de", "del", "la", "da", "do", "the"}

_TZ_SPLIT_RE = re.compile(r"\b(?:account\s+)?time\s?zone\b", re.I)
_IANA_RE = re.compile(r"\b([A-Z][A-Za-z_]+(?:/[A-Z][A-Za-z_\-]+){1,2})\b")
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


_US_ZONES = set(_US_STATES.values()) | set(_US_ABBR.values()) | set(_US_CITIES.values()) | {
    "America/Detroit", "America/Boise", "America/Juneau", "America/Adak"}
_CA_ZONES = {"America/Toronto", "America/Montreal", "America/Vancouver", "America/Edmonton",
             "America/Winnipeg", "America/Regina", "America/Halifax", "America/St_Johns", "America/Moncton",
             "America/Whitehorse", "America/Yellowknife", "America/Iqaluit", "America/Glace_Bay",
             "America/Goose_Bay", "America/Swift_Current", "America/Dawson_Creek", "America/Creston",
             "America/Fort_Nelson", "America/Dawson", "America/Rankin_Inlet", "America/Resolute",
             "America/Cambridge_Bay", "America/Inuvik", "America/Atikokan", "America/Nipigon",
             "America/Thunder_Bay", "America/Rainy_River", "America/Pangnirtung", "America/Blanc-Sablon"}


def _zone_country(key: str) -> str:
    """'US', 'CA', 'AU' or 'GB' for zones of those countries, else the zone
    name itself (the other countries here have one main zone)."""
    if key in _US_ZONES or key.startswith(("US/", "America/Indiana/", "America/Kentucky/",
                                           "America/North_Dakota/")):
        return "US"
    if key in _CA_ZONES or key.startswith("Canada/"):
        return "CA"
    if key.startswith(("Australia/", "Antarctica/Macquarie")):
        return "AU"
    if key in ("Europe/London", "GB"):
        return "GB"
    return key


class _Place(object):
    """One place named in a location: its zone (None for a country marker
    like "US"), its country and its kind ("state" for a US state, DC or a
    two-letter state code, "region" for a province or other country's state,
    "city", "country" or "marker")."""

    def __init__(self, zone: Optional[str], country: str, kind: str) -> None:
        self.zone, self.country, self.kind = zone, country, kind


def _place_for_name(name: str) -> _Place:
    zone = _PLACES[name]
    if name in _US_STATES:
        return _Place(zone, "US", "state")
    if name in _OTHER_REGIONS:
        return _Place(zone, _zone_country(zone), "region")
    if name in _COUNTRIES:
        return _Place(zone, _zone_country(zone), "country")
    return _Place(zone, _zone_country(zone), "city")


def _segment_places(seg: str) -> Optional[List[_Place]]:
    """The places in one comma-separated piece of a location, in order, or
    None when the piece is not a location (a description such as "a staffing
    agency that hires from the Philippines"): that ends the location."""
    low = re.sub(r"\s+", " ", seg.lower()).strip()
    low = re.sub(r"^the ", "", low)
    if low in _COUNTRY_MARKERS:
        return [_Place(None, _COUNTRY_MARKERS[low], "marker")]
    if low in _PLACES:
        return [_place_for_name(low)]
    if seg in _US_ABBR:
        return [_Place(_US_ABBR[seg], "US", "state")]
    found = []  # type: List[Tuple[int, _Place]]
    rest = low
    for m in _PLACE_NAME_RE.finditer(low):
        found.append((m.start(), _place_for_name(m.group(1))))
        rest = rest.replace(m.group(1), " ", 1)
    for m in _MARKER_RE.finditer(rest):
        found.append((low.find(m.group(1)), _Place(None, _COUNTRY_MARKERS[m.group(1)], "marker")))
        rest = rest.replace(m.group(1), " ", 1)
    for m in re.finditer(r"\b([A-Z]{2})\b", seg):
        if m.group(1) in _US_ABBR:
            found.append((m.start(), _Place(_US_ABBR[m.group(1)], "US", "state")))
            rest = re.sub(r"(?<![a-z])%s(?![a-z])" % m.group(1).lower(), " ", rest, count=1)
    found.sort(key=lambda item: item[0])
    places = [p for _pos, p in found]
    leftover = [w for w in re.split(r"[\s.]+", rest) if w]
    if places and all(w in _QUALIFIERS for w in leftover):
        return places
    words = seg.split()
    if 1 <= len(words) <= 4 and words[0][:1].isupper() and all(
            w[:1].isupper() or w.lower() in _CONNECTORS for w in words):
        return places          # a name ("Punjab"), maybe with a known place in it
    return None


def _choose(places: List[_Place]) -> Optional[_Place]:
    """The zone-bearing place a location means. A US marker ("US", "USA",
    "United States") keeps US places only. A US state or code wins over any
    city ("Paris, TX", "Dublin, Ohio"), then a province or other region.
    Otherwise the first place, in the country the location names when it
    names one ("London, Canada" is no place)."""
    zoned = [p for p in places if p.zone]
    if any(p.kind == "marker" and p.country == "US" for p in places):
        zoned = [p for p in zoned if p.country == "US"]
    for kind in ("state", "region"):
        for p in zoned:
            if p.kind == kind:
                return p
    countries = [p.country for p in places if p.kind in ("marker", "country")]
    if countries:
        zoned = [p for p in zoned if p.country == countries[0]]
    return zoned[0] if zoned else None


_DC_RE = re.compile(r"\bwashington\s*,?\s*d\.?\s*c\b\.?", re.I)
_DC_ALONE_RE = re.compile(r"(?<![A-Za-z])d\.\s?c\b\.?", re.I)
_US_DOTS_RE = re.compile(r"(?<![A-Za-z])u\.\s?s\.?(\s?a\b\.?)?", re.I)
_ANCHOR_RE = re.compile(r"\b(?:client\s+(?:is\s+)?(?:in|from|based\s+in|located\s+in)|based\s+in|located\s+in)\b",
                        re.I)
_PAREN_RE = re.compile(r"\(([^)]*)\)")


def _location_place(place_text: str) -> Tuple[Optional[_Place], Optional[str]]:
    """(the place stated first, right after "Client in", or None; the IANA
    zone written in brackets in the same sentence, or None)."""
    paren = None  # type: Optional[str]

    def drop_iana(m: Any) -> str:
        nonlocal paren
        iana = _find_iana(m.group(1))
        if iana:
            paren = paren or iana
            return ", "
        return ", %s, " % m.group(1)

    text = _PAREN_RE.sub(drop_iana, place_text)
    text = _DC_RE.sub("Washington DC", text)
    text = _DC_ALONE_RE.sub("DC", text)
    text = _US_DOTS_RE.sub(lambda m: "USA" if m.group(1) else "US", text)
    anchor = _ANCHOR_RE.search(text)
    if anchor:
        text = text[anchor.end():]
    elif re.match(r"\s*(?:client|account)\b", text, re.I):
        return None, paren             # "Client timezone ...": no place stated
    places = []  # type: List[_Place]
    for seg in re.split(r"[,(]", text.replace(")", ",")):
        seg = seg.strip(" .:")
        if not seg:
            continue
        found = _segment_places(seg)
        if found is None:
            break
        places.extend(found)
    return _choose(places), paren


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


def _resolve_parts(location: str) -> Tuple[Optional[str], Optional[str]]:
    """Location text -> (the zone of the place it states, or None; a stated
    zone, or None). A stated IANA zone in brackets beside the place wins
    when it is in the same country ("Client in Virginia, US
    (America/New_York)"); an account time zone after "timezone" never
    overrides a place."""
    place = None  # type: Optional[str]
    stated = None  # type: Optional[str]
    for sentence in (location or "").split(";"):
        parts = _TZ_SPLIT_RE.split(sentence)
        place_text, stated_text = parts[0], " ".join(parts[1:])
        if place is None:
            found, paren = _location_place(place_text)
            if found is not None and found.zone and _zone(found.zone):
                place = paren if paren and _zone_country(paren) == found.country else found.zone
        if stated is None:
            # Zone cities are only read after the word "timezone"; before it,
            # only a full IANA name counts ("Client in the US (America/New_York)").
            stated = _find_stated_zone(stated_text) or _find_iana(place_text)
    return place, stated


def resolve_text(location: str) -> Tuple[Optional[str], str]:
    """Location text -> (IANA name or None, source)."""
    place, stated = _resolve_parts(location)
    if place:
        return place, "location"
    if stated:
        return stated, "timezone"
    return None, DEFAULT_SOURCE


def resolve(room: Optional[Dict[str, Any]]) -> Tuple[ZoneInfo, str]:
    """The client's zone for a collected room, and where it came from: a
    place in the room's or the job's location text first, then a zone the
    room states (``client_timezone``), then a zone the location text states,
    then Central."""
    room = room or {}
    texts = [room.get("client_location")]
    job = room.get("job")
    if isinstance(job, dict):
        texts.append(job.get("client_location"))
    parsed = [_resolve_parts(t) for t in texts if isinstance(t, str) and t.strip()]
    for place, _stated in parsed:
        if place and _zone(place):
            return _zone(place), "location"  # type: ignore[return-value]
    explicit = room.get("client_timezone")
    if isinstance(explicit, str) and "/" in explicit and _zone(explicit.strip()):
        return _zone(explicit.strip()), "timezone"  # type: ignore[return-value]
    for _place, stated in parsed:
        if stated and _zone(stated):
            return _zone(stated), "timezone"  # type: ignore[return-value]
    return ZoneInfo(CENTRAL), DEFAULT_SOURCE


def label(dt: datetime, zone: ZoneInfo) -> str:
    """The zone label a client reads: ET, CT, MT or PT for North America
(Arizona and Saskatchewan, which keep no DST, get "Arizona time" and
"Saskatchewan time"),
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
