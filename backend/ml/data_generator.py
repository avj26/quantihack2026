"""
StreetSense — Training data generator
Produces augmented labeled examples for two classifiers:
  1. Category classifier  → crime | antisocial | weather | road_hazard | safe | neutral
  2. Severity scorer      → float 0.0 (harmless) → 1.0 (critical)

Run:  python ml/data_generator.py
Output: ml/data/training_data.json
"""

import json, random, itertools, re
from pathlib import Path

random.seed(42)

# ── London areas injected during augmentation ─────────────────────────────────
AREAS = [
    "Brixton", "Hackney", "Peckham", "Shoreditch", "Dalston", "Elephant and Castle",
    "Kings Cross", "Bethnal Green", "Whitechapel", "Tottenham", "New Cross", "Camden",
    "Islington", "Clapham", "Stockwell", "Lewisham", "Woolwich", "Stratford",
    "Canary Wharf", "Soho", "Hoxton", "Walthamstow", "Barking", "Croydon",
]

TIME_REFS = [
    "just now", "tonight", "last night", "this evening", "an hour ago",
    "at midnight", "around 2am", "this afternoon", "earlier today",
    "right now", "a few minutes ago", "this morning",
]

LOCATION_PREFIXES = [
    "Near {area}", "On {area} road", "Just off {area}", "Around {area}",
    "Walking through {area}", "By {area} station", "In {area}",
]

# ── Synonym swaps ─────────────────────────────────────────────────────────────
SYNONYMS = {
    "mugged":       ["robbed", "attacked and robbed", "held up"],
    "stabbed":      ["knifed", "attacked with a weapon", "injured in an attack"],
    "unsafe":       ["dangerous", "not safe", "risky", "sketchy"],
    "avoid":        ["stay away from", "steer clear of", "do not walk through"],
    "attacked":     ["assaulted", "jumped", "set upon"],
    "threatening":  ["intimidating", "aggressive", "menacing"],
    "snatched":     ["grabbed", "stolen", "taken forcefully"],
    "dark":         ["unlit", "poorly lit", "pitch black"],
    "slippery":     ["icy", "wet and dangerous", "treacherous underfoot"],
    "fog":          ["thick fog", "heavy mist", "dense haze"],
    "pothole":      ["road damage", "large hole in the road", "broken tarmac"],
    "safe":         ["secure", "fine", "comfortable", "no issues"],
    "quiet":        ["empty", "deserted", "calm", "peaceful"],
    "police":       ["officers", "police patrol", "police presence", "cops"],
    "gang":         ["group of youths", "group of men", "crew"],
}

# ── Seed data ─────────────────────────────────────────────────────────────────
# Each entry: (text, category, severity_0_to_1)
# severity: crime ~0.6-1.0 | antisocial ~0.3-0.7 | weather ~0.1-0.55
#           road_hazard ~0.15-0.50 | safe ~0.0-0.15 | neutral ~0.05-0.30

