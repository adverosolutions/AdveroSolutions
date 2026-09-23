"""
US Cities & Metros for Lead Scraping
Comprehensive coverage: 350+ base cities + 600+ suburb/neighborhood subdivisions.
Targets every US metro with meaningful local service business density.
"""

US_METROS = [
    # === TOP 50 - Major metros ===
    ("New York", "NY"), ("Los Angeles", "CA"), ("Chicago", "IL"), ("Houston", "TX"),
    ("Phoenix", "AZ"), ("Philadelphia", "PA"), ("San Antonio", "TX"), ("San Diego", "CA"),
    ("Dallas", "TX"), ("San Jose", "CA"), ("Austin", "TX"), ("Jacksonville", "FL"),
    ("Fort Worth", "TX"), ("Columbus", "OH"), ("Charlotte", "NC"), ("Indianapolis", "IN"),
    ("San Francisco", "CA"), ("Seattle", "WA"), ("Denver", "CO"), ("Washington", "DC"),
    ("Nashville", "TN"), ("Oklahoma City", "OK"), ("El Paso", "TX"), ("Boston", "MA"),
    ("Portland", "OR"), ("Las Vegas", "NV"), ("Memphis", "TN"), ("Louisville", "KY"),
    ("Baltimore", "MD"), ("Milwaukee", "WI"), ("Albuquerque", "NM"), ("Tucson", "AZ"),
    ("Fresno", "CA"), ("Mesa", "AZ"), ("Sacramento", "CA"), ("Atlanta", "GA"),
    ("Kansas City", "MO"), ("Colorado Springs", "CO"), ("Omaha", "NE"), ("Raleigh", "NC"),
    ("Long Beach", "CA"), ("Virginia Beach", "VA"), ("Miami", "FL"), ("Oakland", "CA"),
    ("Minneapolis", "MN"), ("Tampa", "FL"), ("Tulsa", "OK"), ("Arlington", "TX"),
    ("New Orleans", "LA"), ("Wichita", "KS"),

    # === 51-100 - Mid-major metros ===
    ("Cleveland", "OH"), ("Bakersfield", "CA"), ("Aurora", "CO"), ("Anaheim", "CA"),
    ("Honolulu", "HI"), ("Santa Ana", "CA"), ("Riverside", "CA"), ("Corpus Christi", "TX"),
    ("Lexington", "KY"), ("Stockton", "CA"), ("St. Louis", "MO"), ("Pittsburgh", "PA"),
    ("Cincinnati", "OH"), ("Henderson", "NV"), ("Greensboro", "NC"),
    ("Plano", "TX"), ("Newark", "NJ"), ("Lincoln", "NE"), ("Orlando", "FL"),
    ("Irvine", "CA"), ("Toledo", "OH"), ("Jersey City", "NJ"), ("Chula Vista", "CA"),
    ("Durham", "NC"), ("Laredo", "TX"), ("Madison", "WI"), ("Gilbert", "AZ"),
    ("Lubbock", "TX"), ("St. Petersburg", "FL"), ("Norfolk", "VA"), ("Reno", "NV"),
    ("Winston-Salem", "NC"), ("Glendale", "AZ"), ("Hialeah", "FL"), ("Garland", "TX"),
    ("Scottsdale", "AZ"), ("Irving", "TX"), ("Chesapeake", "VA"), ("North Las Vegas", "NV"),
    ("Fremont", "CA"), ("Baton Rouge", "LA"), ("Richmond", "VA"), ("Boise", "ID"),
    ("San Bernardino", "CA"), ("Spokane", "WA"), ("Des Moines", "IA"), ("Birmingham", "AL"),
    ("Modesto", "CA"), ("Rochester", "NY"),

    # === 101-150 - Growing metros ===
    ("Fontana", "CA"), ("Moreno Valley", "CA"), ("Fayetteville", "NC"), ("Tacoma", "WA"),
    ("Oxnard", "CA"), ("Knoxville", "TN"), ("Salt Lake City", "UT"), ("McAllen", "TX"),
    ("Huntsville", "AL"), ("Tallahassee", "FL"), ("Worcester", "MA"), ("Grand Rapids", "MI"),
    ("Providence", "RI"), ("Newport News", "VA"), ("Brownsville", "TX"), ("Chattanooga", "TN"),
    ("Fort Lauderdale", "FL"), ("Tempe", "AZ"), ("Overland Park", "KS"), ("Cape Coral", "FL"),
    ("Sioux Falls", "SD"), ("Peoria", "AZ"), ("Ontario", "CA"), ("Jackson", "MS"),
    ("Elk Grove", "CA"), ("Springfield", "MO"), ("Pembroke Pines", "FL"), ("Salem", "OR"),
    ("Corona", "CA"), ("Eugene", "OR"), ("McKinney", "TX"), ("Garden Grove", "CA"),
    ("Fort Collins", "CO"), ("Cary", "NC"), ("Palmdale", "CA"), ("Hayward", "CA"),
    ("Frisco", "TX"), ("Springfield", "IL"), ("Pasadena", "TX"), ("Macon", "GA"),
    ("Alexandria", "VA"), ("Murfreesboro", "TN"), ("Pomona", "CA"), ("Lakewood", "CO"),
    ("Savannah", "GA"), ("Escondido", "CA"), ("Joliet", "IL"), ("Naperville", "IL"),
    ("Bridgeport", "CT"), ("Bellevue", "WA"),

    # === 151-200 - Secondary metros ===
    ("Surprise", "AZ"), ("Denton", "TX"), ("Roseville", "CA"), ("Thornton", "CO"),
    ("Paterson", "NJ"), ("Killeen", "TX"), ("Salinas", "CA"),
    ("Gainesville", "FL"), ("Dayton", "OH"), ("Columbia", "SC"), ("Waco", "TX"),
    ("Little Rock", "AR"), ("Charleston", "SC"), ("West Palm Beach", "FL"), ("Hampton", "VA"),
    ("Columbia", "MO"), ("Olathe", "KS"), ("Sterling Heights", "MI"), ("Cedar Rapids", "IA"),
    ("Stamford", "CT"), ("Visalia", "CA"), ("Elizabeth", "NJ"), ("Miramar", "FL"),
    ("Clarksville", "TN"), ("New Haven", "CT"), ("Topeka", "KS"), ("Thousand Oaks", "CA"),
    ("Concord", "CA"), ("Simi Valley", "CA"), ("Hartford", "CT"), ("Coral Springs", "FL"),
    ("Midland", "TX"), ("Meridian", "ID"), ("Vallejo", "CA"), ("Palm Bay", "FL"),
    ("Round Rock", "TX"), ("Lakeland", "FL"), ("Clearwater", "FL"), ("Beaumont", "TX"),
    ("Westminster", "CO"), ("West Jordan", "UT"), ("Arvada", "CO"), ("Wilmington", "NC"),
    ("Green Bay", "WI"), ("Centennial", "CO"), ("Daly City", "CA"), ("Sparks", "NV"),
    ("Pompano Beach", "FL"), ("Boulder", "CO"),

    # === 201-350 - Additional cities with strong local service demand ===
    # Florida (huge pest control + pool market)
    ("Naples", "FL"), ("Sarasota", "FL"), ("Ocala", "FL"), ("Pensacola", "FL"),
    ("Daytona Beach", "FL"), ("Port St. Lucie", "FL"), ("Deltona", "FL"),
    ("Melbourne", "FL"), ("Kissimmee", "FL"), ("Boynton Beach", "FL"),
    ("Deerfield Beach", "FL"), ("Plantation", "FL"), ("Sunrise", "FL"),
    ("Boca Raton", "FL"), ("Davie", "FL"), ("Coconut Creek", "FL"),
    ("Sanford", "FL"), ("Margate", "FL"), ("Tamarac", "FL"),
    ("Palm Coast", "FL"), ("Jupiter", "FL"), ("Wellington", "FL"),

    # Texas (massive market for all 4 industries)
    ("Amarillo", "TX"), ("Odessa", "TX"), ("Tyler", "TX"), ("Abilene", "TX"),
    ("College Station", "TX"), ("Edinburg", "TX"), ("Allen", "TX"),
    ("League City", "TX"), ("Temple", "TX"), ("Conroe", "TX"),
    ("New Braunfels", "TX"), ("Flower Mound", "TX"), ("Mansfield", "TX"),
    ("Cedar Park", "TX"), ("Pflugerville", "TX"), ("Georgetown", "TX"),
    ("Lewisville", "TX"), ("San Marcos", "TX"), ("Harlingen", "TX"),

    # California
    ("Rancho Cucamonga", "CA"), ("Santa Clarita", "CA"), ("Lancaster", "CA"),
    ("Victorville", "CA"), ("Santa Rosa", "CA"), ("Oceanside", "CA"),
    ("Carlsbad", "CA"), ("Murrieta", "CA"), ("Temecula", "CA"),
    ("Menifee", "CA"), ("Hemet", "CA"), ("Lake Elsinore", "CA"),
    ("San Clemente", "CA"), ("Indio", "CA"), ("Palm Desert", "CA"),
    ("Palm Springs", "CA"), ("Redding", "CA"), ("Chico", "CA"),
    ("Napa", "CA"), ("Vacaville", "CA"), ("Fairfield", "CA"),

    # Arizona (huge pool + pest control market)
    ("Chandler", "AZ"), ("Goodyear", "AZ"), ("Avondale", "AZ"),
    ("Maricopa", "AZ"), ("Buckeye", "AZ"), ("Casa Grande", "AZ"),
    ("Flagstaff", "AZ"), ("Yuma", "AZ"), ("Lake Havasu City", "AZ"),
    ("Prescott", "AZ"), ("Queen Creek", "AZ"), ("San Tan Valley", "AZ"),

    # Southeast
    ("Augusta", "GA"), ("Athens", "GA"), ("Warner Robins", "GA"), ("Valdosta", "GA"),
    ("Greenville", "SC"), ("Rock Hill", "SC"), ("Spartanburg", "SC"),
    ("Roanoke", "VA"), ("Lynchburg", "VA"), ("Charlottesville", "VA"),
    ("Mobile", "AL"), ("Montgomery", "AL"), ("Tuscaloosa", "AL"),
    ("Biloxi", "MS"), ("Hattiesburg", "MS"), ("Gulfport", "MS"),

    # Midwest
    ("Fort Wayne", "IN"), ("Evansville", "IN"), ("South Bend", "IN"),
    ("Ann Arbor", "MI"), ("Lansing", "MI"), ("Kalamazoo", "MI"), ("Flint", "MI"),
    ("Akron", "OH"), ("Canton", "OH"), ("Youngstown", "OH"),
    ("Springfield", "OH"), ("Kettering", "OH"),
    ("Rockford", "IL"), ("Peoria", "IL"), ("Champaign", "IL"), ("Bloomington", "IL"),
    ("Appleton", "WI"), ("Racine", "WI"), ("Kenosha", "WI"), ("Waukesha", "WI"),
    ("Rochester", "MN"), ("Duluth", "MN"), ("St. Cloud", "MN"),
    ("Sioux City", "IA"), ("Davenport", "IA"), ("Iowa City", "IA"),
    ("Olathe", "KS"), ("Lawrence", "KS"),

    # South Central
    ("Shreveport", "LA"), ("Lafayette", "LA"), ("Lake Charles", "LA"),
    ("Fayetteville", "AR"), ("Fort Smith", "AR"), ("Jonesboro", "AR"),
    ("Springfield", "TN"), ("Johnson City", "TN"), ("Kingsport", "TN"),

    # Mountain West
    ("Provo", "UT"), ("Ogden", "UT"), ("St. George", "UT"), ("Logan", "UT"),
    ("Missoula", "MT"), ("Billings", "MT"), ("Great Falls", "MT"),
    ("Bozeman", "MT"), ("Casper", "WY"), ("Cheyenne", "WY"),

    # Southwest / Plains
    ("Santa Fe", "NM"), ("Las Cruces", "NM"), ("Rio Rancho", "NM"),
    ("Rapid City", "SD"), ("Fargo", "ND"), ("Bismarck", "ND"),

    # Northeast
    ("Syracuse", "NY"), ("Buffalo", "NY"), ("Albany", "NY"), ("Yonkers", "NY"),
    ("White Plains", "NY"), ("Schenectady", "NY"),
    ("Trenton", "NJ"), ("Camden", "NJ"), ("Toms River", "NJ"),
    ("Edison", "NJ"), ("Woodbridge", "NJ"),
    ("New Bedford", "MA"), ("Springfield", "MA"), ("Lowell", "MA"), ("Cambridge", "MA"),
    ("Cranston", "RI"), ("Warwick", "RI"),
    ("Waterbury", "CT"), ("Danbury", "CT"), ("Norwalk", "CT"),

    # Pacific NW
    ("Bend", "OR"), ("Medford", "OR"), ("Corvallis", "OR"),
    ("Olympia", "WA"), ("Yakima", "WA"), ("Kennewick", "WA"),
    ("Vancouver", "WA"), ("Bellingham", "WA"),
]

