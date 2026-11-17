"""Best-effort geography enrichment. Cricsheet has no venue country, so it is inferred from a curated city list.
Venues that cannot be mapped keep a NULL country and are reported as unknown rather than guessed."""
import re
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

_CITIES: dict[str, tuple[str, ...]] = {
    "India": ("mumbai", "delhi", "new delhi", "kolkata", "chennai", "bengaluru", "bangalore", "hyderabad", "ahmedabad", "pune", "mohali",
              "chandigarh", "dharamsala", "dharamshala", "jaipur", "nagpur", "rajkot", "ranchi", "visakhapatnam", "indore", "lucknow",
              "guwahati", "kanpur", "cuttack", "raipur", "thiruvananthapuram", "kochi", "bhubaneswar", "surat", "vadodara"),
    "Australia": ("melbourne", "sydney", "perth", "adelaide", "brisbane", "hobart", "canberra", "geelong", "launceston", "darwin",
                  "cairns", "townsville", "gold coast", "carrara", "mackay", "alice springs", "bellerive"),
    "England": ("london", "birmingham", "manchester", "leeds", "nottingham", "southampton", "cardiff", "chester-le-street", "durham",
                "bristol", "taunton", "chelmsford", "canterbury", "hove", "worcester", "northampton", "derby", "leicester", "headingley",
                "edgbaston", "lord's", "old trafford", "trent bridge", "the oval", "kennington"),
    "South Africa": ("johannesburg", "cape town", "durban", "centurion", "pretoria", "port elizabeth", "gqeberha", "bloemfontein",
                     "east london", "paarl", "potchefstroom", "kimberley", "benoni", "newlands", "wanderers"),
    "New Zealand": ("auckland", "wellington", "christchurch", "hamilton", "dunedin", "napier", "mount maunganui", "nelson", "queenstown",
                    "whangarei", "lincoln"),
    "Pakistan": ("karachi", "lahore", "rawalpindi", "islamabad", "multan", "faisalabad", "peshawar", "sialkot", "abbottabad"),
    "Sri Lanka": ("colombo", "kandy", "galle", "hambantota", "dambulla", "pallekele", "moratuwa", "kurunegala"),
    "Bangladesh": ("dhaka", "chattogram", "chittagong", "mirpur", "khulna", "sylhet", "bogra", "fatullah", "rajshahi"),
    "West Indies": ("bridgetown", "kingston", "port of spain", "gros islet", "st lucia", "saint lucia", "st john's", "antigua", "providence",
                    "georgetown", "basseterre", "st kitts", "roseau", "dominica", "kingstown", "st vincent", "st george's", "grenada",
                    "tarouba", "north sound", "trinidad", "barbados", "jamaica", "guyana", "coolidge", "brian lara"),
    "Zimbabwe": ("harare", "bulawayo", "kwekwe", "mutare"),
    "United Arab Emirates": ("dubai", "abu dhabi", "sharjah", "ajman"),
    "Ireland": ("dublin", "malahide", "belfast", "bready", "clontarf", "stormont"),
    "Scotland": ("edinburgh", "glasgow", "aberdeen", "grange"),
    "Netherlands": ("amstelveen", "rotterdam", "the hague", "deventer"),
    "Afghanistan": ("kabul", "kandahar", "khost"),
    "United States of America": ("lauderhill", "houston", "dallas", "new york", "nassau county", "morrisville", "grand prairie", "los angeles"),
    "Canada": ("toronto", "king city", "brampton"),
    "Kenya": ("nairobi", "mombasa"),
    "Oman": ("muscat", "al amerat"),
    "Nepal": ("kathmandu", "kirtipur"),
    "Namibia": ("windhoek",),
    "Singapore": ("singapore",),
    "Malaysia": ("kuala lumpur", "bayuemas", "selangor"),
    "Hong Kong": ("hong kong", "mong kok", "kowloon"),
    "Papua New Guinea": ("port moresby",),
    "Uganda": ("kampala", "entebbe"),
    "Qatar": ("doha",),
    "Bermuda": ("bermuda"),
}
_INDEX = sorted(((c, country) for country, cities in _CITIES.items() for c in cities), key=lambda x: -len(x[0]))
_SUFFIXES = re.compile(r"\s+(women|men|a|under-?\s?\d+s?|xi)$", re.IGNORECASE)


def infer_venue_country(city: str | None, venue_name: str | None) -> str | None:
    c = (city or "").strip().lower()
    for key, country in _INDEX:
        if key == c:
            return country
    haystack = f"{c} {(venue_name or '').lower()}"
    for key, country in _INDEX:
        if re.search(rf"\b{re.escape(key)}\b", haystack):
            return country
    return None


def team_country(name: str, team_type: str | None) -> str | None:
    """Only national sides have a home country; club/franchise teams stay unknown."""
    if team_type != "international":
        return None
    return _SUFFIXES.sub("", name.strip()) or None


def backfill_geography(session: Session) -> tuple[int, int]:
    from app.cricket.models import Team, Venue

    venues = teams = 0
    for v in session.scalars(select(Venue).where(Venue.country.is_(None))):
        if country := infer_venue_country(v.city, v.name):
            v.country, venues = country, venues + 1
    for t in session.scalars(select(Team).where(Team.country.is_(None), Team.team_type == "international")):
        if country := team_country(t.name, t.team_type):
            t.country, teams = country, teams + 1
    session.commit()
    return venues, teams


def main() -> int:
    from app.database.session import get_engine

    with Session(get_engine()) as session:
        v, t = backfill_geography(session)
    print(f"venues updated={v} teams updated={t}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