SEEDS = [
    # ── CRIME ───────────────────────────────────────────────────────────────
    ("Just witnessed a stabbing on this street, police are on the way", "crime", 0.98),
    ("Someone got stabbed outside the shop here tonight", "crime", 0.97),
    ("Armed robbery at the corner shop, they had a knife", "crime", 0.95),
    ("A woman was violently assaulted near the bus stop just now", "crime", 0.93),
    ("Saw a man get jumped by a gang and beaten up", "crime", 0.92),
    ("Knife pulled on a pedestrian outside here", "crime", 0.94),
    ("Got mugged at knifepoint walking through here tonight", "crime", 0.91),
    ("Shooting reported nearby, police have cordoned the area", "crime", 0.99),
    ("Just got mugged, they stole my phone and wallet", "crime", 0.86),
    ("Had my bag snatched while walking here, avoid this route", "crime", 0.84),
    ("Phone grabbed from my hand by someone on a moped", "crime", 0.82),
    ("Saw a pickpocket working the area, be careful with your pockets", "crime", 0.70),
    ("Attempted robbery on this road, victim managed to escape", "crime", 0.80),
    ("Bike theft happened in broad daylight right here", "crime", 0.58),
    ("Car windows smashed and belongings stolen on this street", "crime", 0.60),
    ("Drug dealing openly happening in the alley nearby", "crime", 0.62),
    ("Police arrested someone aggressively right outside here", "crime", 0.65),
    ("Burglary in progress, police called and on their way", "crime", 0.72),
    ("Wallet lifted from my pocket while I was distracted", "crime", 0.68),
    ("Heard loud fight nearby, sounds like someone got hurt", "crime", 0.75),
    ("Someone just threatened me with a bottle, get out of here", "crime", 0.88),
    ("Mugging happened to my friend near this spot last week", "crime", 0.83),
    ("Police tape blocking the road ahead, incident overnight", "crime", 0.74),
    ("Witnessed road rage that turned into a physical fight", "crime", 0.76),

    # ── ANTISOCIAL ──────────────────────────────────────────────────────────
    ("Large group of men blocking the pavement and being aggressive", "antisocial", 0.68),
    ("Gang of youths intimidating people near the park gates", "antisocial", 0.66),
    ("Someone followed me down this road for several minutes, very scary", "antisocial", 0.65),
    ("Felt really threatened by a group hanging around the corner", "antisocial", 0.62),
    ("Men shouting aggressively at passers-by on this street", "antisocial", 0.60),
    ("Group asking for money very aggressively, would not take no", "antisocial", 0.58),
    ("Someone verbally abusing strangers outside the shops here", "antisocial", 0.52),
    ("Drunk group causing trouble and being threatening", "antisocial", 0.55),
    ("Felt intimidated walking past a large group on the corner", "antisocial", 0.50),
    ("Person acting erratically and shouting at everyone passing by", "antisocial", 0.48),
    ("Sketchy group of people hanging around the underpass", "antisocial", 0.45),
    ("Someone was very threatening in their behaviour near here", "antisocial", 0.60),
    ("Youths throwing things at cars and pedestrians on this road", "antisocial", 0.63),
    ("Group of men made comments and followed me briefly, stay aware", "antisocial", 0.54),
    ("Constant harassment from people outside this area tonight", "antisocial", 0.56),
    ("Someone aggressive was blocking the path and refused to move", "antisocial", 0.47),
    ("Two men arguing and pushing each other outside the pub here", "antisocial", 0.42),
    ("People clearly on drugs behaving erratically near here", "antisocial", 0.44),
    ("Graffiti gang marking territory, area feels tense tonight", "antisocial", 0.38),
    ("Loitering group near the ATM made me uncomfortable", "antisocial", 0.36),
    ("Repeated verbal abuse from someone outside the station here", "antisocial", 0.53),
    ("Saw someone being followed and harassed down this road", "antisocial", 0.61),

    # ── WEATHER ─────────────────────────────────────────────────────────────
    ("Dense fog tonight makes it impossible to see ahead safely", "weather", 0.52),
    ("Black ice on the pavements here, very dangerous to walk", "weather", 0.55),
    ("Flooding on the road making it impassable and dangerous", "weather", 0.50),
    ("Violent thunderstorm with lightning, not safe to be outside", "weather", 0.50),
    ("Heavy snow and ice making every step dangerous tonight", "weather", 0.48),
    ("Roads flooded and pavement submerged, take another route", "weather", 0.47),
    ("Strong gusts knocking people over near the open stretch", "weather", 0.42),
    ("Thick fog with almost zero visibility walking through here", "weather", 0.48),
    ("Heavy rain has made the road flood and reduced visibility a lot", "weather", 0.40),
    ("Icy conditions making it really dangerous to walk here tonight", "weather", 0.44),
    ("Heavy rain and poor drainage flooding the underpass", "weather", 0.38),
    ("Slippery cobblestones in the rain, saw someone fall over", "weather", 0.35),
    ("Wind so strong umbrellas are useless and vision is affected", "weather", 0.38),
    ("Rain has washed debris onto the road making it dangerous", "weather", 0.32),
    ("Light drizzle making the road surface slightly slippery", "weather", 0.18),
    ("Bit foggy tonight but mostly fine if you go slowly", "weather", 0.22),
    ("Rain is picking up, roads are getting wet and slippery", "weather", 0.25),
    ("Overcast and breezy tonight, nothing serious but take care", "weather", 0.14),
    ("Puddles everywhere from earlier rain, pavements are wet", "weather", 0.15),
    ("Light snow dusting on the road, a bit slippery in places", "weather", 0.28),
    ("Windy evening making the walk less pleasant but manageable", "weather", 0.16),
    ("Very misty tonight, reduced visibility but still walkable", "weather", 0.24),

    # ── ROAD HAZARD ─────────────────────────────────────────────────────────
    ("This whole stretch has no street lighting at all, pitch black", "road_hazard", 0.50),
    ("Street lights are all out on this road, completely unlit", "road_hazard", 0.48),
    ("No lighting and the path is completely dark and isolated", "road_hazard", 0.47),
    ("Huge pothole in the middle of the road that came out of nowhere", "road_hazard", 0.38),
    ("Pavement completely broken and dangerous to walk on at night", "road_hazard", 0.40),
    ("Scaffolding collapsed and is blocking half the pavement dangerously", "road_hazard", 0.42),
    ("Gas leak reported on this road, area has been cordoned off", "road_hazard", 0.45),
    ("Road surface is really broken and dangerous here", "road_hazard", 0.35),
    ("Several street lights broken making the path very dark", "road_hazard", 0.38),
    ("Underpass has zero lighting tonight, very uncomfortable to walk through", "road_hazard", 0.44),
    ("Loose paving slabs that wobble and could cause a fall", "road_hazard", 0.28),
    ("Overgrown bushes blocking the path and reducing visibility here", "road_hazard", 0.22),
    ("Some broken street lights making parts of this road darker than usual", "road_hazard", 0.30),
    ("Pavement is narrow and poorly maintained along this section", "road_hazard", 0.20),
    ("Gravel path in poor condition makes cycling difficult and risky", "road_hazard", 0.25),
    ("Debris on the road from last night's works, watch your step", "road_hazard", 0.22),
    ("Single street lamp flickering, walking feels less safe", "road_hazard", 0.26),
    ("Cobblestones in poor condition, slippery and uneven underfoot", "road_hazard", 0.24),
    ("Water main burst making the road impassable and slippery", "road_hazard", 0.40),
    ("Works have removed the pavement leaving only a narrow muddy strip", "road_hazard", 0.32),

    # ── SAFE ────────────────────────────────────────────────────────────────
    ("Really lovely evening walk, felt completely safe the whole way", "safe", 0.04),
    ("Lots of people around, great atmosphere, felt very comfortable here", "safe", 0.06),
    ("Police patrol walking through regularly, area feels very secure", "safe", 0.05),
    ("Busy road with loads of families and couples out, very safe feeling", "safe", 0.07),
    ("Just walked this route alone and felt completely fine, recommend it", "safe", 0.06),
    ("Well-lit road with constant foot traffic, never felt unsafe here", "safe", 0.05),
    ("Lovely community feel around here, people are friendly and area is safe", "safe", 0.04),
    ("Night market nearby means it is really lively and safe feeling", "safe", 0.08),
    ("CCTV cameras everywhere and well lit, feels very safe tonight", "safe", 0.05),
    ("Police stationed near here tonight, area is very well covered", "safe", 0.04),
    ("Loads of pubs and restaurants with people outside, very lively and safe", "safe", 0.09),
    ("Walked here late and felt perfectly safe, good lighting and people around", "safe", 0.07),
    ("This road is always busy and well lit, never had any issues here", "safe", 0.05),
    ("Families and dog walkers everywhere, completely safe atmosphere", "safe", 0.04),
    ("Always feel safe walking this route, lots of CCTV and foot traffic", "safe", 0.06),
    ("Well maintained area with good lighting, felt very comfortable", "safe", 0.05),
    ("Council has improved the lighting here recently, much safer now", "safe", 0.06),
    ("Used this route regularly at night, always fine and well lit", "safe", 0.04),
    ("Security guard stationed nearby, feel very safe here", "safe", 0.05),
    ("Busy high street with lots of shops open late, very safe vibe", "safe", 0.07),

    # ── NEUTRAL ─────────────────────────────────────────────────────────────
    ("Walking through now, seems pretty quiet tonight, nothing to report", "neutral", 0.15),
    ("Not many people around at this hour but nothing major to worry about", "neutral", 0.18),
    ("Looks normal here, nothing unusual happening that I can see", "neutral", 0.12),
    ("Just passed through, fairly empty but seemed fine", "neutral", 0.13),
    ("Bit dark around here but nothing sketchy going on", "neutral", 0.22),
    ("Quiet evening, saw a few people walking their dogs, nothing concerning", "neutral", 0.11),
    ("Nothing to report here, normal evening on this road", "neutral", 0.12),
    ("Few people around but the atmosphere seems calm enough", "neutral", 0.16),
    ("Walked past without any issues, nothing out of the ordinary", "neutral", 0.13),
    ("It is pretty empty here tonight but I felt okay walking through", "neutral", 0.20),
    ("Normal level of activity for this time of night, no concerns", "neutral", 0.14),
    ("Saw some people sitting outside but nothing threatening", "neutral", 0.17),
    ("Fairly standard walk, nothing notable or worrying to mention", "neutral", 0.13),
    ("A bit quieter than usual but nothing unusual or alarming", "neutral", 0.18),
    ("Passed through without any incident, road seems fine", "neutral", 0.12),
    ("Nothing happening here that I noticed, seemed pretty ordinary", "neutral", 0.14),
    ("Area seems calm, just the usual late night quietness", "neutral", 0.16),
    ("Not a lot going on here, uneventful walk through", "neutral", 0.11),
    ("Few people about, no obvious safety issues I could see", "neutral", 0.15),
    ("Pretty deserted but nothing to suggest danger", "neutral", 0.22),
]