# Subdivisions for the top 100 metros - suburbs and neighborhoods
# that have their own local service businesses
METRO_SUBDIVISIONS = {
    # === Top 10 metros - heavy subdivision ===
    "New York": [
        "Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island",
        "Yonkers", "White Plains", "New Rochelle", "Hempstead", "Huntington",
        "Islip", "Oyster Bay", "Babylon", "Smithtown",
    ],
    "Los Angeles": [
        "Hollywood", "Santa Monica", "Pasadena", "Glendale", "Burbank",
        "Torrance", "Inglewood", "Compton", "Pomona", "West Covina",
        "Whittier", "Downey", "Norwalk", "El Monte", "Alhambra",
        "Arcadia", "Azusa", "Covina", "Monrovia",
    ],
    "Chicago": [
        "Naperville", "Evanston", "Oak Park", "Schaumburg", "Joliet",
        "Aurora", "Elgin", "Waukegan", "Cicero", "Arlington Heights",
        "Palatine", "Des Plaines", "Orland Park", "Tinley Park",
        "Oak Lawn", "Berwyn", "Downers Grove", "Wheaton",
    ],
    "Houston": [
        "Katy", "Sugar Land", "Pearland", "The Woodlands", "Cypress",
        "Spring", "Humble", "Pasadena", "Baytown", "Missouri City",
        "League City", "Friendswood", "Deer Park", "La Porte",
        "Tomball", "Rosenberg", "Richmond", "Conroe",
    ],
    "Phoenix": [
        "Scottsdale", "Tempe", "Chandler", "Gilbert", "Glendale",
        "Peoria", "Surprise", "Goodyear", "Avondale", "Buckeye",
        "Queen Creek", "Maricopa", "Fountain Hills", "Cave Creek",
    ],
    "Philadelphia": [
        "Center City", "Germantown", "Cherry Hill", "King of Prussia",
        "Norristown", "Chester", "Bensalem", "Levittown", "Media",
        "West Chester", "Lansdale", "Doylestown", "Conshohocken",
    ],
    "San Antonio": [
        "Alamo Heights", "Stone Oak", "Helotes", "Schertz",
        "New Braunfels", "Boerne", "Cibolo", "Universal City",
        "Seguin", "San Marcos",
    ],
    "San Diego": [
        "La Jolla", "Chula Vista", "Oceanside", "Escondido",
        "Carlsbad", "El Cajon", "National City", "Poway",
        "Encinitas", "San Marcos", "Vista", "Santee",
    ],
    "Dallas": [
        "Plano", "Richardson", "Garland", "Mesquite", "Grand Prairie",
        "Carrollton", "Lewisville", "Denton", "Allen", "Flower Mound",
        "Rowlett", "Wylie", "Sachse", "Murphy", "Rockwall",
        "Cedar Hill", "DeSoto", "Duncanville",
    ],
    "San Jose": [
        "Santa Clara", "Sunnyvale", "Milpitas", "Campbell",
        "Cupertino", "Mountain View", "Palo Alto", "Los Gatos",
        "Saratoga", "Morgan Hill", "Gilroy",
    ],

    # === 11-25 - Heavy subdivision ===
    "Austin": [
        "Round Rock", "Cedar Park", "Pflugerville", "Georgetown",
        "San Marcos", "Kyle", "Buda", "Leander", "Dripping Springs",
        "Lakeway", "Bastrop", "Taylor",
    ],
    "Jacksonville": [
        "Orange Park", "Fleming Island", "Ponte Vedra", "St. Augustine",
        "Fernandina Beach", "Middleburg", "Green Cove Springs",
    ],
    "Fort Worth": [
        "Keller", "Southlake", "Grapevine", "Bedford", "Euless",
        "Hurst", "Mansfield", "Burleson", "Crowley", "Weatherford",
    ],
    "San Francisco": [
        "Daly City", "South San Francisco", "San Mateo", "Redwood City",
        "Berkeley", "Oakland", "Walnut Creek", "Fremont", "Hayward",
        "San Leandro", "Alameda", "Pleasanton", "Livermore",
    ],
    "Seattle": [
        "Bellevue", "Tacoma", "Redmond", "Kirkland", "Renton",
        "Kent", "Federal Way", "Everett", "Burien", "Tukwila",
        "Lynnwood", "Shoreline", "Bothell", "Issaquah",
    ],
    "Denver": [
        "Aurora", "Lakewood", "Arvada", "Westminster", "Thornton",
        "Centennial", "Broomfield", "Boulder", "Littleton",
        "Highlands Ranch", "Parker", "Castle Rock", "Longmont",
    ],
    "Atlanta": [
        "Marietta", "Decatur", "Roswell", "Alpharetta", "Kennesaw",
        "Dunwoody", "Sandy Springs", "Lawrenceville", "Duluth",
        "Snellville", "Stone Mountain", "Tucker", "Peachtree City",
        "Newnan", "Smyrna", "Woodstock", "Canton",
    ],
    "Miami": [
        "Fort Lauderdale", "Hialeah", "Hollywood", "Coral Gables",
        "Homestead", "Doral", "Kendall", "Aventura", "North Miami",
        "Miami Beach", "Cutler Bay", "Pinecrest", "Key Biscayne",
        "Weston", "Davie", "Pembroke Pines", "Miramar",
    ],
    "Tampa": [
        "St. Petersburg", "Clearwater", "Brandon", "Lakeland",
        "Plant City", "Wesley Chapel", "Temple Terrace", "Riverview",
        "Valrico", "Land O' Lakes", "New Port Richey", "Dunedin",
    ],
    "Las Vegas": [
        "Henderson", "North Las Vegas", "Summerlin", "Spring Valley",
        "Enterprise", "Paradise", "Boulder City", "Mesquite",
    ],
    "Nashville": [
        "Franklin", "Murfreesboro", "Hendersonville", "Gallatin",
        "Mount Juliet", "Brentwood", "Smyrna", "La Vergne",
        "Spring Hill", "Lebanon", "Goodlettsville",
    ],
    "Minneapolis": [
        "St. Paul", "Bloomington", "Plymouth", "Eagan", "Brooklyn Park",
        "Maple Grove", "Eden Prairie", "Woodbury", "Lakeville",
        "Burnsville", "Coon Rapids", "Blaine", "Apple Valley",
    ],
    "Portland": [
        "Beaverton", "Hillsboro", "Gresham", "Lake Oswego",
        "Tigard", "Tualatin", "Oregon City", "Milwaukie",
        "West Linn", "Wilsonville", "Sherwood", "Clackamas",
    ],
    "Sacramento": [
        "Elk Grove", "Roseville", "Folsom", "Citrus Heights",
        "Rancho Cordova", "Davis", "Woodland", "Rocklin",
        "Lincoln", "Carmichael", "Fair Oaks", "Orangevale",
    ],

    # === 26-50 - Moderate subdivision ===
    "Charlotte": [
        "Huntersville", "Concord", "Gastonia", "Matthews",
        "Mooresville", "Mint Hill", "Indian Trail", "Kannapolis",
        "Monroe", "Waxhaw", "Cornelius", "Davidson",
    ],
    "Raleigh": [
        "Durham", "Cary", "Apex", "Wake Forest", "Holly Springs",
        "Morrisville", "Garner", "Fuquay-Varina", "Clayton", "Knightdale",
    ],
    "Orlando": [
        "Kissimmee", "Sanford", "Winter Park", "Altamonte Springs",
        "Ocoee", "Apopka", "Clermont", "Winter Garden",
        "Lake Mary", "Deltona", "DeLand", "Daytona Beach",
    ],
    "Kansas City": [
        "Overland Park", "Olathe", "Lee's Summit", "Independence",
        "Shawnee", "Lenexa", "Blue Springs", "Liberty",
        "Gladstone", "Raytown", "Grandview",
    ],
    "Columbus": [
        "Dublin", "Westerville", "Gahanna", "Grove City",
        "Hilliard", "Reynoldsburg", "Upper Arlington", "Pickerington",
        "New Albany", "Powell", "Delaware",
    ],
    "Indianapolis": [
        "Carmel", "Fishers", "Greenwood", "Noblesville",
        "Lawrence", "Plainfield", "Avon", "Brownsburg",
        "Zionsville", "Westfield", "Greenfield",
    ],
    "San Bernardino": [
        "Ontario", "Rancho Cucamonga", "Fontana", "Upland",
        "Redlands", "Rialto", "Colton", "Highland", "Loma Linda",
    ],
    "Salt Lake City": [
        "Provo", "Ogden", "West Valley City", "Sandy", "Orem",
        "Layton", "Draper", "South Jordan", "Lehi", "American Fork",
        "Pleasant Grove", "Riverton", "Herriman",
    ],
    "Birmingham": [
        "Hoover", "Vestavia Hills", "Homewood", "Mountain Brook",
        "Trussville", "Pelham", "Alabaster", "Helena",
    ],
    "Oklahoma City": [
        "Norman", "Edmond", "Moore", "Midwest City",
        "Yukon", "Mustang", "Del City", "Bethany", "Choctaw",
    ],
    "Richmond": [
        "Glen Allen", "Henrico", "Midlothian", "Chester",
        "Mechanicsville", "Short Pump", "Chesterfield", "Ashland",
    ],
    "Boise": [
        "Meridian", "Nampa", "Caldwell", "Eagle",
        "Star", "Kuna", "Garden City", "Mountain Home",
    ],
    "Memphis": [
        "Germantown", "Collierville", "Bartlett", "Cordova",
        "Olive Branch", "Southaven", "Horn Lake", "Millington",
    ],
    "Louisville": [
        "Jeffersontown", "St. Matthews", "Shively", "New Albany",
        "Jeffersonville", "Clarksville", "Shepherdsville", "Elizabethtown",
    ],
    "Baltimore": [
        "Towson", "Columbia", "Ellicott City", "Catonsville",
        "Dundalk", "Glen Burnie", "Severn", "Bel Air",
        "Annapolis", "Pasadena", "Laurel", "Odenton",
    ],
    "Milwaukee": [
        "Waukesha", "Brookfield", "West Allis", "Wauwatosa",
        "New Berlin", "Menomonee Falls", "Muskego", "Franklin",
    ],
    "Tucson": [
        "Oro Valley", "Marana", "Sahuarita", "Green Valley",
        "Catalina", "Vail", "Drexel Heights",
    ],
    "Fresno": [
        "Clovis", "Madera", "Sanger", "Selma", "Visalia", "Hanford",
    ],

    # === 51-100 - Light subdivision ===
    "Cleveland": [
        "Parma", "Lakewood", "Strongsville", "Mentor",
        "Euclid", "Westlake", "North Olmsted",
    ],
    "St. Louis": [
        "Chesterfield", "Florissant", "O'Fallon", "St. Charles",
        "Clayton", "Kirkwood", "Webster Groves", "Ballwin",
    ],
    "Pittsburgh": [
        "Cranberry Township", "Bethel Park", "Mt. Lebanon",
        "Robinson Township", "Monroeville", "Murrysville",
    ],
    "Cincinnati": [
        "Mason", "West Chester", "Fairfield", "Hamilton",
        "Florence", "Covington", "Newport", "Norwood",
    ],
    "Riverside": [
        "Moreno Valley", "Corona", "Temecula", "Murrieta",
        "Lake Elsinore", "Menifee", "Hemet", "Perris",
    ],
    "Bakersfield": [
        "Tehachapi", "Delano", "Shafter", "Arvin",
    ],
    "Grand Rapids": [
        "Wyoming", "Kentwood", "Walker", "Grandville",
        "Holland", "Muskegon", "Norton Shores",
    ],
    "Knoxville": [
        "Farragut", "Maryville", "Oak Ridge", "Sevierville", "Lenoir City",
    ],
    "Baton Rouge": [
        "Denham Springs", "Gonzales", "Prairieville", "Central",
        "Baker", "Zachary", "Walker",
    ],
    "Spokane": [
        "Spokane Valley", "Cheney", "Liberty Lake", "Medical Lake",
    ],
    "Des Moines": [
        "West Des Moines", "Ankeny", "Urbandale", "Waukee",
        "Johnston", "Clive", "Ames",
    ],
    "Lexington": [
        "Georgetown", "Nicholasville", "Richmond", "Winchester", "Frankfort",
    ],
    "Reno": [
        "Sparks", "Carson City", "Fernley", "Dayton", "Sun Valley",
    ],
    "Fort Lauderdale": [
        "Weston", "Davie", "Plantation", "Sunrise", "Coral Springs",
        "Pompano Beach", "Deerfield Beach", "Coconut Creek",
        "Margate", "Tamarac", "Oakland Park",
    ],
    "Cape Coral": [
        "Fort Myers", "Lehigh Acres", "Bonita Springs", "Estero",
        "North Fort Myers", "Sanibel",
    ],
    "West Palm Beach": [
        "Boca Raton", "Boynton Beach", "Delray Beach", "Jupiter",
        "Wellington", "Royal Palm Beach", "Palm Beach Gardens",
        "Lake Worth", "Greenacres",
    ],
}


