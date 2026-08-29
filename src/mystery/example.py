"""One case, written by hand, shipped with the code.

Two jobs. `--dry-run` uses it so the whole pipeline can be exercised with no API
key, no network and no spend: parse, solve, validate, critique, solvability, all
of it, in about a second. And the end-to-end test uses it, so there is finally
one test that runs the chain from a raw model response to an accusation (D-070).

It is deliberately a raw dict rather than a `Mystery`. That way the dry run and
the test both go through the parse boundary, which is where a real model's
output actually arrives, rather than starting from something already valid.

The case is prototype 02 rewritten to the current schema: hub victim, gated
motive, three liars of whom one is the killer, a shield, and a decoy.
"""

from typing import Any

OPENING_NIGHT: dict[str, Any] = {
    "title": "Opening Night",
    "killer": "wouter",
    "victim": "bram",
    "murder": "murder",
    "characters": [
        {
            "id": "ilse",
            "role": "The lead actress, twenty years at this theatre",
            "gender": "woman",
            "name": "Ilse Vermeer",
            "wants": "to still be the lead next season",
            "manner": "performing composure, and it is costing her",
            "under_pressure": "becomes grand, then very quiet",
            "look": "a woman in her late forties, sharp featured, still in stage makeup",
            "impressions": {
                "bram": "He decided things about people's lives over the phone.",
                "wouter": "Wouter has kept this building standing for twenty years.",
                "nadia": "She has been learning my part rather too thoroughly.",
            },
        },
        {
            "id": "tomas",
            "role": "The director",
            "gender": "man",
            "name": "Tomas Behr",
            "wants": "to survive a second flop",
            "manner": "talks too much and buries the useful sentence in the middle",
            "under_pressure": "volunteers other people's business",
            "look": "a heavy man of fifty, jacket over a creased shirt",
            "impressions": {
                "bram": "He told me tonight this was my last production here.",
                "renske": "She has been going through the books. Ask her why.",
                "ilse": "Ilse is frightened and covering it with grandeur.",
            },
        },
        {
            "id": "nadia",
            "role": "The understudy",
            "gender": "woman",
            "name": "Nadia Groot",
            "wants": "the part, and to not be pitied for wanting it",
            "manner": "answers exactly the question asked and nothing more",
            "under_pressure": "goes still and asks what you already know",
            "look": "a woman in her twenties, dark bobbed hair, plain black dress",
            "impressions": {
                "bram": "He promised me things in a corridor and forgot by morning.",
                "ilse": "She is not finished. She only thinks everyone thinks so.",
            },
        },
        {
            "id": "renske",
            "role": "Co-producer, and the victim's business partner",
            "gender": "woman",
            "name": "Renske Oud",
            "wants": "to get out of this company clean",
            "manner": "cold and precise, gives you the narrow answer",
            "under_pressure": "stops answering and starts asking",
            "look": "a woman of forty in a grey suit, reading glasses pushed up",
            "impressions": {
                "bram": "My partner was moving money and I was going to be the one holding it.",
                "tomas": "Tomas talks and talks and never says the thing.",
            },
        },
        {
            "id": "wouter",
            "role": "The stage manager, twenty two years in this building",
            "gender": "man",
            "name": "Wouter Damen",
            "wants": "to keep the only place he has ever belonged",
            "manner": "helpful about everything that costs him nothing",
            "under_pressure": "offers a smaller true thing to keep you off the larger one",
            "look": "a man of sixty in stage blacks, heavy hands, radio on his belt",
            "impressions": {
                "bram": "He was going to sell this place out from under all of us.",
                "ilse": "She has been good to me. People forget that about her.",
            },
        },
        {
            "id": "bram",
            "role": "The producer",
            "gender": "man",
            "name": "Bram Kessels",
            "look": "a man of fifty five in an expensive coat, dead since the interval",
        },
    ],
    "places": [
        {"id": "green_room", "name": "Green Room"},
        {"id": "dressing_corridor", "name": "Dressing Corridor"},
        {"id": "prop_store", "name": "Prop Store"},
        {"id": "lighting_box", "name": "Lighting Box"},
        {"id": "stage_door", "name": "Stage Door"},
    ],
    "slots": [
        {"id": "s0", "label": "19:40", "index": 0},
        {"id": "s1", "label": "20:00", "index": 1},
        {"id": "s2", "label": "20:40", "index": 2},
        {"id": "s3", "label": "21:00", "index": 3},
        {"id": "s4", "label": "21:20", "index": 4},
    ],
    "placements": {
        "ilse": {
            "s0": "dressing_corridor",
            "s1": "dressing_corridor",
            "s2": "dressing_corridor",
            "s3": "dressing_corridor",
            "s4": "green_room",
        },
        "tomas": {
            "s0": "green_room",
            "s1": "green_room",
            "s2": "green_room",
            "s3": "green_room",
            "s4": "green_room",
        },
        "nadia": {
            "s0": "dressing_corridor",
            "s1": "stage_door",
            "s2": "dressing_corridor",
            "s3": "dressing_corridor",
            "s4": "dressing_corridor",
        },
        "renske": {
            "s0": "green_room",
            "s1": "lighting_box",
            "s2": "lighting_box",
            "s3": "lighting_box",
            "s4": "green_room",
        },
        "wouter": {
            "s0": "stage_door",
            "s1": "green_room",
            "s2": "green_room",
            "s3": "prop_store",
            "s4": "green_room",
        },
        "bram": {
            "s0": "stage_door",
            "s1": "green_room",
            "s2": "green_room",
            "s3": "prop_store",
            "s4": "prop_store",
        },
    },
    "constraints": [
        {
            "id": "murder",
            "people": ["wouter", "bram"],
            "exclusive": True,
            "place": "prop_store",
            "slot": "s3",
            "description": "Wouter asks Bram down to show him where the equipment went.",
        },
        {
            "id": "the_threat",
            "people": ["wouter", "bram"],
            "exclusive": True,
            "place": "stage_door",
            "slot": "s0",
            "description": "Bram tells Wouter he has traced the missing equipment.",
        },
        {
            "id": "the_books",
            "people": ["renske"],
            "exclusive": True,
            "place": "lighting_box",
            "slot": "s2",
            "description": "Renske goes through Bram's files where nobody will look for her.",
        },
        {
            "id": "the_argument",
            "people": ["nadia", "bram"],
            "exclusive": True,
            "place": "stage_door",
            "slot": "s1",
            "description": "Nadia has it out with Bram about the promise he made her.",
        },
        {
            "id": "the_sacking",
            "people": ["tomas", "bram"],
            "place": "green_room",
            "slot": "s2",
            "description": "Bram tells Tomas this is his last production here.",
        },
    ],
    "secrets": [
        {
            "id": "the_theft",
            "holder": "wouter",
            "about": "bram",
            "summary": "Wouter has been quietly selling theatre equipment for two years.",
            "breaks_when": "he is pressed on who holds keys to the prop store",
            "known_by": [],
        },
        {
            "id": "the_reckoning",
            "holder": "wouter",
            "about": "bram",
            "summary": "Bram had traced the thefts and was going to the police after the run.",
            "revealed_by": "the_books",
            "is_motive": True,
            "known_by": ["renske"],
        },
        {
            "id": "the_books",
            "holder": "renske",
            "about": "bram",
            "summary": "Bram was moving money out of the company and Renske found the transfers.",
            "breaks_when": "she is told somebody already knows about the money",
            "evidence": "the transfer printouts",
            "known_by": ["tomas"],
        },
        {
            "id": "the_promise",
            "holder": "nadia",
            "about": "bram",
            "summary": "Bram promised Nadia the lead and went cold on it two weeks ago.",
            "breaks_when": "she is asked kindly rather than pressed",
            "known_by": ["ilse"],
        },
        {
            "id": "the_padding",
            "holder": "tomas",
            "about": "bram",
            "summary": "Tomas has been inflating production costs and pocketing the difference.",
            "breaks_when": "he is asked about the money rather than about the evening",
            "known_by": ["bram"],
        },
        {
            "id": "the_replacement",
            "holder": "ilse",
            "about": "bram",
            "summary": "Ilse overheard Bram say she was finished after this run.",
            "breaks_when": "she is told her part was already being recast",
            "known_by": [],
        },
    ],
    "false_claims": [
        {
            "character": "wouter",
            "place": "green_room",
            "slot": "s3",
            "covers": "the_theft",
            "admits_when": "never",
        },
        {
            "character": "renske",
            "place": "green_room",
            "slot": "s2",
            "covers": "the_books",
            "admits_when": "she is told somebody already knows what she was looking for",
        },
        {
            "character": "nadia",
            "place": "dressing_corridor",
            "slot": "s1",
            "covers": "the_promise",
            "admits_when": "somebody says they saw her at the stage door",
        },
    ],
    "discovery": {
        "finder": "tomas",
        "place": "prop_store",
        "summary": "He went down for a chair after the curtain and found him.",
    },
}