# ── Augmentation helpers ──────────────────────────────────────────────────────

def _insert_location(text):
    area = random.choice(AREAS)
    prefix = random.choice(LOCATION_PREFIXES).format(area=area)
    # 50% prefix, 50% suffix
    if random.random() < 0.5:
        return f"{prefix} — {text.lower()}"
    else:
        return f"{text} (near {area})"


def _insert_time(text):
    t = random.choice(TIME_REFS)
    # Inject naturally
    patterns = [
        f"{text} — {t}",
        f"{t.capitalize()}: {text.lower()}",
        f"{text}, happened {t}",
    ]
    return random.choice(patterns)


def _synonym_swap(text):
    words = text.split()
    swapped = False
    for i, word in enumerate(words):
        key = word.lower().rstrip('.,!?;:')
        if key in SYNONYMS and random.random() < 0.7:
            replacement = random.choice(SYNONYMS[key])
            # Preserve capitalisation
            if word[0].isupper():
                replacement = replacement.capitalize()
            words[i] = word.replace(key, replacement, 1)
            swapped = True
            break  # one swap per sentence keeps it natural
    return ' '.join(words) if swapped else None


def _intensity_shift(text, severity):
    """Add intensity words that match the severity level."""
    if severity >= 0.85:
        intensifiers = ["really serious", "absolutely terrifying", "extremely dangerous"]
        return f"{text} — {random.choice(intensifiers)}"
    elif severity >= 0.60:
        intensifiers = ["quite dangerous", "pretty concerning", "worrying"]
        return f"{text} — {random.choice(intensifiers)}"
    elif severity >= 0.30:
        cautious = ["take care", "stay alert", "be aware"]
        return f"{text} ({random.choice(cautious)})"
    else:
        positives = ["all good", "feels fine", "no worries"]
        return f"{text} — {random.choice(positives)}"