def get_all_search_locations():
    """
    Generate the full list of unique search locations.
    Returns deduplicated list of "City, State" strings.
    """
    locations = set()

    # Add all base metros
    for city, state in US_METROS:
        locations.add(f"{city}, {state}")

    # Add subdivision searches
    for metro_city, neighborhoods in METRO_SUBDIVISIONS.items():
        # Find the state for this metro
        state = None
        for city, st in US_METROS:
            if city == metro_city:
                state = st
                break
        if state:
            for neighborhood in neighborhoods:
                locations.add(f"{neighborhood}, {state}")

    return sorted(locations)


def get_base_locations():
    """Get just the base metro locations (no subdivisions)."""
    seen = set()
    result = []
    for city, state in US_METROS:
        loc = f"{city}, {state}"
        if loc not in seen:
            seen.add(loc)
            result.append(loc)
    return result


if __name__ == "__main__":
    base = get_base_locations()
    all_locs = get_all_search_locations()
    print(f"Base cities: {len(base)}")
    print(f"Total unique locations (with subdivisions): {len(all_locs)}")
    print(f"Extra subdivision locations: {len(all_locs) - len(base)}")

    # Volume estimate
    per_industry = len(all_locs) * 100
    print(f"\nPer industry: {len(all_locs)} searches × 100 = {per_industry:,} raw leads")
    print(f"After ~30% dedup: ~{int(per_industry * 0.7):,} unique")