def _add_hashtags(text, category):
    tags = {
        "crime":       ["#StaySafe", "#LondonCrime", "#BeCareful", "#CrimeAlert"],
        "antisocial":  ["#StaySafe", "#BeCareful", "#LondonStreets"],
        "weather":     ["#LondonWeather", "#StaySafe", "#TakeExtra Care"],
        "road_hazard": ["#RoadSafety", "#WatchYourStep", "#LondonRoads"],
        "safe":        ["#SafeStreets", "#LondonLife", "#AllGood"],
        "neutral":     ["#LondonLife", "#NightWalk"],
    }
    tag = random.choice(tags.get(category, ["#London"]))
    return f"{text} {tag}"


# ── Severity jitter ────────────────────────────────────────────────────────────

def _jitter(severity, scale=0.04):
    """Add small noise to severity so model learns a distribution, not point values."""
    return round(max(0.0, min(1.0, severity + random.gauss(0, scale))), 3)


# ── Main generator ────────────────────────────────────────────────────────────

def generate(n_augments_per_seed=8, output_path="ml/data/training_data.json"):
    records = []

    for text, category, severity in SEEDS:
        # 1. Original
        records.append({"text": text, "category": category, "severity": _jitter(severity)})

        # 2-8. Augmented variants
        augmentations = []

        syn = _synonym_swap(text)
        if syn:
            augmentations.append(syn)

        augmentations.append(_insert_location(text))
        augmentations.append(_insert_time(text))
        augmentations.append(_insert_location(_insert_time(text)))
        augmentations.append(_intensity_shift(text, severity))
        augmentations.append(_add_hashtags(text, category))

        if syn:
            augmentations.append(_insert_location(syn))
            augmentations.append(_insert_time(syn))

        for aug in augmentations[:n_augments_per_seed]:
            records.append({
                "text": aug,
                "category": category,
                "severity": _jitter(severity),
            })

    # Shuffle so categories are interleaved during training
    random.shuffle(records)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(records, f, indent=2)

    # Print summary
    from collections import Counter
    cats = Counter(r["category"] for r in records)
    print(f"Generated {len(records)} records:")
    for cat, n in sorted(cats.items()):
        print(f"  {cat:15s} {n:4d} examples")
    print(f"Saved → {output_path}")
    return records


if __name__ == "__main__":
    generate()
