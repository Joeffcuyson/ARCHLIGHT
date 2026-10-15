"""
ARCLIGHT: FRONTLINE
A 2D class-based action game. Single file, Pygame, no external assets.
All sprites are drawn procedurally at runtime (no copyright risk).

RUN LOCALLY
    pip install pygame
    python arclight.py

RUN AS A WEB APPLET
    pip install pygbag
    pygbag arclight.py        # then open http://localhost:8000

CONTROLS
    WASD / Arrows .... move
    Mouse ............ aim
    Left Click / J ... basic attack
    Q ................ skill 1
    E ................ skill 2
    SPACE / SHIFT .... dodge roll (i-frames)
    R ................ reload (Gunfighter)
    1-5 .............. drink a potion (heal / speed / strength / ward / focus)
    TAB / I .......... open the inventory (pauses the game)
    F11 .............. toggle fullscreen
    ESC .............. pause      |  ENTER: confirm / advance
    PORTAL ........... opens when a stage is cleared; walk into it (or press
                       ENTER once it is open) to warp on to the next dialog
    1-5 .............. spend a stat point (operative select screen)

PROGRESSION
    Three save slots live in arclight_save.json next to this script.
    Picking an operative in an empty slot unlocks them for free; every
    operative after that costs coins earned in that same slot. Kills pay
    out coins and XP; XP levels an operative up (mastery), and each level
    grants one point to spend on DMG / RNG / SPD / DEF / UTL. Enemies also
    scale up chapter by chapter, on top of the difficulty setting.

    To remove a save, click DELETE on its slot card (or press DEL on the save
    screen) and confirm. This wipes that slot's coins, levels and unlocks.

CHAPTER TWISTS
    Every chapter has its own floor colour and one twist on top of the usual
    fighting. The twist is announced on the story card and as a banner when
    the stage starts, and its name sits under the chapter title in the HUD.
        I    CROSSWIND  ash gusts shove you and the enemies around
        II   CROSSFIRE  mortar shells land on red circles (they hit enemies too)
        III  BLACKOUT   the yard is dark; the relay surges to stun what nears it
        IV   ASH RING   the safe ground shrinks as the Warden fight drags on

POTIONS
    Fallen enemies sometimes drop a potion (brutes most often, and a drop is
    guaranteed after a long dry spell). Walk over it to pick it up. Potions
    live in a bag that carries from chapter to chapter; dying and retrying a
    chapter gives you the bag you started it with.
        HEAL      instantly restores 40% of max HP
        SPEED     +35% move speed for 9s
        STRENGTH  +40% damage dealt for 10s
        WARD      halves damage taken for 8s
        FOCUS     skills and dodge recharge 2.5x faster for 10s
    Each potion stacks up to a cap. The belt along the bottom of the screen
    shows what you hold and how long each active effect has left.
"""

import asyncio
import json
import math
import os
import random
import sys

import pygame
from pygame.math import Vector2 as V2

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
W, H = 1280, 800          # logical resolution: raise these to make the map bigger
OY = (H - 640) // 2       # vertical offset for menu screens laid out for a 640-high view
FPS = 60
ARENA = pygame.Rect(48, 104, W - 96, H - 176)

BG = (17, 19, 27)
BG2 = (25, 28, 39)
GRID = (33, 37, 51)
WALL = (58, 65, 88)
WHITE = (236, 239, 246)
GREY = (142, 150, 168)
DGREY = (68, 74, 92)
BLACK = (10, 11, 16)
RED = (226, 84, 84)
GREEN = (96, 208, 128)
YELLOW = (240, 200, 96)
CYAN = (96, 206, 224)
PURPLE = (170, 122, 232)
ORANGE = (238, 148, 76)


# one portal colour per chapter
PORTAL_COLORS = [CYAN, GREEN, ORANGE, PURPLE]


def dark(c, f=0.60):
    return (int(c[0] * f), int(c[1] * f), int(c[2] * f))


def lite(c, f=0.35):
    return tuple(min(255, int(x + (255 - x) * f)) for x in c)


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def norm(v):
    return v.normalize() if v.length_squared() > 0.0001 else V2(1, 0)


# ----------------------------------------------------------------------------
# CHARACTER DATA
# stats are 1-10 and only feed the radar chart; real numbers are below them.
# ----------------------------------------------------------------------------
CHARACTERS = [
    {
        "id": "garran", "name": "GARRAN", "title": "Bulwark of Marrow Gate",
        "role": "MELEE", "cls": "TANK", "colors": [(96, 128, 196), (214, 178, 96)],
        "weapon": "sword", "hp": 260, "speed": 178, "dmg": 20, "atk_cd": 0.52, "rng": 74,
        "stats": {"DMG": 6, "RNG": 2, "SPD": 4, "DEF": 10, "UTL": 5},
        "passive": ("IRONCLAD", "The lower his HP, the harder he is to kill: up to 45% damage reduction and +25% move speed."),
        "q": ("SHIELD BASH", "Charge forward, damaging and stunning everything you plow through.", 6.0),
        "e": ("BULWARK", "3s of heavy damage reduction. Drags nearby enemies toward you.", 11.0),
        "bio": "Line-holder. Signed on when the Choir cut the relay his district ran on.",
    },
    {
        "id": "vex", "name": "VEX", "title": "The Quiet Knife",
        "role": "MELEE", "cls": "ASSASSIN", "colors": [(74, 80, 110), (226, 92, 118)],
        "weapon": "dagger", "hp": 130, "speed": 252, "dmg": 17, "atk_cd": 0.26, "rng": 58,
        "stats": {"DMG": 8, "RNG": 2, "SPD": 10, "DEF": 3, "UTL": 6},
        "passive": ("BLOODRUSH", "+6% speed per hit (5 stacks), +10 HP per kill, x1.6 damage to targets under 40% HP. Below 35% HP you are slowed and weakened."),
        "q": ("BLINK", "Teleport toward the cursor.", 4.0),
        "e": ("SHADOWSTEP", "Vanish for 2.5s. Enemies lose you; your next hit deals x2.5.", 12.0),
        "bio": "Freelance. Bills by the head and never explains the invoice.",
    },
    {
        "id": "bram", "name": "BRAM", "title": "Pit Champion",
        "role": "MELEE", "cls": "FIGHTER", "colors": [(186, 96, 64), (232, 208, 168)],
        "weapon": "axe", "hp": 190, "speed": 200, "dmg": 19, "atk_cd": 0.38, "rng": 68,
        "stats": {"DMG": 7, "RNG": 2, "SPD": 6, "DEF": 7, "UTL": 5},
        "passive": ("MOMENTUM", "Every 3rd hit is a HEAVY: x1.8 damage and a 1.5s slow. Below 40% HP all damage is x1.35."),
        "q": ("WHIRL", "Spin. Hits everything around you and counts toward Momentum.", 5.0),
        "e": ("GRAPPLE", "Yank the nearest enemy in front of you and stun it.", 8.0),
        "bio": "Fought for coin in the Marrow pits until the pits lost power too.",
    },
    {
        "id": "sable", "name": "SABLE", "title": "Longsight",
        "role": "RANGED", "cls": "MARKSMAN", "colors": [(86, 156, 128), (226, 220, 180)],
        "weapon": "bow", "hp": 140, "speed": 208, "dmg": 20, "atk_cd": 0.50, "rng": 620,
        "stats": {"DMG": 9, "RNG": 10, "SPD": 6, "DEF": 3, "UTL": 4},
        "passive": ("LONGSHOT", "Damage scales with distance, up to x1.6 at maximum range. Every hit grants a short burst of speed."),
        "q": ("PIERCING SHOT", "A heavy arrow that punches through a whole line of enemies.", 6.0),
        "e": ("BACKSTEP", "Leap away from the cursor and gain speed.", 5.0),
        "bio": "Counts distance the way other people count money.",
    },
    {
        "id": "kite", "name": "KITE", "title": "Powder and Nerve",
        "role": "RANGED", "cls": "GUNFIGHTER", "colors": [(150, 122, 96), (238, 176, 84)],
        "weapon": "gun", "hp": 150, "speed": 216, "dmg": 11, "atk_cd": 0.13, "rng": 460,
        "stats": {"DMG": 8, "RNG": 7, "SPD": 7, "DEF": 4, "UTL": 6},
        "passive": ("FALLOFF", "12-round magazine, 1.4s reload. Hurts most up close: x1.25 point blank down to x0.65 at range."),
        "q": ("BUCKSHOT", "Six pellets in a cone. Costs 4 rounds.", 4.5),
        "e": ("COMBAT ROLL", "Roll and reload instantly.", 6.0),
        "bio": "Reloads mid-sentence. Has never once finished the sentence.",
    },
    {
        "id": "nyx", "name": "NYX", "title": "Last of the Shard Choir",
        "role": "MAGE", "cls": "ARCANIST", "colors": [(112, 88, 176), (140, 214, 232)],
        "weapon": "staff", "hp": 135, "speed": 196, "dmg": 18, "atk_cd": 0.42, "rng": 420,
        "stats": {"DMG": 8, "RNG": 6, "SPD": 5, "DEF": 3, "UTL": 9},
        "passive": ("ARCANE PRESSURE", "The inverse of a marksman: x1.5 damage point blank, fading to x0.7 at range. Punish anything that closes in."),
        "q": ("FROST FIELD", "A lingering zone that slows and grinds down whatever stands in it.", 7.0),
        "e": ("NOVA", "Radial burst. Damages, stuns and knocks back everything near you.", 10.0),
        "bio": "Magic is rare now. She is one of the reasons it is rare.",
    },
    {
        "id": "wisp", "name": "WISP", "title": "Field Engineer",
        "role": "SUPPORT", "cls": "UTILITY", "colors": [(96, 168, 168), (232, 232, 120)],
        "weapon": "satchel", "hp": 155, "speed": 210, "dmg": 10, "atk_cd": 0.30, "rng": 340,
        "stats": {"DMG": 4, "RNG": 5, "SPD": 7, "DEF": 5, "UTL": 10},
        "passive": ("FIELD KIT", "Weak on paper. Regenerates HP steadily and reads the battlefield as a board to be rigged."),
        "q": ("LANDMINE", "Plant a proximity mine. Up to 3 live at once.", 2.5),
        "e": ("SMOKE BOMB", "Smoke that slows enemies, blinds their shooters, and speeds you up inside it.", 9.0),
        "bio": "Not a fighter. Simply arrives before the fight and rearranges the floor.",
    },
]

CHAR_BY_ID = {c["id"]: c for c in CHARACTERS}

# ----------------------------------------------------------------------------
# PROGRESSION / SAVE FILES
# Three save slots on disk (arclight_save.json, next to this script). Each
# slot has its own coin bank and, per operative, a mastery level with XP and
# allocatable stat points. The first operative picked in an empty slot is
# free; every operative after that must be unlocked with coins earned in
# that same slot -- so one save can eventually field the whole roster, but
# starts locked to whoever you picked first.
# ----------------------------------------------------------------------------
SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arclight_save.json")
NUM_SLOTS = 3
LEVEL_CAP = 20
UNLOCK_COST = 250
STAT_KEYS = ["DMG", "RNG", "SPD", "DEF", "UTL"]

# per-kill reward -> (xp, coins). Bosses pay out far more of both.
KILL_REWARD = {"grunt": (6, 1), "slinger": (8, 1), "brute": (16, 2), "warden": (320, 40)}


def xp_for_level(level):
    """XP needed to advance from `level` to `level + 1`."""
    return 60 + level * 35


def new_class_save():
    return {"level": 1, "xp": 0, "unspent": 0, "points": {k: 0 for k in STAT_KEYS}}


def new_slot():
    return {"used": False, "coins": 0, "classes": {}, "diff": None}


def load_saves():
    slots = None
    if os.path.exists(SAVE_PATH):
        try:
            with open(SAVE_PATH, "r") as f:
                slots = json.load(f).get("slots")
        except Exception:
            slots = None
    if not slots:
        slots = []
    while len(slots) < NUM_SLOTS:
        slots.append(new_slot())
    for s in slots[:NUM_SLOTS]:
        s.setdefault("diff", None)   # older saves predate the difficulty lock
    return slots[:NUM_SLOTS]


def write_saves(slots):
    try:
        with open(SAVE_PATH, "w") as f:
            json.dump({"slots": slots}, f)
    except Exception:
        pass  # progression is a bonus layer; never crash the game over disk I/O


def slot_has_data(slot):
    """True if a slot holds anything worth deleting (progress or a locked-in difficulty)."""
    return bool(slot.get("classes")) or bool(slot.get("used")) or bool(slot.get("diff"))


def ensure_class(slot, char_id):
    """Unlock `char_id` in `slot` for free -- used for a slot's first pick."""
    if char_id not in slot["classes"]:
        slot["classes"][char_id] = new_class_save()
        slot["used"] = True
    return slot["classes"][char_id]


def grant_xp(csave, xp):
    """Add XP and roll over any level-ups. Returns the number of levels gained."""
    csave["xp"] += xp
    gained = 0
    while csave["level"] < LEVEL_CAP and csave["xp"] >= xp_for_level(csave["level"]):
        csave["xp"] -= xp_for_level(csave["level"])
        csave["level"] += 1
        csave["unspent"] += 1
        gained += 1
    if csave["level"] >= LEVEL_CAP:
        csave["xp"] = 0
    return gained


def effective_char(base, csave):
    """Base operative dict + spent mastery points -> a boosted copy for play."""
    ch = dict(base)
    pts = csave["points"]
    ch["dmg"] = base["dmg"] * (1 + 0.04 * pts["DMG"])
    ch["rng"] = base["rng"] * (1 + 0.05 * pts["RNG"])
    ch["speed"] = base["speed"] * (1 + 0.03 * pts["SPD"])
    ch["hp"] = base["hp"] * (1 + 0.05 * pts["DEF"])
    ch["atk_cd"] = base["atk_cd"] * (1 - min(0.35, 0.03 * pts["UTL"]))
    ch["level"] = csave["level"]
    return ch


# ----------------------------------------------------------------------------
# DIFFICULTY
# ----------------------------------------------------------------------------
DIFFICULTIES = [
    {
        "id": "easy", "name": "EASY", "hp": 0.75, "dmg": 0.70, "interval": 1.30,
        "desc": "Fewer hostiles, softer hits. Good for learning an operative.",
    },
    {
        "id": "normal", "name": "NORMAL", "hp": 1.00, "dmg": 1.00, "interval": 1.00,
        "desc": "The intended way to play. Balanced pace and pressure.",
    },
    {
        "id": "hard", "name": "HARD", "hp": 1.30, "dmg": 1.40, "interval": 0.75,
        "desc": "Enemies hit harder, swarm faster, and take more to put down.",
    },
]

# ----------------------------------------------------------------------------
# STORY / CHAPTERS
# ----------------------------------------------------------------------------
CHAPTERS = [
    {
        "name": "CHAPTER I - THE QUIET ROAD",
        "floor": (54, 54, 52),
        "twist": {"id": "wind", "name": "CROSSWIND",
                  "desc": "Ash gusts shove everyone down the road. Ride them, or fight the drift."},
        "goal": "kills", "target": 14, "relay": False,
        "spawn": {"grunt": 8, "slinger": 1}, "interval": 1.05, "max_alive": 6, "boss": False,
        "intro": [
            "Ardenne runs on Shard Relays. Cut one, and a district goes dark by morning.",
            "Three went dark this week. The Warden Choir left a signature at each: a ring of ash.",
            "Your contract is simple. Walk the north road to Marrow Gate. Arrive alive.",
            "The road is never quiet when someone tells you it is.",
        ],
        "outro": [
            "Fourteen of them for one stretch of empty road.",
            "They were not guarding the road. They were keeping people off it.",
            "Marrow Gate is close enough now to smell the smoke.",
        ],
    },
    {
        "name": "CHAPTER II - CROSSFIRE AT MARROW GATE",
        "floor": (60, 50, 50),
        "twist": {"id": "mortar", "name": "CROSSFIRE",
                  "desc": "Mortar shells land on red circles. Step out, or drag enemies into the blast."},
        "goal": "survive", "target": 55.0, "relay": False,
        "spawn": {"grunt": 6, "slinger": 4, "brute": 1}, "interval": 0.95, "max_alive": 8, "boss": False,
        "intro": [
            "Marrow Gate is a funnel, and the Choir knows it.",
            "Gate crew is evacuating the last two blocks. You buy them the minutes.",
            "Hold this yard until the horn sounds. Nothing clever. Just hold.",
        ],
        "outro": [
            "The horn goes. The yard is yours, for whatever that is worth.",
            "A gate runner presses a slate into your hand: RELAY SEVEN, STILL LIT.",
            "One relay still burning in the whole district. They will come for it tonight.",
        ],
    },
    {
        "name": "CHAPTER III - HOLD RELAY SEVEN",
        "floor": (30, 41, 54),
        "twist": {"id": "blackout", "name": "BLACKOUT",
                  "desc": "The yard is dark outside your light and the relay's. The relay surges to stun."},
        "goal": "protect", "target": 60.0, "relay": True,
        "spawn": {"grunt": 6, "slinger": 4, "brute": 3}, "interval": 1.00, "max_alive": 8, "boss": False,
        "intro": [
            "Relay Seven hums in the middle of the yard like something asleep.",
            "If it dies, forty thousand people wake up to no light and no water.",
            "They will ignore you and go for the relay. Make that a mistake.",
        ],
        "outro": [
            "The relay holds. Scorched, screaming, but lit.",
            "Then the yard goes cold, and the ash starts falling in a ring.",
            "The Warden has decided to handle this personally.",
        ],
    },
    {
        "name": "CHAPTER IV - THE WARDEN",
        "floor": (48, 41, 60),
        "twist": {"id": "ashring", "name": "ASH RING",
                  "desc": "The safe ground shrinks as the fight drags on. Ash outside the ring burns."},
        "goal": "boss", "target": 1, "relay": False,
        "spawn": {"grunt": 1}, "interval": 4.0, "max_alive": 4, "boss": True,
        "intro": [
            "It was a person once. It signed the same kind of contract you did.",
            "The Choir does not cut relays out of malice. They believe the light is a leash.",
            "You are not here to settle that argument. You are here to end this one.",
        ],
        "outro": [
            "The ring of ash lifts. Relay Seven throws light back across the yard.",
            "Somewhere north, three districts are still dark, and the Choir is still singing.",
            "But tonight Marrow Gate has power, and you are still standing in it.",
            "-- END OF ACT ONE --",
        ],
    },
]

# ----------------------------------------------------------------------------
# SPRITES  (procedural pixel-art, animated, cached)
#
# Everything is drawn into a small low-resolution surface and then scaled up
# with nearest-neighbour, which is what gives it the chunky hand-made pixel
# look of a real 2D game instead of smooth vector blobs. Each character gets
# a full animation set: idle bob, a run cycle with swinging legs and arms,
# an attack swing, and a hurt pose.
# ----------------------------------------------------------------------------
_SPR = {}
_ANIM = {}

PX = 2  # pixel scale factor


def _px_scale(s, f=PX):
    return pygame.transform.scale(s, (s.get_width() * f, s.get_height() * f))


def _rect(s, col, x, y, w, h):
    if w >= 1 and h >= 1:
        pygame.draw.rect(s, col, (round(x), round(y), max(1, round(w)), max(1, round(h))))


def _outline(s, col=(14, 15, 22)):
    """Wrap the sprite in a 1px dark silhouette so it separates from the floor."""
    w, h = s.get_size()
    out = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
    mask = pygame.mask.from_surface(s)
    sil = mask.to_surface(setcolor=col, unsetcolor=(0, 0, 0, 0))
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2), (0, 0), (2, 0), (0, 2), (2, 2)):
        out.blit(sil, (dx, dy))
    out.blit(s, (1, 1))
    return out


def _outline_shade(s, col, x, y, w, h, f=0.62):
    """Block plus a darker bottom edge -- cheap but reads as volume."""
    _rect(s, col, x, y, w, h)
    _rect(s, dark(col, f), x, y + h - 1, w, 1)


# --------------------------------------------------------------- WEAPON ART
def _weapon_surf(kind, acc):
    """Small weapon sprite pointing right, drawn once and rotated per frame."""
    key = "wp_%s_%s" % (kind, acc)
    if key in _SPR:
        return _SPR[key]
    steel = (206, 214, 232)
    wood = (132, 96, 66)
    if kind == "sword":
        s = pygame.Surface((16, 7), pygame.SRCALPHA)
        _rect(s, steel, 4, 3, 11, 2)
        _rect(s, lite(steel, 0.5), 4, 3, 11, 1)
        _rect(s, acc, 3, 1, 2, 5)
        _rect(s, dark(wood), 0, 3, 3, 2)
    elif kind == "dagger":
        s = pygame.Surface((11, 6), pygame.SRCALPHA)
        _rect(s, lite(steel, 0.3), 4, 2, 7, 2)
        _rect(s, acc, 3, 1, 1, 4)
        _rect(s, dark(wood), 0, 2, 3, 2)
    elif kind == "axe":
        s = pygame.Surface((14, 11), pygame.SRCALPHA)
        _rect(s, wood, 0, 5, 11, 2)
        pygame.draw.polygon(s, steel, [(9, 1), (14, 5), (14, 7), (9, 11)])
        pygame.draw.polygon(s, lite(steel, 0.45), [(9, 1), (13, 4), (10, 5)])
    elif kind == "bow":
        s = pygame.Surface((10, 18), pygame.SRCALPHA)
        pygame.draw.arc(s, wood, (0, 0, 10, 18), -1.45, 1.45, 2)
        pygame.draw.line(s, (228, 228, 232), (3, 2), (3, 16), 1)
    elif kind == "gun":
        s = pygame.Surface((14, 9), pygame.SRCALPHA)
        _rect(s, (72, 78, 96), 2, 2, 11, 3)
        _rect(s, lite((72, 78, 96), 0.3), 2, 2, 11, 1)
        _rect(s, dark(wood), 0, 4, 5, 4)
        _rect(s, acc, 10, 3, 2, 1)
    elif kind == "staff":
        s = pygame.Surface((8, 20), pygame.SRCALPHA)
        _rect(s, (104, 82, 128), 3, 4, 2, 16)
        pygame.draw.circle(s, acc, (4, 3), 3)
        pygame.draw.circle(s, lite(acc, 0.6), (3, 2), 1)
    else:
        s = pygame.Surface((12, 12), pygame.SRCALPHA)
        _rect(s, dark(acc, 0.8), 2, 2, 8, 8)
        _rect(s, acc, 2, 2, 8, 2)
    _SPR[key] = s
    return s


# --------------------------------------------------------------- HERO FRAMES
def _hero_frame(c, leg, arm, bob, swing, crouch=0):
    """One pose of a character, facing right. leg/arm are -1..1 swing phases."""
    s = pygame.Surface((22, 26), pygame.SRCALPHA)
    main, acc = c["colors"]
    skin = (234, 196, 160)
    boot = dark(main, 0.40)
    ty = 8 + bob + crouch          # torso top
    # --- legs (back leg first so the front one overlaps) ---
    back_x = 8 - leg * 3
    front_x = 10 + leg * 3
    leg_h = 6 - abs(leg) * 1.5
    _rect(s, dark(boot, 0.8), back_x, ty + 9, 3, leg_h)
    _rect(s, boot, back_x, ty + 9 + leg_h - 2, 4, 2)
    _rect(s, boot, front_x, ty + 9, 3, leg_h)
    _rect(s, dark(boot, 0.75), front_x, ty + 9 + leg_h - 2, 4, 2)
    # --- back arm ---
    _rect(s, dark(main, 0.7), 7 - arm * 2, ty + 2, 3, 5)
    # --- torso ---
    _outline_shade(s, main, 6, ty, 11, 10)
    _rect(s, acc, 6, ty, 11, 3)                 # chest band
    _rect(s, dark(acc, 0.7), 6, ty + 6, 11, 2)  # belt
    _rect(s, lite(main, 0.22), 6, ty, 2, 10)    # rim light on the front edge
    # --- head ---
    hy = ty - 7
    _rect(s, skin, 8, hy, 8, 7)
    _rect(s, dark(skin, 0.85), 8, hy + 6, 8, 1)
    _rect(s, acc, 7, hy - 2, 10, 3)             # helmet
    _rect(s, lite(acc, 0.35), 7, hy - 2, 10, 1)
    _rect(s, dark(acc, 0.6), 15, hy + 1, 2, 3)  # cheek guard
    _rect(s, (28, 28, 38), 11, hy + 3, 2, 2)    # eye
    # --- front arm + weapon ---
    ax = 14 + arm * 2
    _rect(s, lite(main, 0.1), ax, ty + 2, 3, 5)
    wp = _weapon_surf(c["weapon"], acc)
    if swing:
        wp = pygame.transform.rotate(wp, swing)
    wr = wp.get_rect(center=(int(ax + 5), int(ty + 4)))
    s.blit(wp, wr)
    return _px_scale(_outline(s))


def hero_anim(c):
    """dict of state -> list of frames, plus per-state frame duration."""
    key = "hero_" + c["id"]
    if key in _ANIM:
        return _ANIM[key]
    a = {
        "idle": [_hero_frame(c, 0, 0, 0, 0), _hero_frame(c, 0, 0, -1, 0),
                 _hero_frame(c, 0, 0, 0, 0), _hero_frame(c, 0, 0, 1, 0)],
        "run": [_hero_frame(c, 1.0, -1.0, -1, 0), _hero_frame(c, 0.5, -0.5, 0, 0),
                _hero_frame(c, 0.0, 0.0, 1, 0), _hero_frame(c, -0.5, 0.5, 0, 0),
                _hero_frame(c, -1.0, 1.0, -1, 0), _hero_frame(c, -0.5, 0.5, 0, 0)],
        "attack": [_hero_frame(c, 0, -0.8, 0, 48, 0), _hero_frame(c, 0, 1.0, -1, -30, 0),
                   _hero_frame(c, 0, 0.6, 0, -8, 0)],
        "hurt": [_hero_frame(c, -0.3, 0.4, 1, 10, 2)],
    }
    _ANIM[key] = a
    return a


def hero_sprite(c):
    """Kept for compatibility -- the neutral standing frame."""
    return hero_anim(c)["idle"][0]


# -------------------------------------------------------------- ENEMY FRAMES
ENEMY_LOOK = {
    "grunt": dict(col=(172, 76, 90), acc=(66, 22, 32), eye=(255, 126, 126), size=(18, 22), sc=2),
    "slinger": dict(col=(188, 132, 74), acc=(70, 44, 22), eye=(255, 176, 120), size=(17, 22), sc=2),
    "brute": dict(col=(132, 68, 134), acc=(48, 22, 54), eye=(255, 120, 200), size=(24, 27), sc=2),
    "warden": dict(col=(96, 62, 154), acc=(202, 92, 222), eye=(255, 226, 132), size=(30, 34), sc=3),
}


def _enemy_frame(kind, leg, arm, bob):
    lk = ENEMY_LOOK[kind]
    w, h = lk["size"]
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    col, acc, eye = lk["col"], lk["acc"], lk["eye"]
    cx = w // 2
    ty = h * 0.34 + bob
    body_w = w * 0.62
    # legs
    _rect(s, dark(acc, 0.85), cx - body_w * 0.42 - leg * 2, ty + h * 0.40, w * 0.15, h * 0.24)
    _rect(s, acc, cx + body_w * 0.10 + leg * 2, ty + h * 0.40, w * 0.15, h * 0.24)
    # back arm
    _rect(s, dark(col, 0.65), cx - body_w * 0.62 - arm * 2, ty + h * 0.10, w * 0.12, h * 0.22)
    # torso
    _outline_shade(s, col, cx - body_w / 2, ty, body_w, h * 0.42)
    _rect(s, acc, cx - body_w / 2, ty, body_w, h * 0.12)
    _rect(s, lite(col, 0.18), cx - body_w / 2, ty, 2, h * 0.42)
    # head
    hh = h * 0.22
    _rect(s, dark(col, 0.88), cx - w * 0.20, ty - hh, w * 0.40, hh)
    _rect(s, eye, cx - w * 0.14, ty - hh * 0.55, w * 0.09, 2)
    _rect(s, eye, cx + w * 0.05, ty - hh * 0.55, w * 0.09, 2)
    # front arm + kind-specific gear
    _rect(s, col, cx + body_w * 0.44 + arm * 2, ty + h * 0.10, w * 0.13, h * 0.22)
    if kind == "brute":
        _rect(s, (206, 210, 222), cx + body_w * 0.5, ty + h * 0.04, w * 0.20, h * 0.10)
    elif kind == "slinger":
        pygame.draw.arc(s, (150, 112, 74), (cx + body_w * 0.42, ty - 1, 7, h * 0.40), -1.4, 1.4, 2)
    elif kind == "warden":
        pygame.draw.polygon(s, (226, 206, 255),
                            [(cx, ty - hh - 5), (cx - w * 0.18, ty - hh), (cx + w * 0.18, ty - hh)])
        _rect(s, acc, cx - body_w / 2 - 2, ty + h * 0.16, body_w + 4, 2)
    return _px_scale(_outline(s), lk["sc"])


def enemy_anim(kind):
    key = "en_" + kind
    if key in _ANIM:
        return _ANIM[key]
    a = {
        "idle": [_enemy_frame(kind, 0, 0, 0), _enemy_frame(kind, 0, 0, -1)],
        "run": [_enemy_frame(kind, 1.0, -1.0, -1), _enemy_frame(kind, 0.4, -0.4, 0),
                _enemy_frame(kind, -1.0, 1.0, -1), _enemy_frame(kind, -0.4, 0.4, 0)],
        "attack": [_enemy_frame(kind, 0, -1.4, 1), _enemy_frame(kind, 0, 1.6, -1)],
    }
    _ANIM[key] = a
    return a


def enemy_sprite(kind):
    return enemy_anim(kind)["idle"][0]


class Anim:
    """Tiny state machine that walks through a frame list."""

    def __init__(self, table, state="idle", fps=10.0):
        self.table = table
        self.state = state
        self.fps = fps
        self.t = 0.0
        self.lock = 0.0          # while >0 the state cannot be changed

    def set(self, state, fps=None, lock=0.0):
        if self.lock > 0 or state == self.state:
            if state == self.state and fps:
                self.fps = fps
            return
        self.state = state
        self.t = 0.0
        self.lock = lock
        if fps:
            self.fps = fps

    def update(self, dt):
        self.t += dt
        self.lock = max(0.0, self.lock - dt)

    @property
    def frame(self):
        fr = self.table.get(self.state) or self.table["idle"]
        return fr[int(self.t * self.fps) % len(fr)]


# ----------------------------------------------------------------------------
# ARENA BACKGROUND  (tile map baked once)
# ----------------------------------------------------------------------------
_BG_CACHE = {}

TILE = 48
FLOOR_BASE = (44, 48, 63)


def build_arena(seed=7, floor=None):
    """Bake the whole arena floor + walls into one surface."""
    floor = floor or FLOOR_BASE
    key = "arena_%d" % seed
    if key in _BG_CACHE:
        return _BG_CACHE[key]
    rng = random.Random(seed)
    sf = pygame.Surface((W, H))
    sf.fill(BG)

    # ---- floor tiles -------------------------------------------------------
    for ty in range(ARENA.top, ARENA.bottom, TILE):
        for tx in range(ARENA.left, ARENA.right, TILE):
            w = min(TILE, ARENA.right - tx)
            h = min(TILE, ARENA.bottom - ty)
            # gentle checker + small jitter: cohesive stone, not a noise field
            checker = 3 if ((tx // TILE) + (ty // TILE)) % 2 == 0 else -3
            j = rng.randint(-2, 2) + checker
            base = [clamp(v + j, 0, 255) for v in floor]
            pygame.draw.rect(sf, base, (tx, ty, w, h))
            # bevel: lit top/left edge, shadowed bottom/right -> tiles read as stone
            pygame.draw.line(sf, lite(base, 0.10), (tx, ty), (tx + w - 1, ty))
            pygame.draw.line(sf, lite(base, 0.10), (tx, ty), (tx, ty + h - 1))
            pygame.draw.line(sf, dark(base, 0.72), (tx, ty + h - 1), (tx + w - 1, ty + h - 1))
            pygame.draw.line(sf, dark(base, 0.72), (tx + w - 1, ty), (tx + w - 1, ty + h - 1))
            # surface detail: speckle, cracks, the occasional drain grate
            for _ in range(rng.randint(2, 6)):
                sx = tx + rng.randrange(3, max(4, w - 3))
                sy = ty + rng.randrange(3, max(4, h - 3))
                pygame.draw.rect(sf, dark(base, 0.86), (sx, sy, 2, 2))
            if rng.random() < 0.13:
                x0 = tx + rng.randrange(6, max(7, w - 6))
                y0 = ty + rng.randrange(6, max(7, h - 6))
                pts = [(x0, y0)]
                for _ in range(3):
                    x0 += rng.randint(-7, 7)
                    y0 += rng.randint(-7, 7)
                    pts.append((x0, y0))
                pygame.draw.lines(sf, dark(base, 0.66), False, pts, 1)
            if rng.random() < 0.015:
                gx, gy = tx + w // 2, ty + h // 2
                pygame.draw.rect(sf, (28, 31, 42), (gx - 9, gy - 7, 18, 14), border_radius=2)
                for i in range(4):
                    pygame.draw.line(sf, (18, 20, 28), (gx - 7, gy - 5 + i * 3), (gx + 7, gy - 5 + i * 3))

    # ---- scenery: crates, barrels, rubble ----------------------------------
    spots = []
    for _ in range(11):
        for _try in range(30):
            px = rng.randint(ARENA.left + 40, ARENA.right - 40)
            py = rng.randint(ARENA.top + 40, ARENA.bottom - 40)
            if abs(px - ARENA.centerx) < 90 and abs(py - ARENA.centery) < 90:
                continue          # keep the middle clear for fighting
            if all(math.hypot(px - sx, py - sy) > 90 for sx, sy in spots):
                spots.append((px, py))
                break
    for (px, py) in spots:
        kind = rng.random()
        sw = 34 if kind < 0.42 else (28 if kind < 0.72 else 36)
        sh = pygame.Surface((sw, 11), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 65), (0, 0, sw, 11))
        sf.blit(sh, (px - sw / 2, py - 3))
        if kind < 0.42:                                   # crate
            wd, hd = 30, 26
            pygame.draw.rect(sf, (104, 78, 52), (px - wd // 2, py - hd, wd, hd))
            pygame.draw.rect(sf, (126, 96, 64), (px - wd // 2, py - hd, wd, 5))
            pygame.draw.rect(sf, (72, 54, 36), (px - wd // 2, py - hd, wd, hd), 2)
            pygame.draw.line(sf, (78, 58, 38), (px - wd // 2, py - hd), (px + wd // 2, py), 2)
            pygame.draw.line(sf, (78, 58, 38), (px + wd // 2, py - hd), (px - wd // 2, py), 2)
        elif kind < 0.72:                                 # barrel
            pygame.draw.rect(sf, (74, 88, 96), (px - 12, py - 30, 24, 30), border_radius=5)
            pygame.draw.rect(sf, (96, 114, 124), (px - 12, py - 30, 24, 6), border_radius=3)
            pygame.draw.rect(sf, (48, 58, 66), (px - 12, py - 22, 24, 3))
            pygame.draw.rect(sf, (48, 58, 66), (px - 12, py - 11, 24, 3))
        else:                                             # rubble pile
            for _ in range(7):
                rx = px + rng.randint(-16, 16)
                ry = py + rng.randint(-8, 2)
                s2 = rng.randint(4, 9)
                pygame.draw.rect(sf, (62, 68, 86), (rx, ry - s2, s2, s2))
                pygame.draw.rect(sf, (84, 92, 114), (rx, ry - s2, s2, 2))

    # ---- overhead light pool: bright in the middle, dim at the edges -------
    light = pygame.Surface((ARENA.w, ARENA.h), pygame.SRCALPHA)
    cx, cy = ARENA.w / 2, ARENA.h * 0.42
    maxd = math.hypot(cx, cy)
    for ry in range(0, ARENA.h, 4):
        for rx in range(0, ARENA.w, 4):
            t = math.hypot(rx - cx, ry - cy) / maxd
            if t < 1:
                pygame.draw.rect(light, (255, 246, 214, int(16 * (1 - t) ** 2)), (rx, ry, 4, 4))
            else:
                pygame.draw.rect(light, (0, 0, 20, int(50 * min(1, (t - 1) * 3))), (rx, ry, 4, 4))
    sf.blit(light, (ARENA.left, ARENA.top))

    # ---- scorch marks + moss so the floor isn't uniform ---------------------
    for _ in range(14):
        cx = rng.randint(ARENA.left + 20, ARENA.right - 20)
        cy = rng.randint(ARENA.top + 20, ARENA.bottom - 20)
        r = rng.randint(10, 26)
        blot = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        col = (30, 46, 38) if rng.random() < 0.5 else (24, 24, 30)
        for _ in range(9):
            pygame.draw.circle(blot, (*col, 46), (rng.randrange(r // 2, r + r // 2),
                                                  rng.randrange(r // 2, r + r // 2)),
                               rng.randint(4, r // 2 + 3))
        sf.blit(blot, (cx - r, cy - r))

    # ---- wall ring: face + lit cap, so the arena has real edges ------------
    wall_t = 14
    outer = ARENA.inflate(wall_t * 2, wall_t * 2)
    # draw the ring as four bands so the floor underneath survives
    for band in (pygame.Rect(outer.left, outer.top, outer.w, wall_t),
                 pygame.Rect(outer.left, outer.bottom - wall_t, outer.w, wall_t),
                 pygame.Rect(outer.left, outer.top, wall_t, outer.h),
                 pygame.Rect(outer.right - wall_t, outer.top, wall_t, outer.h)):
        pygame.draw.rect(sf, (44, 49, 68), band)
    # brick seams around the ring
    for x in range(outer.left, outer.right, 24):
        pygame.draw.line(sf, (34, 38, 54), (x, outer.top), (x, outer.top + wall_t))
        pygame.draw.line(sf, (34, 38, 54), (x, outer.bottom - wall_t), (x, outer.bottom))
    for y in range(outer.top, outer.bottom, 24):
        pygame.draw.line(sf, (34, 38, 54), (outer.left, y), (outer.left + wall_t, y))
        pygame.draw.line(sf, (34, 38, 54), (outer.right - wall_t, y), (outer.right, y))
    pygame.draw.rect(sf, (72, 80, 106), outer, 2, border_radius=3)
    pygame.draw.line(sf, (96, 106, 136), (outer.left + 2, outer.top + 1), (outer.right - 2, outer.top + 1), 2)
    # inner lip shadow cast onto the floor
    shadow = pygame.Surface((ARENA.w, 16), pygame.SRCALPHA)
    for i in range(16):
        pygame.draw.line(shadow, (0, 0, 0, int(80 * (1 - i / 16))), (0, i), (ARENA.w, i))
    sf.blit(shadow, (ARENA.left, ARENA.top))

    _BG_CACHE[key] = sf
    return sf


def build_vignette():
    if "vig" in _BG_CACHE:
        return _BG_CACHE["vig"]
    v = pygame.Surface((W, H), pygame.SRCALPHA)
    steps = 26
    for i in range(steps):
        a = int(70 * (i / steps) ** 2)
        pygame.draw.rect(v, (0, 0, 0, a), (i * 2, i * 2, W - i * 4, H - i * 4), 3, border_radius=8)
    _BG_CACHE["vig"] = v
    return v


_LIGHT = {}


def get_light(radius):
    """Soft round light mask (alpha = how much darkness it removes). Cached."""
    radius = max(20, int(round(radius / 20.0)) * 20)
    if radius not in _LIGHT:
        sp = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for r in range(radius, 0, -2):
            a = int(255 * (1 - r / radius) ** 0.75)
            pygame.draw.circle(sp, (0, 0, 0, a), (radius, radius), r)
        _LIGHT[radius] = sp
    return _LIGHT[radius]


# ----------------------------------------------------------------------------
# PARTICLES
# ----------------------------------------------------------------------------
class Particle:
    __slots__ = ("pos", "vel", "life", "maxlife", "col", "size", "grav", "kind")

    def __init__(self, pos, vel, life, col, size=3, grav=0.0, kind="spark"):
        self.pos = V2(pos)
        self.vel = V2(vel)
        self.life = life
        self.maxlife = life
        self.col = col
        self.size = size
        self.grav = grav
        self.kind = kind

    def update(self, dt):
        self.pos += self.vel * dt
        self.vel *= 0.90
        self.vel.y += self.grav * dt
        self.life -= dt

    def draw(self, sf):
        a = clamp(self.life / self.maxlife, 0, 1)
        if self.kind == "smoke":
            r = self.size * (1.8 - a)
            s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*self.col, int(90 * a)), (r + 1, r + 1), r)
            sf.blit(s, (self.pos.x - r, self.pos.y - r))
        else:
            # additive glow: a soft halo behind a bright core reads as light
            # rather than a flat colored square, and it's cheap since the
            # halo surface is tiny.
            sz = max(1, int(self.size * a))
            gr = sz + 3
            g = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
            pygame.draw.circle(g, (*lite(self.col, 0.5), int(150 * a)), (gr, gr), gr)
            pygame.draw.circle(g, (*self.col, 255), (gr, gr), max(1, sz // 2 + 1))
            sf.blit(g, (self.pos.x - gr, self.pos.y - gr), special_flags=pygame.BLEND_RGBA_ADD)


# ----------------------------------------------------------------------------
# ITEMS / INVENTORY / PICKUPS
# Adding a potion = one entry in ITEMS plus its effect in Game.use_item (and, if
# it is a timed buff, a hook in Player). ITEM_ORDER sets belt order and 1-5 keys.
# ----------------------------------------------------------------------------
ITEM_BLUE = (110, 150, 240)
ITEMS = {
    "heal": dict(name="HEALING POTION", tag="HEAL", col=RED, cap=4, weight=30, dur=0.0,
                 desc="Restores 40% of max HP instantly."),
    "speed": dict(name="SWIFTNESS POTION", tag="SPEED", col=CYAN, cap=3, weight=20, dur=9.0,
                  desc="+35% move speed for 9 seconds."),
    "strength": dict(name="STRENGTH POTION", tag="STRENGTH", col=ORANGE, cap=3, weight=20, dur=10.0,
                     desc="+40% damage dealt for 10 seconds."),
    "ward": dict(name="WARD POTION", tag="WARD", col=ITEM_BLUE, cap=3, weight=16, dur=8.0,
                 desc="Halves all damage taken for 8 seconds."),
    "focus": dict(name="FOCUS POTION", tag="FOCUS", col=PURPLE, cap=3, weight=14, dur=10.0,
                  desc="Skills and dodge recharge 2.5x faster for 10s."),
}
ITEM_ORDER = ["heal", "speed", "strength", "ward", "focus"]
POTION_KEYS = (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5)
DROP_BASE = {"grunt": 0.10, "slinger": 0.14, "brute": 0.35}   # per-kill drop chance
DROP_PITY = 0.025      # extra chance per kill since the last drop
DROP_GUARANTEE = 12    # kills without a drop before one is guaranteed


class Inventory:
    """The bag: a count per item id, each capped by ITEMS[id]['cap']."""

    def __init__(self, items=None):
        self.n = {k: 0 for k in ITEM_ORDER}
        if items:
            for k, v in items.items():
                self.n[k] = min(v, ITEMS[k]["cap"])

    def copy(self):
        return Inventory(self.n)

    def count(self, iid):
        return self.n.get(iid, 0)

    def room(self, iid):
        return self.n[iid] < ITEMS[iid]["cap"]

    def add(self, iid):
        if not self.room(iid):
            return False
        self.n[iid] += 1
        return True

    def take(self, iid):
        if self.n.get(iid, 0) <= 0:
            return False
        self.n[iid] -= 1
        return True


def potion_sprite(iid, scale=2):
    """Little pixel-art flask, tinted per item, with a mark on the liquid."""
    key = "potion_%s_%d" % (iid, scale)
    if key in _SPR:
        return _SPR[key]
    col = ITEMS[iid]["col"]
    s = pygame.Surface((11, 14), pygame.SRCALPHA)
    glass = (204, 220, 236)
    pygame.draw.rect(s, (150, 106, 64), (4, 0, 3, 2))          # cork
    pygame.draw.rect(s, glass, (4, 2, 3, 3))                    # neck
    pygame.draw.ellipse(s, glass, (0, 4, 11, 10))               # glass body
    pygame.draw.ellipse(s, dark(col, 0.8), (1, 6, 9, 7))        # liquid (shaded)
    pygame.draw.ellipse(s, col, (2, 7, 7, 5))                   # liquid (lit)
    pygame.draw.rect(s, (255, 255, 255), (2, 8, 1, 2))          # glint
    W_ = (255, 255, 255)
    marks = {
        "heal": [(5, 7, 1, 4), (4, 8, 3, 1)],
        "speed": [(4, 8, 1, 1), (5, 9, 1, 1), (4, 10, 1, 1), (6, 8, 1, 1), (7, 9, 1, 1), (6, 10, 1, 1)],
        "strength": [(5, 7, 1, 4), (4, 8, 1, 1), (6, 8, 1, 1)],
        "ward": [(4, 8, 3, 2), (5, 10, 1, 1)],
        "focus": [(4, 8, 3, 1), (4, 10, 3, 1), (4, 9, 1, 1), (6, 9, 1, 1)],
    }
    for r in marks.get(iid, []):
        pygame.draw.rect(s, W_, r)
    out = _px_scale(_outline(s), scale)
    _SPR[key] = out
    return out


class Pickup:
    """A potion lying on the floor. Pops out of the kill, bobs, then expires."""
    LIFE = 18.0

    def __init__(self, pos, iid):
        self.pos = V2(pos)
        self.iid = iid
        a = random.uniform(0, math.tau)
        self.vel = V2(math.cos(a), math.sin(a)) * random.uniform(180, 260)
        self.age = 0.0
        self.phase = random.uniform(0, math.tau)

    def draw(self, sf, tnow, near_full=False, font=None):
        if self.age > Pickup.LIFE - 4.0 and int(self.age * 8) % 2 == 0:
            return                                   # blink out near expiry
        it = ITEMS[self.iid]
        col = it["col"]
        bob = math.sin(tnow * 4 + self.phase) * 3
        sh = pygame.Surface((26, 9), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 70), (0, 0, 26, 9))
        sf.blit(sh, (self.pos.x - 13, self.pos.y - 2))
        gr = 26 + int(3 * math.sin(tnow * 5 + self.phase))
        glow = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*col, 38), (gr, gr), gr)
        pygame.draw.circle(glow, (*col, 62), (gr, gr), int(gr * 0.55))
        sf.blit(glow, (self.pos.x - gr, self.pos.y - 12 + bob - gr))
        spr = potion_sprite(self.iid)
        sf.blit(spr, (self.pos.x - spr.get_width() / 2, self.pos.y - spr.get_height() + 2 + bob))
        if near_full and font is not None:
            im = font.render("BAG FULL", True, lite(col, 0.4))
            sf.blit(im, (self.pos.x - im.get_width() / 2, self.pos.y - 52 + bob))


# ----------------------------------------------------------------------------
# ENTITIES
# ----------------------------------------------------------------------------
class Projectile:
    def __init__(self, pos, vel, dmg, owner, color, radius=5, pierce=0, life=2.2,
                 slow=0.0, stun=0.0, kind="bolt"):
        self.pos = V2(pos)
        self.vel = V2(vel)
        self.dmg = dmg
        self.owner = owner
        self.color = color
        self.radius = radius
        self.pierce = pierce
        self.life = life
        self.slow = slow
        self.stun = stun
        self.kind = kind
        self.hit = set()
        self.dead = False
        self.start = V2(pos)

    def update(self, dt):
        self.pos += self.vel * dt
        self.life -= dt
        if self.life <= 0 or not ARENA.inflate(60, 60).collidepoint(self.pos):
            self.dead = True

    def draw(self, sf):
        if self.kind == "arrow":
            d = norm(self.vel) * 11
            pygame.draw.line(sf, self.color, self.pos - d, self.pos + d, 3)
        else:
            pygame.draw.circle(sf, lite(self.color, 0.4), self.pos, self.radius + 2)
            pygame.draw.circle(sf, self.color, self.pos, self.radius)


class Zone:
    """Frost field / smoke cloud."""

    def __init__(self, pos, radius, life, kind, slow=0.4, dps=0.0, color=CYAN):
        self.pos = V2(pos)
        self.radius = radius
        self.life = life
        self.maxlife = life
        self.kind = kind
        self.slow = slow
        self.dps = dps
        self.color = color
        self.dead = False

    def update(self, dt):
        self.life -= dt
        if self.life <= 0:
            self.dead = True

    def draw(self, sf):
        a = clamp(self.life / self.maxlife, 0, 1)
        # additive under-glow first, so frost/smoke fields actually cast
        # light onto the floor instead of reading as a flat translucent disc
        glow = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow, (*self.color, int(70 * a)), (self.radius, self.radius), self.radius)
        sf.blit(glow, (self.pos.x - self.radius, self.pos.y - self.radius),
                special_flags=pygame.BLEND_RGBA_ADD)
        surf = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*self.color, int(60 * a)), (self.radius, self.radius), self.radius)
        pygame.draw.circle(surf, (*self.color, int(140 * a)), (self.radius, self.radius), self.radius, 2)
        sf.blit(surf, (self.pos.x - self.radius, self.pos.y - self.radius))


class Mine:
    def __init__(self, pos, dmg):
        self.pos = V2(pos)
        self.dmg = dmg
        self.arm = 0.6
        self.dead = False
        self.t = 0.0

    def update(self, dt):
        self.arm = max(0.0, self.arm - dt)
        self.t += dt

    def draw(self, sf):
        col = YELLOW if self.arm <= 0 else DGREY
        pygame.draw.circle(sf, dark(col), self.pos, 9)
        r = 4 + (2 if math.sin(self.t * 8) > 0 and self.arm <= 0 else 0)
        pygame.draw.circle(sf, col, self.pos, r)


class Relay:
    def __init__(self, pos):
        self.pos = V2(pos)
        self.hp = 1100
        self.maxhp = 1100
        self.t = 0.0

    def draw(self, sf):
        self.t += 1 / FPS
        pulse = 4 + math.sin(self.t * 3) * 3
        # soft additive bloom under the relay so it reads as a genuine light
        # source in the yard rather than a flat cyan icon
        br = 70 + pulse * 2
        bloom = pygame.Surface((br * 2, br * 2), pygame.SRCALPHA)
        pygame.draw.circle(bloom, (*CYAN, 40), (br, br), br)
        pygame.draw.circle(bloom, (*CYAN, 70), (br, br), int(br * 0.55))
        sf.blit(bloom, (self.pos.x - br, self.pos.y - br), special_flags=pygame.BLEND_RGBA_ADD)
        pygame.draw.circle(sf, (40, 60, 80), self.pos, 46 + pulse, 2)
        pygame.draw.rect(sf, (54, 62, 86), (self.pos.x - 22, self.pos.y - 14, 44, 40), border_radius=6)
        pygame.draw.polygon(sf, CYAN, [
            (self.pos.x, self.pos.y - 44), (self.pos.x - 16, self.pos.y - 10),
            (self.pos.x, self.pos.y + 2), (self.pos.x + 16, self.pos.y - 10)])
        pygame.draw.polygon(sf, lite(CYAN, 0.5), [
            (self.pos.x, self.pos.y - 44), (self.pos.x - 16, self.pos.y - 10),
            (self.pos.x, self.pos.y + 2), (self.pos.x + 16, self.pos.y - 10)], 2)
        bw = 80
        pygame.draw.rect(sf, (30, 34, 46), (self.pos.x - bw / 2, self.pos.y + 32, bw, 7), border_radius=3)
        pygame.draw.rect(sf, CYAN, (self.pos.x - bw / 2, self.pos.y + 32,
                                    bw * clamp(self.hp / self.maxhp, 0, 1), 7), border_radius=3)


class Enemy:
    STATS = {
        "grunt": dict(hp=46, speed=112, dmg=9, cd=0.9, rad=17, touch=True),
        "slinger": dict(hp=34, speed=88, dmg=10, cd=1.7, rad=16, touch=False),
        "brute": dict(hp=165, speed=74, dmg=20, cd=1.5, rad=24, touch=True),
        "warden": dict(hp=1250, speed=92, dmg=16, cd=1.5, rad=32, touch=True),
    }

    def __init__(self, kind, pos, scale=1.0, dmg_mult=1.0):
        st = Enemy.STATS[kind]
        self.kind = kind
        self.pos = V2(pos)
        self.maxhp = st["hp"] * scale
        self.hp = self.maxhp
        self.speed = st["speed"]
        self.dmg = st["dmg"] * dmg_mult
        self.cd = st["cd"]
        self.rad = st["rad"]
        self.touch = st["touch"]
        self.timer = random.uniform(0.2, 0.8)
        self.stun = 0.0
        self.slow_t = 0.0
        self.slow_f = 1.0
        self.flash = 0.0
        self.dead = False
        self.kb = V2(0, 0)
        self.windup = 0.0
        self.windup_max = 0.0
        self.strike_relay = False
        self.anim = Anim(enemy_anim(kind), "idle", 8.0)
        self.face = -1
        self.spr = self.anim.frame
        self.dust_t = 0.0
        self.phase_marks = [0.66, 0.33]
        self.charge = 0.0
        self.charge_dir = V2(1, 0)
        self.bob = random.uniform(0, 6.0)
        self.relay_hunter = random.random() < 0.55

    def hurt(self, amount, slow=0.0, stun=0.0, kb=None):
        self.hp -= amount
        self.flash = 0.12
        if slow > 0:
            self.slow_t = max(self.slow_t, slow)
            self.slow_f = 0.5
        if stun > 0:
            self.stun = max(self.stun, stun)
        if kb is not None:
            self.kb += kb
        if self.hp <= 0:
            self.dead = True

    def update(self, dt, g):
        prev = V2(self.pos)
        self._update(dt, g)
        self._anim_step(dt, g, prev)

    def _anim_step(self, dt, g, prev):
        moved = (self.pos - prev).length()
        if abs(self.pos.x - prev.x) > 0.4:
            self.face = 1 if self.pos.x > prev.x else -1
        self.anim.update(dt)
        if self.stun > 0:
            self.anim.set("idle", 4.0)
        elif moved > 0.35:
            self.anim.set("run", 9.0 + min(6.0, moved * 40))
            # kick up dust while running
            self.dust_t -= dt
            if self.dust_t <= 0:
                self.dust_t = 0.16
                g.fx_dust(self.pos + V2(0, self.rad * 0.6), 1, (58, 62, 80))
        else:
            self.anim.set("idle", 5.0)
        self.spr = self.anim.frame

    def swing_anim(self):
        self.anim.set("attack", 12.0, lock=0.18)

    def _resolve_strike(self, g):
        """Fired when the wind-up finishes -- a dodged blow now actually misses."""
        if self.strike_relay and g.relay is not None and g.relay.hp > 0:
            if self.pos.distance_to(g.relay.pos) <= self.rad + 60:
                g.relay.hp -= self.dmg
                g.fx_hit(g.relay.pos, self.dmg, RED)
            return
        if self.pos.distance_to(g.player.pos) <= self.rad + 42:
            g.player.hurt(self.dmg, g)
            g.shake = max(g.shake, 5)
        else:
            g.fx_dust(self.pos + norm(g.player.pos - self.pos) * self.rad, 3, (90, 96, 118))

    def _update(self, dt, g):
        self.bob += dt
        self.flash = max(0.0, self.flash - dt)
        self.timer -= dt
        if self.slow_t > 0:
            self.slow_t -= dt
            if self.slow_t <= 0:
                self.slow_f = 1.0
        if self.kb.length_squared() > 1:
            self.pos += self.kb * dt
            self.kb *= 0.86
        if self.stun > 0:
            self.stun -= dt
            self.windup = 0.0            # getting stunned cancels the swing
            return

        if self.windup > 0:
            self.windup -= dt
            if self.windup <= 0:
                self._resolve_strike(g)
            return                        # rooted during the tell

        mult = self.slow_f
        for z in g.zones:
            if z.pos.distance_to(self.pos) < z.radius:
                mult *= (1 - z.slow)
                if z.dps:
                    self.hurt(z.dps * dt)

        # pick a target: relay if it exists and is closer-ish, else the player
        target = g.player.pos
        aggro_relay = False
        if g.relay is not None and g.relay.hp > 0 and self.relay_hunter:
            if self.pos.distance_to(g.relay.pos) < self.pos.distance_to(g.player.pos) + 60:
                target = g.relay.pos
                aggro_relay = True
        if g.player.stealth > 0 and not aggro_relay:
            target = self.pos + V2(math.cos(self.bob), math.sin(self.bob * 0.7)) * 60

        d = target - self.pos
        dist = d.length()

        if self.kind == "warden":
            self._warden(dt, g, d, dist, mult)
            return

        if self.kind == "slinger":
            blinded = any(z.kind == "smoke" and z.pos.distance_to(self.pos) < z.radius for z in g.zones)
            if dist > 300:
                self.pos += norm(d) * self.speed * mult * dt
            elif dist < 210:
                self.pos -= norm(d) * self.speed * mult * dt
            if self.timer <= 0 and not blinded and dist < 420 and not aggro_relay:
                self.timer = self.cd
                self.swing_anim()
                g.projectiles.append(Projectile(self.pos, norm(d) * 290, self.dmg, "enemy", ORANGE, 6))
            elif self.timer <= 0 and aggro_relay and dist < 200:
                self.timer = self.cd
                g.relay.hp -= self.dmg
                g.fx_hit(g.relay.pos, self.dmg, ORANGE)
            return

        if dist > (self.rad + 22):
            self.pos += norm(d) * self.speed * mult * dt
        elif self.timer <= 0:
            self.timer = self.cd
            self.swing_anim()
            self.strike_relay = aggro_relay
            self.windup = 0.34 if self.kind != "brute" else 0.52
            self.windup_max = self.windup

    def _warden(self, dt, g, d, dist, mult):
        for m in self.phase_marks[:]:
            if self.hp / self.maxhp < m:
                self.phase_marks.remove(m)
                for i in range(4):
                    a = i * math.pi / 2
                    g.enemies.append(Enemy("grunt", self.pos + V2(math.cos(a), math.sin(a)) * 90, g.scale))
                g.banner("THE WARDEN CALLS THE CHOIR", 2.0)

        if self.charge > 0:
            self.charge -= dt
            self.pos += self.charge_dir * 380 * dt
            if dist < 60:
                g.player.hurt(self.dmg, g)
                self.charge = 0
            return

        if dist > 90:
            self.pos += norm(d) * self.speed * mult * dt
        if self.timer <= 0:
            self.timer = self.cd
            roll = random.random()
            if roll < 0.4:
                self.charge = 0.45
                self.charge_dir = norm(d)
                g.banner("WARDEN CHARGES", 0.8)
            elif roll < 0.8:
                for i in range(12):
                    a = i * math.tau / 12 + random.uniform(-0.1, 0.1)
                    g.projectiles.append(Projectile(self.pos, V2(math.cos(a), math.sin(a)) * 225,
                                                    11, "enemy", PURPLE, 7))
            else:
                if dist < 110:
                    g.player.hurt(self.dmg, g)

    def draw(self, sf):
        spr = self.spr
        r = spr.get_rect()
        if self.face > 0:
            spr = pygame.transform.flip(spr, True, False)

        # soft contact shadow, tighter when the sprite is at the top of its bob
        sw = r.w * 0.60
        shadow = pygame.Surface((sw, 9), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 105), (0, 0, sw, 9))
        sf.blit(shadow, (self.pos.x - sw / 2, self.pos.y + r.h * 0.34))

        if self.flash > 0:
            tmp = spr.copy()
            k = int(210 * clamp(self.flash / 0.12, 0, 1))
            tmp.fill((k, k, k), None, pygame.BLEND_RGB_ADD)
            spr = tmp
        if self.charge > 0:                       # warden charge = motion streak
            ghost = spr.copy()
            ghost.set_alpha(70)
            sf.blit(ghost, (self.pos.x - r.w / 2 - self.charge_dir.x * 16,
                            self.pos.y - r.h / 2 - self.charge_dir.y * 16))
        sf.blit(spr, (self.pos.x - r.w / 2, self.pos.y - r.h / 2))

        if self.hp < self.maxhp:
            bw = max(26, r.w * 0.8)
            bx, by = self.pos.x - bw / 2, self.pos.y - r.h / 2 - 10
            pygame.draw.rect(sf, (12, 13, 18), (bx - 1, by - 1, bw + 2, 7), border_radius=2)
            pygame.draw.rect(sf, (48, 22, 28), (bx, by, bw, 5), border_radius=2)
            col = RED if self.kind != "warden" else PURPLE
            fw = bw * clamp(self.hp / self.maxhp, 0, 1)
            pygame.draw.rect(sf, col, (bx, by, fw, 5), border_radius=2)
            pygame.draw.rect(sf, lite(col, 0.45), (bx, by, fw, 2), border_radius=2)
        if self.windup > 0 and self.windup_max > 0:
            k = 1 - self.windup / self.windup_max      # 0 -> 1 as the blow lands
            d = norm(V2(self.face, 0) if self.face else V2(1, 0))
            # a red wedge that snaps shut on the strike frame
            tel = pygame.Surface((130, 130), pygame.SRCALPHA)
            pygame.draw.circle(tel, (235, 70, 70, int(40 + 90 * k)), (65, 65),
                               int(58 * (0.45 + 0.55 * k)), 3)
            sf.blit(tel, (self.pos.x - 65, self.pos.y - 65))
            pygame.draw.line(sf, (255, 150, 150),
                             (self.pos.x, self.pos.y - r.h / 2 - 20),
                             (self.pos.x + 26 * k - 13, self.pos.y - r.h / 2 - 20), 3)
        if self.stun > 0:
            for i in range(3):
                a = self.bob * 7 + i * math.tau / 3
                pygame.draw.circle(sf, YELLOW, (self.pos.x + math.cos(a) * 11,
                                                self.pos.y - r.h / 2 - 12 + math.sin(a) * 4), 2)


class Player:
    def __init__(self, c):
        self.c = c
        self.pos = V2(ARENA.center)
        self.maxhp = c["hp"]
        self.hp = self.maxhp
        self.aim = V2(1, 0)
        self.atk_t = 0.0
        self.cdq = 0.0
        self.cde = 0.0
        self.cdd = 0.0
        self.dash_t = 0.0
        self.dash_dir = V2(1, 0)
        self.iframe = 0.0
        self.stacks = 0
        self.stack_t = 0.0
        self.combo = 0
        self.stealth = 0.0
        self.empowered = False
        self.guard = 0.0
        self.speed_buff = 0.0
        self.ammo = 12
        self.reloading = 0.0
        self.kills = 0
        self.mines = []
        self.anim = Anim(hero_anim(c), "idle", 8.0)
        self.face = 1
        self.spr = self.anim.frame
        self.dust_t = 0.0
        self.step_t = 0.0
        self.lunge_t = 0.0
        self.lunge_dir = V2(1, 0)
        self.lunge_pow = 0.0
        self.trail = []          # afterimages during a dash
        self.muzzle = 0.0
        self.slash = 0.0
        self.slash_dir = V2(1, 0)
        self.dmg_taken = 0
        # timed potion buffs, seconds remaining (see ITEMS)
        self.pot = {k: 0.0 for k in ITEM_ORDER if ITEMS[k]["dur"] > 0}

    # ---- derived numbers -------------------------------------------------
    @property
    def hp_frac(self):
        return clamp(self.hp / self.maxhp, 0, 1)

    def move_speed(self):
        s = self.c["speed"]
        cid = self.c["id"]
        if cid == "garran":
            s *= 1 + 0.25 * (1 - self.hp_frac)
        if cid == "vex":
            s *= 1 + 0.06 * self.stacks
            if self.hp_frac < 0.35:
                s *= 0.75
        if self.speed_buff > 0:
            s *= 1.18
        if self.guard > 0:
            s *= 0.7
        if self.pot["speed"] > 0:
            s *= 1.35
        return s

    def dmg_mult(self, dist, target_frac=1.0):
        m = 1.0
        cid = self.c["id"]
        if cid == "vex":
            if target_frac < 0.40:
                m *= 1.6
            if self.hp_frac < 0.35:
                m *= 0.70
            if self.empowered:
                m *= 2.5
        elif cid == "bram":
            if self.hp_frac < 0.40:
                m *= 1.35
        elif cid == "sable":
            m *= 0.70 + clamp(dist / 520, 0, 1) * 0.90
        elif cid == "kite":
            m *= 1.25 - clamp(dist / 460, 0, 1) * 0.60
        elif cid == "nyx":
            m *= 1.50 - clamp(dist / 420, 0, 1) * 0.80
        if self.pot["strength"] > 0:
            m *= 1.40
        return m

    # ---- damage taken ----------------------------------------------------
    def hurt(self, amount, g):
        if self.iframe > 0 or self.dash_t > 0:
            return
        cid = self.c["id"]
        if cid == "garran":
            amount *= 1 - 0.45 * (1 - self.hp_frac)
        if self.guard > 0:
            amount *= 0.45
        if self.pot["ward"] > 0:
            amount *= 0.5
        amount = max(1, amount)
        self.hp -= amount
        self.dmg_taken += amount
        self.iframe = 0.35
        g.shake = max(g.shake, 8)
        g.punch = max(g.punch, 0.07)
        g.fx_hit(self.pos, int(amount), RED)

    def heal(self, v):
        self.hp = min(self.maxhp, self.hp + v)

    # ---- attacks ---------------------------------------------------------
    def melee_hit(self, g, reach, mult=1.0, arc=0.42, slow=0.0, stun=0.0, kb=0.0):
        hit_any = False
        acc = self.c["colors"][1]
        for e in g.enemies:
            d = e.pos - self.pos
            dist = d.length()
            if dist <= reach + e.rad and (arc >= 3.0 or self.aim.dot(norm(d)) > arc):
                dmg = self.c["dmg"] * mult * self.dmg_mult(dist, e.hp / e.maxhp)
                e.hurt(dmg, slow=slow, stun=stun, kb=norm(d) * kb if kb else None)
                g.fx_hit(e.pos, int(dmg), YELLOW if mult > 1.2 else WHITE)
                g.fx_spark(e.pos + norm(self.pos - e.pos) * e.rad * 0.6,
                           acc if mult <= 1.2 else lite(acc, 0.5), 9, 210)
                # brief freeze so the blow lands with weight
                g.hitstop = max(g.hitstop, 0.055 if mult <= 1.2 else 0.10)
                g.shake = max(g.shake, 5 if mult <= 1.2 else 10)
                g.punch = max(g.punch, 0.05 if mult <= 1.2 else 0.11)
                hit_any = True
                self.on_hit(e, g)
        return hit_any

    def on_hit(self, e, g):
        cid = self.c["id"]
        if cid == "vex":
            self.stacks = min(5, self.stacks + 1)
            self.stack_t = 3.0
            self.empowered = False
        elif cid == "sable":
            self.speed_buff = 1.2
        if e.dead:
            self.kills += 1

    def shoot(self, g, speed, dmg_mult=1.0, color=None, radius=5, pierce=0, kind="bolt",
              slow=0.0, stun=0.0, spread=0.0):
        col = color or self.c["colors"][1]
        a = math.atan2(self.aim.y, self.aim.x) + random.uniform(-spread, spread)
        v = V2(math.cos(a), math.sin(a)) * speed
        g.projectiles.append(Projectile(self.pos, v, self.c["dmg"] * dmg_mult, "player",
                                        col, radius, pierce, 2.4, slow, stun, kind))

    def attack(self, g):
        cid = self.c["id"]
        self.atk_t = self.c["atk_cd"]
        self.anim.set("attack", 16.0, lock=min(0.19, self.c["atk_cd"] * 0.7))
        if self.c["role"] == "MELEE":
            # only melee steps into the swing, which is what gives it weight
            self.lunge_t = 0.10
            self.lunge_dir = V2(self.aim)
            self.lunge_pow = 210.0
        else:
            # RANGED / MAGE / SUPPORT stay planted. Previously anything that
            # wasn't literally "RANGED" (Nyx = MAGE, Wisp = SUPPORT) fell into
            # the melee branch and stepped forward on every shot, and Sable /
            # Kite got a recoil shove that made them drift while firing.
            self.lunge_t = 0.0
            self.lunge_pow = 0.0
            if self.c["role"] == "RANGED":
                self.muzzle = 0.07
                # ejected casings (visual only, no movement)
                side = V2(-self.aim.y, self.aim.x)
                for _ in range(2):
                    g.particles.append(Particle(
                        self.pos + self.aim * 18,
                        side * random.uniform(40, 110) - self.aim * 40,
                        0.45, (214, 186, 110), 3, grav=420))
        self.slash = 0.18
        self.slash_dir = V2(self.aim)
        if cid in ("garran", "vex", "bram"):
            mult = 1.0
            slow = 0.0
            if cid == "bram":
                self.combo += 1
                if self.combo % 3 == 0:
                    mult, slow = 1.8, 1.5
                    g.banner("HEAVY", 0.5)
            self.melee_hit(g, self.c["rng"], mult, 0.30, slow=slow,
                           kb=140 if cid == "garran" else 60)
            if cid == "vex":
                self.empowered = False
        elif cid == "sable":
            self.shoot(g, 700, 1.0, (232, 226, 190), 4, pierce=0, kind="arrow")
        elif cid == "kite":
            if self.reloading > 0:
                return
            if self.ammo <= 0:
                self.reloading = 1.4
                return
            self.ammo -= 1
            self.shoot(g, 760, 1.0, YELLOW, 4, spread=0.05)
        elif cid == "nyx":
            self.shoot(g, 470, 1.0, PURPLE, 7, slow=0.4)
        elif cid == "wisp":
            self.shoot(g, 620, 1.0, (220, 230, 150), 4, spread=0.04, kind="arrow")

    def skill_q(self, g):
        cid = self.c["id"]
        role = self.c["role"]
        self.cdq = self.c["q"][2]
        acc = self.c["colors"][1]
        self.anim.lock = 0.0
        self.anim.set("attack", 14.0, lock=0.20)
        self.slash = 0.0
        # Telegraph flavor differs by role instead of one shared burst, so a
        # cast reads as "this class" before its unique payload even lands.
        if role == "MELEE":
            g.fx_ring(self.pos, acc, 60)
            g.fx_dust(self.pos, 5, dark(acc, 0.5))
            g.shake = max(g.shake, 6)
        elif role == "RANGED":
            g.fx_spark(self.pos + self.aim * 14, acc, 6, 140)
        elif role == "MAGE":
            g.fx_orbit(self.pos, acc, 10, 150)
            g.fx_ring(self.pos, lite(acc, 0.3), 40)
        else:  # SUPPORT
            g.fx_spark(self.pos, acc, 5, 120)
        if cid == "garran":
            start = V2(self.pos)
            self.dash_dir = V2(self.aim)
            self.dash_t = 0.30
            self.iframe = 0.30
            self.melee_hit(g, 110, 1.4, 0.0, stun=0.9, kb=200)
            g.fx_beam(start, start + self.aim * 130, lite(acc, 0.5), 0.14, 10)
            g.fx_spark(start + self.aim * 100, WHITE, 10, 260)
            g.banner("SHIELD BASH", 0.7)
        elif cid == "vex":
            start = V2(self.pos)
            g.fx_ring(start, PURPLE, 34)
            self.pos += self.aim * 190
            self.clamp_pos()
            g.fx_beam(start, self.pos, PURPLE, 0.14, 4)
            g.fx_dust(start, 6, dark(PURPLE, 0.6))
            g.fx_ring(self.pos, PURPLE, 50)
        elif cid == "bram":
            self.combo += 1
            self.melee_hit(g, 115, 1.25, 3.0, slow=0.8, kb=120)
            g.fx_orbit(self.pos, ORANGE, 14, 240, life=(0.22, 0.38))
            g.fx_ring(self.pos, ORANGE, 115)
        elif cid == "sable":
            g.projectiles.append(Projectile(self.pos, self.aim * 950, self.c["dmg"] * 1.9,
                                            "player", CYAN, 6, pierce=99, kind="arrow"))
            g.fx_beam(self.pos, self.pos + self.aim * 500, lite(CYAN, 0.4), 0.10, 2)
        elif cid == "kite":
            if self.reloading > 0:
                self.cdq = 0.1
                return
            self.ammo = max(0, self.ammo - 4)
            base = math.atan2(self.aim.y, self.aim.x)
            for i in range(6):
                a = base + (i - 2.5) * 0.10
                v = V2(math.cos(a), math.sin(a)) * random.uniform(640, 780)
                g.projectiles.append(Projectile(self.pos, v, self.c["dmg"] * 0.85,
                                                "player", ORANGE, 4, 0, 0.45))
            side = V2(-self.aim.y, self.aim.x)
            for _ in range(3):
                g.particles.append(Particle(
                    self.pos + self.aim * 16, side * random.uniform(-90, 90) - self.aim * 60,
                    0.4, (214, 186, 110), 3, grav=420))
            g.shake = max(g.shake, 6)
        elif cid == "nyx":
            g.zones.append(Zone(self.pos + self.aim * 150, 96, 4.5, "frost", 0.55,
                                self.c["dmg"] * 1.1, CYAN))
            g.fx_spark(self.pos + self.aim * 150, (200, 235, 245), 10, 90)
        elif cid == "wisp":
            if len(self.mines) >= 3:
                self.mines.pop(0)
            self.mines.append(Mine(self.pos, self.c["dmg"] * 5.5))
            g.fx_spark(self.pos, GREEN, 6, 90)
            g.fx_ring(self.pos, GREEN, 22)

    def skill_e(self, g):
        cid = self.c["id"]
        role = self.c["role"]
        self.cde = self.c["e"][2]
        acc = self.c["colors"][1]
        self.anim.lock = 0.0
        self.anim.set("attack", 14.0, lock=0.20)
        self.slash = 0.0
        if role == "MELEE":
            g.fx_ring(self.pos, acc, 70)
            g.fx_dust(self.pos, 6, dark(acc, 0.5))
            g.shake = max(g.shake, 7)
        elif role == "RANGED":
            g.fx_spark(self.pos + self.aim * 10, acc, 6, 140)
        elif role == "MAGE":
            g.fx_orbit(self.pos, acc, 12, 170)
            g.fx_ring(self.pos, lite(acc, 0.3), 44)
        else:  # SUPPORT
            g.fx_spark(self.pos, acc, 5, 120)
        if cid == "garran":
            self.guard = 3.0
            for e in g.enemies:
                if e.pos.distance_to(self.pos) < 200:
                    e.kb += norm(self.pos - e.pos) * 260
                    g.fx_beam(e.pos, self.pos, lite(acc, 0.4), 0.18, 3)
            g.fx_ring(self.pos, WHITE, 200)
            g.banner("BULWARK", 1.0)
        elif cid == "vex":
            g.fx_dust(self.pos, 10, dark(PURPLE, 0.5))
            self.stealth = 2.5
            self.empowered = True
            g.fx_ring(self.pos, dark(PURPLE, 0.7), 46)
        elif cid == "bram":
            best, bd = None, 1e9
            for e in g.enemies:
                d = e.pos - self.pos
                if d.length() < 280 and self.aim.dot(norm(d)) > 0.2 and d.length() < bd:
                    best, bd = e, d.length()
            if best:
                g.fx_beam(self.pos, best.pos, ORANGE, 0.16, 5)
                best.kb = norm(self.pos - best.pos) * 900
                best.hurt(self.c["dmg"] * 0.8, stun=0.8)
                g.fx_hit(best.pos, int(self.c["dmg"] * 0.8), ORANGE)
                g.fx_spark(best.pos, ORANGE, 10, 220)
        elif cid == "sable":
            start = V2(self.pos)
            self.dash_dir = -V2(self.aim)
            self.dash_t = 0.22
            self.iframe = 0.3
            self.speed_buff = 2.0
            g.fx_beam(start, start - self.aim * 90, lite(GREEN, 0.3), 0.14, 4)
        elif cid == "kite":
            self.dash_dir = V2(self.aim)
            self.dash_t = 0.22
            self.iframe = 0.3
            self.ammo = 12
            self.reloading = 0.0
            g.fx_orbit(self.pos, (214, 186, 110), 8, 140, life=(0.16, 0.3))
            g.fx_ring(self.pos, ORANGE, 40)
        elif cid == "nyx":
            for e in g.enemies:
                d = e.pos - self.pos
                if d.length() < 165:
                    dmg = self.c["dmg"] * 1.6
                    e.hurt(dmg, stun=1.0, kb=norm(d) * 420)
                    g.fx_hit(e.pos, int(dmg), CYAN)
                    self.on_hit(e, g)
            g.fx_ring(self.pos, CYAN, 165)
            g.fx_ring(self.pos, lite(CYAN, 0.4), 90)
            g.fx_orbit(self.pos, PURPLE, 16, 320, life=(0.3, 0.5))
            g.shake = max(g.shake, 10)
        elif cid == "wisp":
            g.zones.append(Zone(self.pos, 120, 5.5, "smoke", 0.35, 0.0, (170, 180, 190)))
            g.fx_dust(self.pos, 14, (150, 160, 150))

    def dash(self, g, mv=None):
        self.cdd = 2.2
        self.dash_t = 0.20
        self.iframe = 0.26
        # dodge where you are WALKING; only fall back to the cursor if standing still
        self.dash_dir = norm(mv) if (mv is not None and mv.length_squared() > 0) else V2(self.aim)
        self.anim.lock = 0.0
        self.anim.set("run", 16.0)
        g.fx_dust(self.pos + V2(0, 18), 5, dark(self.c["colors"][1], 0.55))

    def clamp_pos(self):
        self.pos.x = clamp(self.pos.x, ARENA.left + 18, ARENA.right - 18)
        self.pos.y = clamp(self.pos.y, ARENA.top + 20, ARENA.bottom - 20)

    def update(self, dt, g, mv, aim, firing, keys):
        prev = V2(self.pos)
        self._update(dt, g, mv, aim, firing, keys)
        self._anim_step(dt, g, prev, mv)

    def _anim_step(self, dt, g, prev, mv):
        self.muzzle = max(0.0, self.muzzle - dt)
        self.anim.update(dt)
        if abs(self.aim.x) > 0.15:
            self.face = 1 if self.aim.x > 0 else -1
        moved = (self.pos - prev).length()

        # dash leaves a fading afterimage trail
        if self.dash_t > 0:
            self.trail.append([V2(self.pos), 0.28])
        for t in self.trail[:]:
            t[1] -= dt
            if t[1] <= 0:
                self.trail.remove(t)

        if self.anim.lock > 0:
            pass
        elif moved > 0.4:
            self.anim.set("run", 11.0)
            self.step_t -= dt
            if self.step_t <= 0:
                self.step_t = 0.20
                g.fx_dust(self.pos + V2(0, 20), 2, (70, 76, 98))
        else:
            self.anim.set("idle", 5.0)
        self.spr = self.anim.frame

    def _update(self, dt, g, mv, aim, firing, keys):
        cid = self.c["id"]
        # NOTE: dash_t was missing from this list, so it never counted down.
        # After a single dash the player was stuck in dash movement forever and
        # WASD stopped steering -- that was the "can't move around" bug.
        for t in ("atk_t", "cdq", "cde", "cdd", "dash_t", "iframe", "slash",
                  "speed_buff", "guard", "stealth", "reloading", "stack_t"):
            setattr(self, t, max(0.0, getattr(self, t) - dt))
        for k in self.pot:
            self.pot[k] = max(0.0, self.pot[k] - dt)
        if self.pot["focus"] > 0:              # cooldowns tick 2.5x as fast
            extra = dt * 1.5
            self.cdq = max(0.0, self.cdq - extra)
            self.cde = max(0.0, self.cde - extra)
            self.cdd = max(0.0, self.cdd - extra)
        if self.stack_t <= 0:
            self.stacks = 0
        if cid == "wisp":
            self.heal(3.0 * dt)
        if cid == "kite":
            if self.reloading > 0 and self.reloading - dt <= 0:
                self.ammo = 12
            if keys[pygame.K_r] and self.ammo < 12 and self.reloading <= 0:
                self.reloading = 1.4

        if aim.length_squared() > 0:
            self.aim = norm(aim)

        if self.dash_t > 0:
            self.pos += self.dash_dir * self.move_speed() * 3.1 * dt
        elif mv.length_squared() > 0:
            self.pos += norm(mv) * self.move_speed() * dt
        # lunge/recoil rides on top of normal movement -- it never blocks it
        if self.lunge_t > 0:
            self.lunge_t = max(0.0, self.lunge_t - dt)
            self.pos += self.lunge_dir * self.lunge_pow * dt
        self.clamp_pos()

        inside_smoke = any(z.kind == "smoke" and z.pos.distance_to(self.pos) < z.radius for z in g.zones)
        if inside_smoke:
            self.pos += norm(mv) * 60 * dt if mv.length_squared() else V2(0, 0)

        if firing and self.atk_t <= 0:
            self.attack(g)

        for m in self.mines[:]:
            m.update(dt)
            if m.arm <= 0:
                for e in g.enemies:
                    if e.pos.distance_to(m.pos) < 34:
                        for e2 in g.enemies:
                            if e2.pos.distance_to(m.pos) < 82:
                                e2.hurt(m.dmg, slow=1.0, kb=norm(e2.pos - m.pos) * 260)
                                g.fx_hit(e2.pos, int(m.dmg), YELLOW)
                                self.on_hit(e2, g)
                        g.fx_ring(m.pos, YELLOW, 82)
                        g.shake = max(g.shake, 7)
                        m.dead = True
                        break
            if m.dead:
                self.mines.remove(m)

    def draw(self, sf):
        spr = self.spr
        r = spr.get_rect()
        if self.face < 0:
            spr = pygame.transform.flip(spr, True, False)

        # ---- dash afterimages (drawn under the real sprite) ----------------
        for pos, life in self.trail:
            gh = spr.copy()
            gh.set_alpha(int(110 * (life / 0.28)))
            sf.blit(gh, (pos.x - r.w / 2, pos.y - r.h / 2))

        # ---- contact shadow ------------------------------------------------
        shadow = pygame.Surface((34, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 115), (0, 0, 34, 10))
        sf.blit(shadow, (self.pos.x - 17, self.pos.y + 20))

        if self.stealth > 0:
            spr = spr.copy()
            spr.set_alpha(95)
        elif self.iframe > 0 and int(self.iframe * 22) % 2 == 0:
            spr = spr.copy()
            spr.fill((150, 60, 60), None, pygame.BLEND_RGB_ADD)
        sf.blit(spr, (self.pos.x - r.w / 2, self.pos.y - r.h / 2))

        # ---- guard bubble ---------------------------------------------------
        if self.guard > 0:
            bub = pygame.Surface((88, 88), pygame.SRCALPHA)
            pygame.draw.circle(bub, (*CYAN, 34), (44, 44), 42)
            pygame.draw.circle(bub, (*CYAN, 190), (44, 44), 42, 2)
            sf.blit(bub, (self.pos.x - 44, self.pos.y - 44))

        # ---- melee slash arc: a real tapered sweep, not a thin line --------
        if self.slash > 0:
            k = clamp(self.slash / 0.18, 0, 1)
            a = math.atan2(self.slash_dir.y, self.slash_dir.x)
            rr = self.c["rng"] if self.c["rng"] < 200 else 44
            sweep = 1.15
            start = a - sweep / 2 + (1 - k) * sweep
            layer = pygame.Surface((rr * 2 + 20, rr * 2 + 20), pygame.SRCALPHA)
            cxy = rr + 10
            steps = 12
            inner, outer_pts = [], []
            for i in range(steps + 1):
                t = i / steps
                ang = start - sweep * 0.55 + sweep * 0.7 * t
                taper = math.sin(t * math.pi)          # thin at both ends
                r_in = rr * (0.62 + 0.10 * (1 - taper))
                r_out = r_in + 3 + 7 * taper
                inner.append((cxy + math.cos(ang) * r_in, cxy + math.sin(ang) * r_in))
                outer_pts.append((cxy + math.cos(ang) * r_out, cxy + math.sin(ang) * r_out))
            pygame.draw.polygon(layer, (255, 255, 255, int(190 * k)),
                                inner + outer_pts[::-1])
            pygame.draw.polygon(layer, (*lite(self.c["colors"][1], 0.4), int(120 * k)),
                                inner + outer_pts[::-1], 2)
            sf.blit(layer, (self.pos.x - cxy, self.pos.y - cxy))

        # ---- muzzle flash ---------------------------------------------------
        # drawn on its own surface and additively blitted so it actually
        # flares against the scene instead of sitting as a flat-colored shape
        if self.muzzle > 0:
            mp = self.pos + self.aim * 26
            k = self.muzzle / 0.07
            col = self.c["colors"][1]
            hw = int(20 * k) + 2
            flash = pygame.Surface((hw * 2, hw * 2), pygame.SRCALPHA)
            fc = V2(hw, hw)
            pygame.draw.circle(flash, (*lite(col, 0.6), 255), fc, int(9 * k))
            perp = V2(-self.aim.y, self.aim.x)
            pygame.draw.polygon(flash, (*lite(col, 0.3), 220), [
                fc + self.aim * 16 * k, fc + perp * 7 * k, fc - perp * 7 * k])
            sf.blit(flash, (mp.x - hw, mp.y - hw), special_flags=pygame.BLEND_RGBA_ADD)

        # ---- aim indicator: small floating reticle reads better than a stub -
        tip = self.pos + self.aim * 40
        acc = self.c["colors"][1]
        pygame.draw.line(sf, acc, self.pos + self.aim * 24, self.pos + self.aim * 34, 2)
        pygame.draw.circle(sf, acc, tip, 3, 1)


# ----------------------------------------------------------------------------
# GAME (one chapter)
# ----------------------------------------------------------------------------
class Game:
    def __init__(self, char, chapter_index, font, bigfont, smallfont, diff=None, inv=None):
        self.c = char
        self.ci = chapter_index
        self.ch = CHAPTERS[chapter_index]
        self.diff = diff or DIFFICULTIES[1]
        self.player = Player(char)
        self.inv = inv if inv is not None else Inventory()
        self.pickups = []
        self.drought = 0            # kills since the last potion drop
        self.note_time = -99.0
        self.note_k = 0
        self.fx_t = 0.0
        self.enemies = []
        self.projectiles = []
        self.zones = []
        self.numbers = []
        self.rings = []
        self.beams = []
        self.relay = Relay(V2(ARENA.center)) if self.ch["relay"] else None
        if self.relay:
            self.player.pos = V2(ARENA.centerx, ARENA.centery + 130)
        self.spawn_t = 1.2
        self.time = 0.0
        self.kills = 0
        self.shake = 0.0
        self.state = "play"  # play | won | lost
        # --- stage-clear portal (runs while state == "won") ---
        self.rewarded = False        # App commits XP/coins once, on the first won frame
        self.portal_pos = None
        self.portal_t = 0.0          # seconds since the stage was cleared
        self.portal_col = PORTAL_COLORS[chapter_index % len(PORTAL_COLORS)]
        self.portal_burst = False    # opening flare fired?
        self.portal_ready_msg = False
        self.enter_t = None          # None until the player steps in
        self.enter_from = V2(0, 0)
        self.portal_done = False     # warp finished -> App moves on to the dialog
        self.banner_text = ""
        self.banner_sub = ""
        self.banner_t = 0.0
        self.scale = (1.0 + 0.18 * chapter_index) * self.diff["hp"]
        self.dmg_scale = (1.0 + 0.12 * chapter_index) * self.diff["dmg"]
        self.xp_earned = 0
        self.coins_earned = 0
        self.font, self.bigfont, self.small = font, bigfont, smallfont
        self.particles = []
        self.prev_down = set()      # for press-vs-hold detection
        self.buf = {"q": 0.0, "e": 0.0, "dash": 0.0}
        self.hitstop = 0.0
        self.punch = 0.0            # brief camera zoom-in on heavy impacts
        self.decals = []            # scorch/blood marks that persist on the floor
        self.bg = build_arena(1000 + chapter_index, self.ch.get("floor"))
        self.vignette = build_vignette()
        self.motes = [[V2(random.randint(ARENA.left, ARENA.right),
                          random.randint(ARENA.top, ARENA.bottom)),
                       random.uniform(-9, 9), random.uniform(-16, -5),
                       random.uniform(1.0, 2.0)] for _ in range(22)]
        self.props = [(random.randint(ARENA.left + 30, ARENA.right - 30),
                       random.randint(ARENA.top + 30, ARENA.bottom - 30),
                       random.randint(6, 16)) for _ in range(18)]
        self.init_twist()
        spec = self.ch.get("twist")
        if self.ch["boss"]:
            self.enemies.append(Enemy("warden", V2(ARENA.centerx, ARENA.top + 90),
                                       1.0 * self.diff["hp"], self.dmg_scale))
            self.banner("THE WARDEN", 3.0, ("TWIST - %s: %s" % (spec["name"], spec["desc"])) if spec else "")
        elif spec:
            self.banner(spec["name"], 3.0, spec["desc"])

    # ---- fx helpers ------------------------------------------------------
    def fx_hit(self, pos, amount, color):
        self.numbers.append([V2(pos) + V2(random.uniform(-8, 8), -14), str(int(amount)), color, 0.8])

    def fx_ring(self, pos, color, r=60):
        self.rings.append([V2(pos), color, 0.0, r])

    def fx_beam(self, p1, p2, color, life=0.16, width=3):
        self.beams.append([V2(p1), V2(p2), color, life, life, width])

    def fx_orbit(self, pos, col, n=10, power=180, life=(0.20, 0.40)):
        """Sparks launched evenly around a circle -- reads as a magical/spin burst
        rather than the random scatter fx_spark gives."""
        for i in range(n):
            a = math.tau * i / n
            self.particles.append(Particle(
                pos, V2(math.cos(a), math.sin(a)) * power,
                random.uniform(*life), col, random.randint(2, 4), grav=60))

    def fx_dust(self, pos, n, col=(70, 76, 98)):
        for _ in range(n):
            self.particles.append(Particle(
                pos + V2(random.uniform(-5, 5), random.uniform(-2, 2)),
                V2(random.uniform(-22, 22), random.uniform(-26, -6)),
                random.uniform(0.25, 0.5), col, random.randint(3, 5),
                grav=40, kind="smoke"))

    def fx_spark(self, pos, col, n=8, power=200):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(0.4, 1.0) * power
            self.particles.append(Particle(
                pos, V2(math.cos(a), math.sin(a)) * sp,
                random.uniform(0.18, 0.42), random.choice([col, lite(col, 0.5)]),
                random.randint(2, 4), grav=260))

    def fx_death(self, pos, col):
        self.fx_spark(pos, col, 16, 300)
        for _ in range(7):
            self.particles.append(Particle(
                pos + V2(random.uniform(-9, 9), random.uniform(-9, 9)),
                V2(random.uniform(-40, 40), random.uniform(-60, -20)),
                random.uniform(0.4, 0.8), dark(col, 0.8), random.randint(5, 9),
                kind="smoke"))
        self.decals.append([V2(pos), dark(col, 0.45), random.randint(9, 15)])
        if len(self.decals) > 40:
            self.decals.pop(0)

    def banner(self, text, t, sub=""):
        self.banner_text = text
        self.banner_sub = sub
        self.banner_t = t

    # ---- potions ---------------------------------------------------------
    def note(self, text, col):
        """Short floating label above the player."""
        if self.time - self.note_time < 0.6:
            self.note_k += 1
        else:
            self.note_k = 0
        self.note_time = self.time
        self.numbers.append([V2(self.player.pos) + V2(-len(text) * 3, -46 - 16 * self.note_k), text, col, 1.2])

    def use_item(self, iid):
        """Drink a potion from the bag. Returns True if one was consumed."""
        if self.state != "play":
            return False
        it = ITEMS[iid]
        p = self.player
        if self.inv.count(iid) <= 0:
            self.note("NO %s" % it["tag"], GREY)
            return False
        if iid == "heal":
            if p.hp >= p.maxhp - 0.5:
                self.note("HP FULL", GREY)
                return False
            self.inv.take(iid)
            before = p.hp
            p.heal(p.maxhp * 0.40)
            self.note("+%d HP" % round(p.hp - before), GREEN)
        else:
            self.inv.take(iid)
            p.pot[iid] = max(p.pot[iid], it["dur"])       # re-drinking refreshes it
            self.note(it["tag"] + "!", it["col"])
        self.fx_ring(p.pos, it["col"], 70)
        self.fx_orbit(p.pos, it["col"], 12, 170)
        return True

    def pick_drop(self):
        """Weighted choice; full stacks never drop, and heals favour low HP."""
        w = {}
        for k in ITEM_ORDER:
            if not self.inv.room(k):
                continue
            wt = ITEMS[k]["weight"]
            if k == "heal":
                f = self.player.hp_frac
                wt *= 2.4 if f < 0.5 else (0.5 if f > 0.9 else 1.0)
            w[k] = wt
        if not w:
            return None
        return random.choices(list(w), list(w.values()))[0]

    def maybe_drop(self, e):
        base = DROP_BASE.get(e.kind, 0.0)
        if base <= 0:
            return
        self.drought += 1
        chance = 1.0 if self.drought >= DROP_GUARANTEE else base + DROP_PITY * self.drought
        if random.random() >= chance:
            return
        iid = self.pick_drop()
        if iid is None:
            return
        self.drought = 0
        self.pickups.append(Pickup(e.pos, iid))
        self.fx_ring(e.pos, ITEMS[iid]["col"], 34)

    def update_pickups(self, dt):
        p = self.player
        for pk in self.pickups[:]:
            pk.age += dt
            if pk.age > Pickup.LIFE:
                self.pickups.remove(pk)
                continue
            if pk.vel.length_squared() > 4:
                pk.pos += pk.vel * dt
                pk.vel *= 0.93 ** (dt * 60)
                pk.pos.x = clamp(pk.pos.x, ARENA.left + 16, ARENA.right - 16)
                pk.pos.y = clamp(pk.pos.y, ARENA.top + 16, ARENA.bottom - 16)
            room = self.inv.room(pk.iid)
            d = p.pos.distance_to(pk.pos)
            if room and pk.age > 0.35 and self.enter_t is None and d < 110:
                pk.pos += norm(p.pos - pk.pos) * (150 + (110 - d) * 4) * dt   # magnet
                d = p.pos.distance_to(pk.pos)
            if room and pk.age > 0.25 and d < 30:
                self.inv.add(pk.iid)
                self.pickups.remove(pk)
                it = ITEMS[pk.iid]
                self.note("+" + it["tag"], it["col"])
                self.fx_ring(pk.pos, it["col"], 40)
                self.fx_spark(pk.pos, it["col"], 8, 160)

    def update_buff_fx(self, dt):
        self.fx_t -= dt
        if self.fx_t > 0:
            return
        self.fx_t = 0.09
        p = self.player
        for k, t in p.pot.items():
            if t > 0:
                off = V2(random.uniform(-14, 14), random.uniform(6, 20))
                self.particles.append(Particle(
                    p.pos + off, V2(random.uniform(-8, 8), -random.uniform(40, 80)),
                    random.uniform(0.35, 0.6), ITEMS[k]["col"], random.randint(2, 4)))

    def draw_buff_auras(self, sf):
        p = self.player
        active = [k for k, t in p.pot.items() if t > 0]
        for i, k in enumerate(active):
            col = ITEMS[k]["col"]
            fade = 1.0 if p.pot[k] > 1.5 else 0.5 + 0.5 * math.sin(self.time * 20)   # blinks when ending
            w, h = 46 + i * 10, 18 + i * 4
            surf = pygame.Surface((w + 4, h + 4), pygame.SRCALPHA)
            pygame.draw.ellipse(surf, (*col, int(70 * fade)), (2, 2, w, h))
            pygame.draw.ellipse(surf, (*lite(col, 0.3), int(210 * fade)), (2, 2, w, h), 2)
            sf.blit(surf, (p.pos.x - w / 2 - 2, p.pos.y + 20 - h / 2 - 2))

    def belt_rects(self):
        bw, gap = 48, 6
        n = len(ITEM_ORDER)
        x0 = W - 24 - (n * bw + (n - 1) * gap)
        return [pygame.Rect(x0 + i * (bw + gap), H - 54, bw, 48) for i in range(n)]

    def draw_belt(self, sf):
        """Bottom-right potion belt: icon, key, count, and a timer bar while active."""
        for i, (iid, r) in enumerate(zip(ITEM_ORDER, self.belt_rects())):
            it = ITEMS[iid]
            col = it["col"]
            n = self.inv.count(iid)
            act = self.player.pot.get(iid, 0.0)
            has = n > 0
            pygame.draw.rect(sf, (30, 33, 44) if has else (20, 22, 30), r, border_radius=6)
            pygame.draw.rect(sf, col if has else DGREY, r, 2 if has else 1, border_radius=6)
            spr = potion_sprite(iid)
            if not has:
                spr = spr.copy()
                spr.set_alpha(70)
            sf.blit(spr, (r.centerx - spr.get_width() / 2, r.y + 6))
            tcol = WHITE if has else DGREY
            sf.blit(self.small.render(str(i + 1), True, tcol), (r.x + 5, r.y + 3))
            cimg = self.small.render("x%d" % n, True, tcol)
            sf.blit(cimg, (r.right - cimg.get_width() - 4, r.y + 3))
            if act > 0:
                pygame.draw.rect(sf, lite(col, 0.5), r.inflate(4, 4), 1, border_radius=7)
                bar = pygame.Rect(r.x + 3, r.bottom - 7, int((r.w - 6) * clamp(act / it["dur"], 0, 1)), 4)
                pygame.draw.rect(sf, col, bar, border_radius=2)

    # ---- chapter twists --------------------------------------------------
    # One twist per chapter (CHAPTERS[i]["twist"]). State lives in self.tw.
    # update_twist() runs once per play frame; draw_twist_under() paints floor
    # hazards beneath the units, draw_twist_over() paints weather / darkness.
    GUST_DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)]
    RING_IX, RING_IY = 280, 150      # how far the ash ring closes in at 100%

    def init_twist(self):
        spec = self.ch.get("twist")
        tid = spec["id"] if spec else None
        self.tw = {"id": tid}
        if tid == "wind":
            self.tw.update(
                next=3.5, gust=0.0, gust_len=4.2, dir=V2(1, 0), env=0.0,
                streaks=[[V2(random.uniform(ARENA.left, ARENA.right),
                             random.uniform(ARENA.top, ARENA.bottom)),
                          random.uniform(0.6, 1.4)] for _ in range(70)],
                ov=pygame.Surface(ARENA.size, pygame.SRCALPHA))
        elif tid == "mortar":
            self.tw.update(next=4.0, shells=[], det=0)
        elif tid == "blackout":
            self.tw.update(surge_t=9.0, surges=0, flash=0.0,
                           dark=pygame.Surface(ARENA.size, pygame.SRCALPHA))
        elif tid == "ashring":
            self.tw.update(f=0.0, tick=0.0, ov=pygame.Surface(ARENA.size, pygame.SRCALPHA))

    def twist_label(self):
        spec = self.ch.get("twist")
        if not spec:
            return ""
        tid, name = self.tw["id"], spec["name"]
        if tid == "wind" and self.tw["env"] > 0.05:
            return name + "  -  GUST"
        if tid == "blackout":
            return "%s  -  SURGE IN %ds" % (name, max(0, math.ceil(self.tw["surge_t"])))
        if tid == "ashring":
            return "%s  -  %d%% CLOSED" % (name, int(self.tw["f"] * 100))
        return name

    def update_twist(self, dt):
        tid = self.tw["id"]
        if tid == "wind":
            self._tw_wind(dt)
        elif tid == "mortar":
            self._tw_mortar(dt)
        elif tid == "blackout":
            self._tw_blackout(dt)
        elif tid == "ashring":
            self._tw_ashring(dt)

    # -- I: crosswind ---------------------------------------------------------
    def _tw_wind(self, dt):
        tw = self.tw
        if tw["gust"] > 0:
            tw["gust"] = max(0.0, tw["gust"] - dt)
            tw["env"] = math.sin((1 - tw["gust"] / tw["gust_len"]) * math.pi)
        else:
            tw["env"] = 0.0
            tw["next"] -= dt
            if tw["next"] <= 0:
                d = V2(random.choice(self.GUST_DIRS))
                tw["dir"] = norm(d)
                tw["gust"] = tw["gust_len"]
                tw["next"] = random.uniform(5.0, 8.0)
                name = ("NORTH" if d.y < 0 else "SOUTH" if d.y > 0 else "") + \
                       ("EAST" if d.x > 0 else "WEST" if d.x < 0 else "")
                self.banner("GUST BLOWING " + name, 1.6)
        if tw["env"] > 0:
            push = tw["dir"] * (110 * tw["env"])
            p = self.player
            p.pos += push * dt
            p.clamp_pos()
            box = ARENA.inflate(60, 60)
            for e in self.enemies:
                e.pos += push * dt * (0.5 if e.kind == "warden" else 1.0)
                e.pos.x = clamp(e.pos.x, box.left, box.right)
                e.pos.y = clamp(e.pos.y, box.top, box.bottom)
            for st in tw["streaks"]:
                st[0] += tw["dir"] * (520 * tw["env"] * st[1] * dt)
                if st[0].x > ARENA.right:
                    st[0].x = ARENA.left
                elif st[0].x < ARENA.left:
                    st[0].x = ARENA.right
                if st[0].y > ARENA.bottom:
                    st[0].y = ARENA.top
                elif st[0].y < ARENA.top:
                    st[0].y = ARENA.bottom

    # -- II: crossfire ---------------------------------------------------------
    def _tw_mortar(self, dt):
        tw = self.tw
        tw["next"] -= dt
        if tw["next"] <= 0:
            k = clamp(self.time / self.ch["target"], 0, 1)
            tw["next"] = 2.9 - 1.3 * k                  # the barrage tightens over time
            for _ in range(1 if self.time < 28 else 2):
                if random.random() < 0.65:              # most shells lead the player
                    a = random.uniform(0, math.tau)
                    pos = self.player.pos + V2(math.cos(a), math.sin(a)) * random.uniform(0, 150)
                else:
                    pos = V2(random.randint(ARENA.left, ARENA.right),
                             random.randint(ARENA.top, ARENA.bottom))
                pos.x = clamp(pos.x, ARENA.left + 50, ARENA.right - 50)
                pos.y = clamp(pos.y, ARENA.top + 50, ARENA.bottom - 50)
                tw["shells"].append([pos, 1.5, 1.5, 78])
        for sh in tw["shells"][:]:
            sh[1] -= dt
            if sh[1] <= 0:
                tw["shells"].remove(sh)
                self._mortar_blast(sh[0], sh[3])

    def _mortar_blast(self, pos, rad):
        p = self.player
        if p.pos.distance_to(pos) < rad + 14:
            p.hurt(24 * self.dmg_scale, self)
        for e in self.enemies:
            if e.pos.distance_to(pos) < rad + e.rad * 0.5:
                e.hurt(60, stun=0.4, kb=norm(e.pos - pos) * 240)
                self.fx_hit(e.pos, 60, ORANGE)
        self.fx_ring(pos, ORANGE, rad)
        self.fx_spark(pos, ORANGE, 18, 320)
        self.fx_dust(pos, 6)
        self.decals.append([V2(pos), (36, 28, 24), 30])
        if len(self.decals) > 40:
            self.decals.pop(0)
        self.shake = max(self.shake, 9)
        self.tw["det"] += 1

    # -- III: blackout ---------------------------------------------------------
    def _tw_blackout(self, dt):
        tw = self.tw
        tw["flash"] = max(0.0, tw["flash"] - dt)
        if self.relay is None or self.relay.hp <= 0:
            return
        tw["surge_t"] -= dt
        if tw["surge_t"] <= 0:
            tw["surge_t"] = 14.0
            tw["surges"] += 1
            tw["flash"] = 0.6
            rp = self.relay.pos
            reach = 300
            self.fx_ring(rp, CYAN, reach / 1.1)
            self.fx_ring(rp, lite(CYAN, 0.6), reach / 1.6)
            self.shake = max(self.shake, 6)
            self.banner("RELAY SURGE", 1.4, "a shockwave stuns everything near the relay")
            for e in self.enemies:
                if e.pos.distance_to(rp) < reach:
                    e.hurt(24, stun=1.6, kb=norm(e.pos - rp) * 320)
                    self.fx_beam(rp, e.pos, CYAN, 0.3, 3)
                    self.fx_hit(e.pos, 24, CYAN)

    # -- IV: ash ring ----------------------------------------------------------
    def ring_safe(self):
        f = self.tw["f"]
        return ARENA.inflate(-int(2 * self.RING_IX * f), -int(2 * self.RING_IY * f))

    def _tw_ashring(self, dt):
        tw = self.tw
        boss = next((e for e in self.enemies if e.kind == "warden"), None)
        hpf = boss.hp / boss.maxhp if boss else 1.0
        # closes with the Warden's wounds, or on a timer if the fight stalls
        target = clamp(max(1 - hpf, self.time / 150.0), 0.0, 1.0)
        tw["f"] = min(target, tw["f"] + dt / 12.0)
        p = self.player
        if not self.ring_safe().inflate(28, 28).collidepoint(p.pos):
            dps = 11 * self.diff["dmg"]
            p.hp -= dps * dt
            p.dmg_taken += dps * dt
            tw["tick"] -= dt
            if tw["tick"] <= 0:
                tw["tick"] = 0.5
                self.fx_hit(p.pos, max(1, int(dps * 0.5)), PURPLE)
                self.fx_spark(p.pos, (200, 200, 220), 4, 100)

    # -- drawing ---------------------------------------------------------------
    def draw_twist_under(self, sf):
        tid = self.tw["id"]
        if tid == "mortar":
            for pos, t, total, rad in self.tw["shells"]:
                k = 1 - t / total
                size = int(rad * 2 + 8)
                c = size // 2
                s = pygame.Surface((size, size), pygame.SRCALPHA)
                pulse = 0.5 + 0.5 * math.sin(self.time * 18)
                pygame.draw.circle(s, (226, 84, 84, int(34 + 60 * k)), (c, c), rad)
                pygame.draw.circle(s, (255, 130, 110, int(150 + 80 * pulse * k)), (c, c), rad, 3)
                pygame.draw.circle(s, (255, 190, 150, 210), (c, c), max(3, int(rad * (1 - k))), 2)
                pygame.draw.line(s, (255, 150, 120, 150), (c - 10, c), (c + 10, c), 2)
                pygame.draw.line(s, (255, 150, 120, 150), (c, c - 10), (c, c + 10), 2)
                sf.blit(s, (pos.x - c, pos.y - c))
        elif tid == "ashring":
            ov = self.tw["ov"]
            pulse = 0.5 + 0.5 * math.sin(self.time * 3)
            ov.fill((170, 168, 190, int(72 + 26 * pulse)))
            safe = self.ring_safe().move(-ARENA.left, -ARENA.top)
            ov.fill((0, 0, 0, 0), safe)
            pygame.draw.rect(ov, (226, 222, 244, int(150 + 70 * pulse)), safe, 3)
            sf.blit(ov, ARENA.topleft)

    def draw_twist_over(self, sf):
        tw = self.tw
        if tw["id"] == "wind" and tw["env"] > 0.02:
            ov = tw["ov"]
            ov.fill((0, 0, 0, 0))
            d = tw["dir"]
            a = int(130 * tw["env"])
            for pos, sp in tw["streaks"]:
                ln = 14 + 46 * tw["env"] * sp
                x, y = pos.x - ARENA.left, pos.y - ARENA.top
                pygame.draw.line(ov, (200, 182, 150, a), (x, y), (x - d.x * ln, y - d.y * ln), 2)
            sf.blit(ov, ARENA.topleft)
        elif tw["id"] == "blackout":
            dk = tw["dark"]
            dk.fill((3, 5, 14, 198))
            ax, ay = ARENA.left, ARENA.top

            def cut(pos, radius):
                sp = get_light(radius)
                r = sp.get_width() // 2
                dk.blit(sp, (pos.x - ax - r, pos.y - ay - r), special_flags=pygame.BLEND_RGBA_SUB)

            cut(self.player.pos, 180)
            if self.relay is not None and self.relay.hp > 0:
                flick = 1 + 0.04 * math.sin(self.time * 9)
                cut(self.relay.pos, 270 * flick * (1 + tw["flash"]))
            for pr in self.projectiles[:10]:
                cut(pr.pos, 50)
            for pk in self.pickups:
                cut(pk.pos, 60)                     # potions glow in the dark
            sf.blit(dk, ARENA.topleft)

    # ---- objective -------------------------------------------------------
    def objective_text(self):
        g = self.ch["goal"]
        if g == "kills":
            return "ELIMINATE %d / %d" % (min(self.kills, self.ch["target"]), self.ch["target"])
        if g == "survive":
            return "SURVIVE  %0.1fs" % max(0.0, self.ch["target"] - self.time)
        if g == "protect":
            return "HOLD RELAY  %0.1fs" % max(0.0, self.ch["target"] - self.time)
        return "DEFEAT THE WARDEN"

    def progress(self):
        g = self.ch["goal"]
        if g == "kills":
            return clamp(self.kills / self.ch["target"], 0, 1)
        if g in ("survive", "protect"):
            return clamp(self.time / self.ch["target"], 0, 1)
        boss = next((e for e in self.enemies if e.kind == "warden"), None)
        return 1 - (boss.hp / boss.maxhp) if boss else 1.0

    def check_end(self):
        if self.player.hp <= 0:
            self.state = "lost"
            return
        if self.relay is not None and self.relay.hp <= 0:
            self.state = "lost"
            return
        g = self.ch["goal"]
        if g == "kills" and self.kills >= self.ch["target"]:
            self.state = "won"
        elif g in ("survive", "protect") and self.time >= self.ch["target"]:
            self.state = "won"
        elif g == "boss" and not any(e.kind == "warden" for e in self.enemies):
            self.state = "won"
        if self.state == "won":
            self.begin_portal()

    # ---- spawning --------------------------------------------------------
    def spawn(self):
        pool = []
        for k, weight in self.ch["spawn"].items():
            pool += [k] * weight
        kind = random.choice(pool)
        side = random.randint(0, 3)
        if side == 0:
            p = V2(random.randint(ARENA.left, ARENA.right), ARENA.top + 10)
        elif side == 1:
            p = V2(random.randint(ARENA.left, ARENA.right), ARENA.bottom - 10)
        elif side == 2:
            p = V2(ARENA.left + 10, random.randint(ARENA.top, ARENA.bottom))
        else:
            p = V2(ARENA.right - 10, random.randint(ARENA.top, ARENA.bottom))
        self.enemies.append(Enemy(kind, p, self.scale, self.dmg_scale))

    # ---- update ----------------------------------------------------------
    def update(self, dt, keys, mouse_pos, mouse_down):
        if self.state == "won":
            if self.portal_pos is not None and not self.portal_done:
                self.update_portal(dt, keys, mouse_pos)
            return
        if self.state != "play":
            return
        if self.hitstop > 0:
            self.hitstop = max(0.0, self.hitstop - dt)
            dt *= 0.18                      # everything crawls for a few frames
        self.time += dt
        self.shake = max(0.0, self.shake - dt * 40)
        self.punch = max(0.0, self.punch - dt * 1.5)
        self.banner_t = max(0.0, self.banner_t - dt)

        mv = V2(0, 0)
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            mv.x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            mv.x += 1
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            mv.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            mv.y += 1

        aim = V2(mouse_pos) - self.player.pos
        firing = mouse_down or keys[pygame.K_j]

        p = self.player

        # --- skills/dash fire on PRESS, not while held -----------------------
        # Holding the key used to re-fire the instant the cooldown expired,
        # which yanked the player around and fought the movement keys.
        watch = {"q": (pygame.K_q,), "e": (pygame.K_e,),
                 "dash": (pygame.K_SPACE, pygame.K_LSHIFT, pygame.K_RSHIFT)}
        down = set()
        for name, codes in watch.items():
            if any(keys[c] for c in codes):
                down.add(name)
        just = down - self.prev_down
        self.prev_down = down

        # a short buffer means a press just before the cooldown ends still counts
        for name in self.buf:
            self.buf[name] = max(0.0, self.buf[name] - dt)
            if name in just:
                self.buf[name] = 0.22
        if self.buf["q"] > 0 and p.cdq <= 0:
            self.buf["q"] = 0.0
            p.skill_q(self)
        if self.buf["e"] > 0 and p.cde <= 0:
            self.buf["e"] = 0.0
            p.skill_e(self)
        if self.buf["dash"] > 0 and p.cdd <= 0:
            self.buf["dash"] = 0.0
            p.dash(self, mv)

        p.update(dt, self, mv, aim, firing, keys)

        # enemies
        alive = 0
        for e in self.enemies[:]:
            e.update(dt, self)
            if e.dead:
                self.enemies.remove(e)
                self.kills += 1
                xp, coins = KILL_REWARD.get(e.kind, (6, 1))
                self.xp_earned += xp
                self.coins_earned += coins
                self.numbers.append([V2(e.pos) + V2(random.uniform(-6, 6), -30),
                                      "+%dc" % coins, YELLOW, 0.9])
                self.fx_ring(e.pos, RED, 26)
                self.fx_death(e.pos, ENEMY_LOOK[e.kind]["col"])
                self.maybe_drop(e)
                self.shake = max(self.shake, 5 if e.kind != "warden" else 16)
                self.punch = max(self.punch, 0.05 if e.kind != "warden" else 0.22)
                if self.c["id"] == "vex":
                    p.heal(10)
                    p.stacks = min(5, p.stacks + 1)
                    p.stack_t = 3.0
            else:
                alive += 1

        # spawn
        if not (self.ch["goal"] == "kills" and self.kills >= self.ch["target"]):
            self.spawn_t -= dt
            if self.spawn_t <= 0 and alive < self.ch["max_alive"]:
                self.spawn_t = self.ch["interval"] * self.diff["interval"]
                self.spawn()

        # projectiles
        for pr in self.projectiles[:]:
            pr.update(dt)
            if pr.owner == "player":
                for e in self.enemies:
                    if id(e) in pr.hit:
                        continue
                    if pr.pos.distance_to(e.pos) < e.rad + pr.radius:
                        dist = pr.start.distance_to(pr.pos)
                        dmg = pr.dmg * p.dmg_mult(dist, e.hp / e.maxhp)
                        e.hurt(dmg, slow=1.2 if pr.slow else 0.0, stun=pr.stun,
                               kb=norm(pr.vel) * 60)
                        self.fx_hit(e.pos, int(dmg), WHITE)
                        self.fx_spark(pr.pos, pr.color, 7, 170)
                        p.on_hit(e, self)
                        pr.hit.add(id(e))
                        if pr.pierce <= 0:
                            pr.dead = True
                            break
                        pr.pierce -= 1
            else:
                if pr.pos.distance_to(p.pos) < 16 + pr.radius:
                    p.hurt(pr.dmg, self)
                    self.fx_spark(pr.pos, RED, 8, 190)
                    pr.dead = True
                elif self.relay and pr.pos.distance_to(self.relay.pos) < 34:
                    self.relay.hp -= pr.dmg
                    self.fx_hit(self.relay.pos, pr.dmg, ORANGE)
                    pr.dead = True
            if pr.dead:
                self.projectiles.remove(pr)

        self.update_buff_fx(dt)
        self.update_twist(dt)
        self.update_fx(dt)
        self.check_end()

    def update_fx(self, dt):
        """Decay zones / numbers / particles / motes. Shared by play + portal."""
        self.update_pickups(dt)
        for z in self.zones[:]:
            z.update(dt)
            if z.dead:
                self.zones.remove(z)
        for n in self.numbers[:]:
            n[0].y -= 34 * dt
            n[3] -= dt
            if n[3] <= 0:
                self.numbers.remove(n)
        for rg in self.rings[:]:
            rg[2] += dt
            if rg[2] > 0.35:
                self.rings.remove(rg)
        for bm in self.beams[:]:
            bm[3] -= dt
            if bm[3] <= 0:
                self.beams.remove(bm)
        for q in self.particles[:]:
            q.update(dt)
            if q.life <= 0:
                self.particles.remove(q)
        if len(self.particles) > 320:
            del self.particles[:len(self.particles) - 320]
        for m in self.motes:
            m[0].x += m[1] * dt
            m[0].y += m[2] * dt
            if m[0].y < ARENA.top:
                m[0].y = ARENA.bottom
                m[0].x = random.randint(ARENA.left, ARENA.right)
            if not ARENA.left <= m[0].x <= ARENA.right:
                m[0].x = random.randint(ARENA.left, ARENA.right)

    # ---- stage-clear portal ---------------------------------------------
    PORTAL_DELAY = 0.6      # beat between "STAGE CLEAR" and the gate tearing open
    PORTAL_OPEN_TIME = 1.6
    ENTER_TIME = 0.9

    def portal_open(self):
        """0..1 how far the gate has opened (eased)."""
        k = clamp((self.portal_t - self.PORTAL_DELAY) / self.PORTAL_OPEN_TIME, 0.0, 1.0)
        return 1 - (1 - k) ** 3

    def portal_ready(self):
        return self.portal_open() >= 0.9 and self.enter_t is None

    def begin_portal(self):
        """Stage just cleared: wipe leftovers, pick a spot far from the player."""
        for e in self.enemies:
            self.fx_death(e.pos, ENEMY_LOOK[e.kind]["col"])
        self.enemies.clear()
        self.projectiles.clear()
        pp = self.player.pos
        cands = [V2(ARENA.centerx, ARENA.top + 120), V2(ARENA.centerx, ARENA.bottom - 80),
                 V2(ARENA.left + 110, ARENA.centery), V2(ARENA.right - 110, ARENA.centery)]
        self.portal_pos = max(cands, key=lambda c: c.distance_to(pp))
        self.portal_t = 0.0
        self.shake = max(self.shake, 8)
        self.banner("STAGE CLEAR", 2.0)

    def begin_enter(self):
        """Player steps into the gate (walk in, or ENTER as a shortcut)."""
        if not self.portal_ready():
            return False
        self.enter_t = 0.0
        self.enter_from = V2(self.player.pos)
        self.fx_ring(self.portal_pos, self.portal_col, 90)
        self.shake = max(self.shake, 6)
        return True

    def update_portal(self, dt, keys, mouse_pos):
        self.portal_t += dt
        self.shake = max(0.0, self.shake - dt * 40)
        self.punch = max(0.0, self.punch - dt * 1.5)
        self.banner_t = max(0.0, self.banner_t - dt)
        pp = self.portal_pos
        col = self.portal_col

        if self.enter_t is None:
            # the player can still move and dodge; attacks/skills are off
            mv = V2(0, 0)
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                mv.x -= 1
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                mv.x += 1
            if keys[pygame.K_w] or keys[pygame.K_UP]:
                mv.y -= 1
            if keys[pygame.K_s] or keys[pygame.K_DOWN]:
                mv.y += 1
            p = self.player
            down = set()
            if any(keys[c] for c in (pygame.K_SPACE, pygame.K_LSHIFT, pygame.K_RSHIFT)):
                down.add("dash")
            if "dash" in down - self.prev_down and p.cdd <= 0:
                p.dash(self, mv)
            self.prev_down = down
            aim = V2(mouse_pos) - p.pos
            p.update(dt, self, mv, aim, False, keys)
        else:
            self.enter_t += dt
            if self.enter_t >= self.ENTER_TIME:
                self.portal_done = True

        # one big flare the moment the gate tears open
        if not self.portal_burst and self.portal_t >= self.PORTAL_DELAY:
            self.portal_burst = True
            self.fx_ring(pp, col, 120)
            self.fx_orbit(pp, col, 18, 220, life=(0.30, 0.55))
            self.fx_spark(pp, lite(col, 0.6), 14, 260)
            self.shake = max(self.shake, 7)
        if not self.portal_ready_msg and self.portal_ready():
            self.portal_ready_msg = True
            self.banner("PORTAL OPEN", 2.4)
            self.fx_ring(pp, lite(col, 0.4), 80)

        # walking into the gate
        if self.portal_ready():
            dx = (self.player.pos.x - pp.x) / 34.0
            dy = (self.player.pos.y - pp.y) / 52.0
            if dx * dx + dy * dy < 1.0:
                self.begin_enter()

        self.update_fx(dt)

    def draw_portal(self, sf):
        """Procedural gate: stone frame, swirling energy, orbiting motes."""
        if self.portal_pos is None:
            return
        op = self.portal_open()
        col = self.portal_col
        t = self.portal_t
        cx, cy = int(self.portal_pos.x), int(self.portal_pos.y)
        rx = max(2, int(46 * op))
        ry = max(4, int(70 * clamp(op * 1.5, 0.0, 1.0)))
        pulse = 0.5 + 0.5 * math.sin(t * 5.0)

        # ground glow
        glow = pygame.Surface((rx * 4 + 20, 60), pygame.SRCALPHA)
        pygame.draw.ellipse(glow, (*col, int(40 + 40 * op)), (0, 0, glow.get_width(), 60))
        sf.blit(glow, (cx - glow.get_width() // 2, cy + ry - 30))

        layer = pygame.Surface((rx * 2 + 60, ry * 2 + 60), pygame.SRCALPHA)
        lc = (layer.get_width() // 2, layer.get_height() // 2)

        # energy fill: nested ellipses, dark rim -> bright core
        n = 7
        for i in range(n):
            f = 1 - i / n
            c = tuple(int(a + (b - a) * (i / (n - 1)))
                      for a, b in zip(dark(col, 0.30), lite(col, 0.65)))
            er = pygame.Rect(0, 0, max(2, int(rx * 2 * f)), max(2, int(ry * 2 * f)))
            er.center = lc
            pygame.draw.ellipse(layer, (*c, 235), er)

        # swirling arcs that spin at different speeds
        for j in range(4):
            f = 0.30 + 0.17 * j
            er = pygame.Rect(0, 0, max(4, int(rx * 2 * f)), max(4, int(ry * 2 * f)))
            er.center = lc
            a0 = t * (2.2 + j * 0.8) * (1 if j % 2 == 0 else -1) + j * 1.7
            pygame.draw.arc(layer, (*lite(col, 0.7), 210), er, a0, a0 + 2.0, 3)

        # bright pulsing core
        core = pygame.Rect(0, 0, max(2, int(rx * 0.5 * (0.8 + 0.4 * pulse))),
                           max(2, int(ry * 0.5 * (0.8 + 0.4 * pulse))))
        core.center = lc
        pygame.draw.ellipse(layer, (*lite(col, 0.9), 230), core)

        # stone frame with slowly turning rune ticks
        fr = pygame.Rect(0, 0, rx * 2 + 10, ry * 2 + 10)
        fr.center = lc
        pygame.draw.ellipse(layer, (*(58, 65, 88), 255), fr, 9)
        pygame.draw.ellipse(layer, (*lite(col, 0.3), 200), fr, 2)
        for k in range(12):
            a = math.tau * k / 12 + t * 0.5
            px = lc[0] + math.cos(a) * (rx + 5)
            py = lc[1] + math.sin(a) * (ry + 5)
            pygame.draw.circle(layer, (*lite(col, 0.5), int(120 + 120 * pulse)), (int(px), int(py)), 2)
        sf.blit(layer, (cx - lc[0], cy - lc[1]))

        # motes spiralling inward (stateless: purely a function of time)
        if op > 0.15:
            for i in range(16):
                ph = (t * 0.7 + i / 16) % 1.0
                a = i * 2.4 + t * 2.0 + ph * 6.0
                r = 1.35 * (1 - ph)
                mx = cx + math.cos(a) * rx * r
                my = cy + math.sin(a) * ry * r
                al = int(220 * math.sin(ph * math.pi) * op)
                m = pygame.Surface((8, 8), pygame.SRCALPHA)
                pygame.draw.circle(m, (*lite(col, 0.6), al), (4, 4), 3)
                sf.blit(m, (mx - 4, my - 4), special_flags=pygame.BLEND_RGBA_ADD)

        # "ENTER" cue floating above the gate once it is usable
        if self.portal_ready() and int(t * 2.5) % 2 == 0:
            cue = self.small.render("ENTER", True, lite(col, 0.7))
            sf.blit(cue, (cx - cue.get_width() / 2, cy - ry - 28))

    def draw_entering_player(self, sf):
        """Player is sucked in: spirals toward the core while shrinking."""
        u = clamp(self.enter_t / self.ENTER_TIME, 0.0, 1.0)
        ease = u * u * (3 - 2 * u)
        pos = self.enter_from.lerp(self.portal_pos, ease)
        ang = u * 5.0 * math.pi
        rad = (1 - u) * 18
        pos = pos + V2(math.cos(ang), math.sin(ang)) * rad
        scale = max(0.05, 1 - 0.95 * ease)
        spr = self.player.spr
        if self.player.face < 0:
            spr = pygame.transform.flip(spr, True, False)
        spr = pygame.transform.rotozoom(spr, -math.degrees(ang) * 0.6, scale)
        spr.set_alpha(int(255 * (1 - clamp((u - 0.7) / 0.3, 0.0, 1.0))))
        sf.blit(spr, (pos.x - spr.get_width() / 2, pos.y - spr.get_height() / 2))

    # ---- draw ------------------------------------------------------------
    def draw(self, screen):
        sf = pygame.Surface((W, H))
        # --- baked tile floor + walls (one blit instead of a live grid) -----
        sf.blit(self.bg, (0, 0))

        # --- floor decals: scorch marks left by kills ------------------------
        for pos, col, rad in self.decals:
            d = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
            pygame.draw.ellipse(d, (*col, 80), (0, rad * 0.35, rad * 2, rad * 1.2))
            sf.blit(d, (pos.x - rad, pos.y - rad))

        for pk in self.pickups:
            near = (not self.inv.room(pk.iid)) and pk.pos.distance_to(self.player.pos) < 60
            pk.draw(sf, self.time, near, self.small)
        if self.state != "won":
            self.draw_twist_under(sf)
        for z in self.zones:
            z.draw(sf)
        for m in self.player.mines:
            m.draw(sf)
        for rg in self.rings:
            pos, col, t, rad = rg
            a = 1 - t / 0.35
            pygame.draw.circle(sf, col, pos, int(rad * (0.4 + t * 2)), max(1, int(3 * a)))
        for bm in self.beams:
            p1, p2, col, t, maxt, width = bm
            a = clamp(t / maxt, 0, 1)
            beam_surf = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.line(beam_surf, (*col, int(220 * a)), p1, p2, max(1, int(width * a) + 1))
            sf.blit(beam_surf, (0, 0))

        self.draw_portal(sf)

        # --- depth sort everything that stands on the floor ------------------
        standing = list(self.enemies)
        if self.enter_t is None:
            self.draw_buff_auras(sf)
            standing.append(self.player)
        if self.relay:
            standing.append(self.relay)
        for ent in sorted(standing, key=lambda x: x.pos.y):
            ent.draw(sf)

        if self.enter_t is not None:
            self.draw_entering_player(sf)

        for pr in self.projectiles:
            pr.draw(sf)
        for q in self.particles:
            q.draw(sf)

        # --- drifting dust motes give the arena some air ---------------------
        for m in self.motes:
            r = max(1, int(m[3]))
            mote = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(mote, (150, 160, 190, 48), (r, r), r)
            sf.blit(mote, (m[0].x - r, m[0].y - r))

        if self.state != "won":
            self.draw_twist_over(sf)
        sf.blit(self.vignette, (0, 0))

        for n in self.numbers:
            img = self.small.render(n[1], True, n[2])
            img.set_alpha(int(255 * clamp(n[3] / 0.8, 0, 1)))
            sh = self.small.render(n[1], True, (10, 10, 14))
            sh.set_alpha(int(190 * clamp(n[3] / 0.8, 0, 1)))
            sf.blit(sh, (n[0].x + 1, n[0].y + 1))
            sf.blit(img, n[0])

        # low-HP danger pulse: a soft red heartbeat over the whole arena,
        # separate from the per-hit white flash, so being low feels tense
        # even between hits
        if self.player.hp_frac < 0.3:
            beat = 0.5 + 0.5 * math.sin(self.time * 6.0)
            danger = pygame.Surface((W, H), pygame.SRCALPHA)
            a = int(70 * (1 - self.player.hp_frac / 0.3) * beat)
            for i in range(18):
                pygame.draw.rect(danger, (140, 20, 20, max(0, a - i * 4)),
                                 (i * 2, i * 2, W - i * 4, H - i * 4), 2)
            sf.blit(danger, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        self.draw_hud(sf)

        if self.banner_t > 0:
            img = self.bigfont.render(self.banner_text, True, YELLOW)
            sf.blit(img, (W / 2 - img.get_width() / 2, ARENA.top + 40))
            if self.banner_sub:
                sub_img = self.small.render(self.banner_sub, True, WHITE)
                sf.blit(sub_img, (W / 2 - sub_img.get_width() / 2, ARENA.top + 40 + img.get_height() + 6))

        # warp flash: builds through the second half of the suck-in and hands
        # off to App.flash, which fades the next scene in from the same colour
        if self.enter_t is not None:
            u = clamp((self.enter_t / self.ENTER_TIME - 0.5) / 0.5, 0.0, 1.0)
            if u > 0:
                fl = pygame.Surface((W, H))
                fl.fill(lite(self.portal_col, 0.8))
                fl.set_alpha(int(255 * u * u))
                sf.blit(fl, (0, 0))

        ox = random.uniform(-self.shake, self.shake)
        oy = random.uniform(-self.shake, self.shake)
        if self.punch > 0.002:
            # quick zoom-in punch on heavy impacts, riding the same timer
            # as the existing hit-stop/shake so hits land with more weight
            zoom = 1 + min(0.05, self.punch)
            zw, zh = int(W * zoom), int(H * zoom)
            zoomed = pygame.transform.smoothscale(sf, (zw, zh))
            screen.blit(zoomed, (ox - (zw - W) / 2, oy - (zh - H) / 2))
        else:
            screen.blit(sf, (ox, oy))

    def draw_hud(self, sf):
        p = self.player
        pygame.draw.rect(sf, (12, 14, 20), (0, 0, W, 104))
        pygame.draw.line(sf, DGREY, (0, 104), (W, 104))

        # portrait + name
        sf.blit(pygame.transform.scale(p.spr, (40, 50)), (18, 24))
        sf.blit(self.font.render(self.c["name"], True, WHITE), (66, 20))
        sf.blit(self.small.render(self.c["cls"] + " / " + self.c["role"], True, GREY), (66, 42))

        # hp bar
        bw = 300
        pygame.draw.rect(sf, (30, 33, 44), (66, 62, bw, 16), border_radius=4)
        col = GREEN if p.hp_frac > 0.5 else (YELLOW if p.hp_frac > 0.25 else RED)
        pygame.draw.rect(sf, col, (66, 62, bw * p.hp_frac, 16), border_radius=4)
        pygame.draw.rect(sf, DGREY, (66, 62, bw, 16), 1, border_radius=4)
        sf.blit(self.small.render("%d / %d" % (max(0, int(p.hp)), self.maxhp_i()), True, WHITE), (72, 63))

        # passive state
        notes = []
        if self.c["id"] == "vex":
            notes.append("STACKS %d" % p.stacks)
            if p.hp_frac < 0.35:
                notes.append("OVEREXPOSED")
            if p.empowered:
                notes.append("SHADOW READY")
        if self.c["id"] == "garran":
            notes.append("DR %d%%" % int(45 * (1 - p.hp_frac)))
        if self.c["id"] == "bram":
            notes.append("COMBO %d/3" % (p.combo % 3))
        if self.c["id"] == "kite":
            notes.append("RELOADING" if p.reloading > 0 else "AMMO %d/12" % p.ammo)
        if notes:
            sf.blit(self.small.render("  ".join(notes), True, CYAN), (66, 82))

        # skills
        x = W - 300
        for label, cd, maxcd in (("Q", p.cdq, self.c["q"][2]), ("E", p.cde, self.c["e"][2]),
                                 ("SPC", p.cdd, 2.2)):
            r = pygame.Rect(x, 26, 64, 52)
            ready = cd <= 0
            pygame.draw.rect(sf, (34, 38, 52) if ready else (24, 26, 34), r, border_radius=6)
            pygame.draw.rect(sf, self.c["colors"][1] if ready else DGREY, r, 2, border_radius=6)
            if not ready:
                fh = int(r.h * (cd / maxcd))
                pygame.draw.rect(sf, (40, 44, 60), (r.x, r.bottom - fh, r.w, fh), border_radius=6)
                sf.blit(self.small.render("%0.1f" % cd, True, GREY), (r.x + 20, r.y + 18))
            else:
                sf.blit(self.font.render(label, True, WHITE), (r.x + 8, r.y + 12))
            x += 74

        # objective
        txt = self.objective_text()
        img = self.font.render(txt, True, YELLOW)
        sf.blit(img, (W / 2 - img.get_width() / 2, 14))
        pb = pygame.Rect(W / 2 - 150, 42, 300, 8)
        pygame.draw.rect(sf, (30, 33, 44), pb, border_radius=4)
        pygame.draw.rect(sf, YELLOW, (pb.x, pb.y, pb.w * self.progress(), pb.h), border_radius=4)
        sf.blit(self.small.render(self.ch["name"], True, GREY),
                (W / 2 - self.small.size(self.ch["name"])[0] / 2, 56))
        label = self.twist_label()
        if label:
            limg = self.small.render(label, True, self.portal_col)
            sf.blit(limg, (W / 2 - limg.get_width() / 2, 74))
        dname = self.diff["name"]
        dcol = GREEN if dname == "EASY" else (RED if dname == "HARD" else YELLOW)
        sf.blit(self.small.render(dname, True, dcol), (W - 90, 14))
        coin_txt = "COINS +%d" % self.coins_earned
        img = self.small.render(coin_txt, True, YELLOW)
        sf.blit(img, (W - 16 - img.get_width(), 34))

        # footer
        foot = "WASD move   MOUSE aim   LMB attack   Q %s   E %s   SPACE dodge   1-5 potion   TAB bag   ESC pause" % (
            self.c["q"][0], self.c["e"][0])
        sf.blit(self.small.render(foot, True, DGREY), (24, H - 26))
        self.draw_belt(sf)

    def maxhp_i(self):
        return int(self.player.maxhp)


# ----------------------------------------------------------------------------
# UI HELPERS
# ----------------------------------------------------------------------------
def wrap(font, text, width):
    words = text.split(" ")
    lines, cur = [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if font.size(t)[0] > width and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def draw_radar(sf, cx, cy, r, stats, color, font):
    keys = ["DMG", "RNG", "SPD", "DEF", "UTL"]
    ang = [-math.pi / 2 + i * math.tau / 5 for i in range(5)]
    for ring in (0.25, 0.5, 0.75, 1.0):
        pts = [(cx + math.cos(a) * r * ring, cy + math.sin(a) * r * ring) for a in ang]
        pygame.draw.polygon(sf, DGREY if ring == 1.0 else GRID, pts, 1)
    for a in ang:
        pygame.draw.line(sf, GRID, (cx, cy), (cx + math.cos(a) * r, cy + math.sin(a) * r))
    pts = []
    for i, k in enumerate(keys):
        v = clamp(stats[k] / 10, 0.08, 1.0)
        pts.append((cx + math.cos(ang[i]) * r * v, cy + math.sin(ang[i]) * r * v))
    poly = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.polygon(poly, (*color, 90), pts)
    sf.blit(poly, (0, 0))
    pygame.draw.polygon(sf, color, pts, 2)
    for i, k in enumerate(keys):
        lx = cx + math.cos(ang[i]) * (r + 24)
        ly = cy + math.sin(ang[i]) * (r + 20)
        img = font.render("%s %d" % (k, stats[k]), True, GREY)
        sf.blit(img, (lx - img.get_width() / 2, ly - 7))


# ----------------------------------------------------------------------------
# APP
# ----------------------------------------------------------------------------
class App:
    def __init__(self, screen):
        self.screen = screen
        self.big = pygame.font.Font(None, 40)
        self.mid = pygame.font.Font(None, 26)
        self.small = pygame.font.Font(None, 20)
        self.tiny = pygame.font.Font(None, 17)
        self.scene = "title"
        self.slots = load_saves()
        self.slot_index = 0
        self.slot_sel = 0
        self.flash = 0.0          # scene-change flash that fades out (portal warp)
        self.flash_col = WHITE
        self.del_confirm = None   # slot index awaiting delete confirmation
        self.del_choice = 0       # 0 = CANCEL (default), 1 = DELETE
        self.levels_gained = 0
        self.sel = 0
        self.diff_sel = 1
        self.char = None
        self.chapter = 0
        self.story_page = 0
        self.story_mode = "intro"
        self.game = None
        self.paused = False
        self.pause_sel = 0
        self.inv = Inventory()          # the bag for the current run
        self.inv_snap = Inventory()     # the bag as it was when this chapter began
        self.inv_open = False
        self.inv_sel = 0
        self.pause_items = ["RESUME", "RESTART CHAPTER", "CHANGE OPERATIVE", "QUIT TO TITLE"]
        self.t = 0.0

    def slot(self):
        return self.slots[self.slot_index]

    def enter_slot(self, i):
        """Open a save slot -- skip difficulty select entirely if this slot
        already locked one in, so the choice can never be revisited."""
        self.slot_index = i
        slot = self.slots[i]
        if slot.get("diff"):
            self.diff_sel = next((idx for idx, d in enumerate(DIFFICULTIES)
                                   if d["id"] == slot["diff"]), 1)
            self.scene = "select"
        else:
            self.scene = "diff"

    def lock_difficulty(self):
        """Confirm the diff scene -- writes the choice into the slot the
        first time only, permanently locking it in for that save."""
        slot = self.slot()
        if not slot.get("diff"):
            slot["diff"] = DIFFICULTIES[self.diff_sel]["id"]
            write_saves(self.slots)
        self.scene = "select"

    def ask_delete(self, i):
        """Open the delete confirmation for slot i (only if it has data)."""
        if slot_has_data(self.slots[i]):
            self.del_confirm = i
            self.del_choice = 0   # default to CANCEL so a stray Enter is safe

    def do_delete(self):
        i = self.del_confirm
        if i is not None:
            self.slots[i] = new_slot()
            write_saves(self.slots)
        self.del_confirm = None

    def go_back(self):
        if self.scene == "select":
            self.scene = "saves"
        elif self.scene == "diff":
            self.scene = "saves"
        elif self.scene == "saves":
            self.scene = "title"

    # ---- events ----------------------------------------------------------
    def handle(self, ev):
        if ev.type == pygame.KEYDOWN:
            if self.scene == "title":
                self.scene = "saves"
            elif self.scene == "saves" and self.del_confirm is not None:
                # delete-confirmation dialog swallows all other input
                if ev.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_a, pygame.K_d, pygame.K_TAB):
                    self.del_choice = 1 - self.del_choice
                elif ev.key == pygame.K_y:
                    self.del_choice = 1
                    self.do_delete()
                elif ev.key in (pygame.K_n, pygame.K_ESCAPE):
                    self.del_confirm = None
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    if self.del_choice == 1:
                        self.do_delete()
                    else:
                        self.del_confirm = None
            elif self.scene == "saves":
                if ev.key in (pygame.K_DOWN, pygame.K_s):
                    self.slot_sel = (self.slot_sel + 1) % NUM_SLOTS
                elif ev.key in (pygame.K_UP, pygame.K_w):
                    self.slot_sel = (self.slot_sel - 1) % NUM_SLOTS
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self.enter_slot(self.slot_sel)
                elif ev.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                    self.ask_delete(self.slot_sel)
                elif ev.key == pygame.K_ESCAPE:
                    self.go_back()
            elif self.scene == "diff":
                if ev.key in (pygame.K_RIGHT, pygame.K_d):
                    self.diff_sel = (self.diff_sel + 1) % len(DIFFICULTIES)
                elif ev.key in (pygame.K_LEFT, pygame.K_a):
                    self.diff_sel = (self.diff_sel - 1) % len(DIFFICULTIES)
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self.lock_difficulty()
                elif ev.key == pygame.K_ESCAPE:
                    self.go_back()
            elif self.scene == "select":
                if ev.key in (pygame.K_RIGHT, pygame.K_d):
                    self.sel = (self.sel + 1) % len(CHARACTERS)
                elif ev.key in (pygame.K_LEFT, pygame.K_a):
                    self.sel = (self.sel - 1) % len(CHARACTERS)
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self.confirm_select()
                elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                    idx = (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5).index(ev.key)
                    self.spend_point(STAT_KEYS[idx])
                elif ev.key == pygame.K_ESCAPE:
                    self.go_back()
            elif self.scene == "story":
                if ev.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                    self.advance_story()
                elif ev.key == pygame.K_ESCAPE:
                    self.finish_story()
            elif self.scene == "play":
                if self.inv_open:
                    self.handle_inv_key(ev.key)
                elif not self.paused:
                    if ev.key == pygame.K_ESCAPE:
                        self.paused = True
                        self.pause_sel = 0
                    elif ev.key in (pygame.K_TAB, pygame.K_i):
                        self.inv_open = True
                        self.inv_sel = 0
                    elif ev.key in POTION_KEYS and self.game.state == "play":
                        self.game.use_item(ITEM_ORDER[POTION_KEYS.index(ev.key)])
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.game.state == "won":
                        self.game.begin_enter()   # shortcut: jump straight into the open portal
                else:
                    if ev.key == pygame.K_ESCAPE:
                        self.paused = False
                    elif ev.key in (pygame.K_DOWN, pygame.K_s):
                        self.pause_sel = (self.pause_sel + 1) % len(self.pause_items)
                    elif ev.key in (pygame.K_UP, pygame.K_w):
                        self.pause_sel = (self.pause_sel - 1) % len(self.pause_items)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        self.do_pause_action(self.pause_items[self.pause_sel])
            elif self.scene == "result":
                if ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.game.state == "won":
                        self.story_mode = "outro"
                        self.story_page = 0
                        self.scene = "story"
                    else:
                        self.game = self.make_game(retry=True)
                        self.scene = "play"
                elif ev.key == pygame.K_c:
                    self.scene = "select"
        if ev.type == pygame.MOUSEBUTTONDOWN and self.scene == "saves" and self.del_confirm is not None:
            cancel_r, del_r = self.del_dialog_buttons()
            if cancel_r.collidepoint(ev.pos):
                self.del_confirm = None
            elif del_r.collidepoint(ev.pos):
                self.do_delete()
        elif ev.type == pygame.MOUSEBUTTONDOWN and self.scene == "saves":
            if self.back_rect().collidepoint(ev.pos):
                self.go_back()
            else:
                for i, r in enumerate(self.slot_rects()):
                    # the DELETE button sits inside the card, so test it first
                    if slot_has_data(self.slots[i]) and self.slot_delete_rect(i).collidepoint(ev.pos):
                        self.slot_sel = i
                        self.ask_delete(i)
                        break
                    if r.collidepoint(ev.pos):
                        if self.slot_sel == i:
                            self.enter_slot(i)
                        self.slot_sel = i
                        break
        if ev.type == pygame.MOUSEBUTTONDOWN and self.scene == "diff":
            if self.back_rect().collidepoint(ev.pos):
                self.go_back()
            for i, r in enumerate(self.diff_rects()):
                if r.collidepoint(ev.pos):
                    if self.diff_sel == i:
                        self.lock_difficulty()
                    self.diff_sel = i
        if ev.type == pygame.MOUSEBUTTONDOWN and self.scene == "select":
            if self.back_rect().collidepoint(ev.pos):
                self.go_back()
            for i, r in enumerate(self.card_rects()):
                if r.collidepoint(ev.pos):
                    if self.sel == i:
                        self.confirm_select()
                    self.sel = i
            if self.confirm_rect().collidepoint(ev.pos):
                self.confirm_select()
            for i, r in enumerate(self.stat_rects()):
                if r.collidepoint(ev.pos):
                    self.spend_point(STAT_KEYS[i])
        if ev.type == pygame.MOUSEBUTTONDOWN and self.scene == "play" and self.inv_open:
            if getattr(ev, "button", 1) == 1:
                for i, r in enumerate(self.inv_rects()):
                    if r.collidepoint(ev.pos):
                        self.inv_use(i)
                        break
                else:
                    if not self.inv_panel_rect().collidepoint(ev.pos):
                        self.inv_open = False
        if ev.type == pygame.MOUSEMOTION and self.scene == "play" and self.inv_open:
            for i, r in enumerate(self.inv_rects()):
                if r.collidepoint(ev.pos):
                    self.inv_sel = i
        if ev.type == pygame.MOUSEBUTTONDOWN and self.scene == "play" and self.paused:
            for i, r in enumerate(self.pause_rects()):
                if r.collidepoint(ev.pos):
                    self.pause_sel = i
                    self.do_pause_action(self.pause_items[i])
        if ev.type == pygame.MOUSEMOTION and self.scene == "play" and self.paused:
            for i, r in enumerate(self.pause_rects()):
                if r.collidepoint(ev.pos):
                    self.pause_sel = i

    def handle_inv_key(self, key):
        n = len(ITEM_ORDER)
        if key in (pygame.K_ESCAPE, pygame.K_TAB, pygame.K_i):
            self.inv_open = False
        elif key in POTION_KEYS:
            self.inv_use(POTION_KEYS.index(key))
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.inv_sel = (self.inv_sel + 1) % n
        elif key in (pygame.K_UP, pygame.K_w):
            self.inv_sel = (self.inv_sel - 1) % n
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.inv_use(self.inv_sel)

    def inv_use(self, i):
        self.inv_sel = i
        self.game.use_item(ITEM_ORDER[i])

    def make_game(self, retry=False):
        """Start the current chapter. The bag carries over from the last one; a
        retry rewinds it to how it was when this chapter began."""
        if retry:
            self.inv = self.inv_snap.copy()
        else:
            self.inv_snap = self.inv.copy()
        self.inv_open = False
        return Game(self.char, self.chapter, self.mid, self.big, self.small,
                    DIFFICULTIES[self.diff_sel], inv=self.inv)

    def do_pause_action(self, action):
        if action == "RESUME":
            self.paused = False
        elif action == "RESTART CHAPTER":
            self.game = self.make_game(retry=True)
            self.paused = False
        elif action == "CHANGE OPERATIVE":
            self.paused = False
            self.inv_open = False
            self.scene = "select"
        elif action == "QUIT TO TITLE":
            self.paused = False
            self.game = None
            self.char = None
            self.scene = "title"

    def pause_rects(self):
        n = len(self.pause_items)
        bw, bh, gap = 260, 44, 12
        y0 = H / 2 - 30
        return [pygame.Rect(W / 2 - bw / 2, y0 + i * (bh + gap), bw, bh) for i in range(n)]

    def confirm_select(self):
        base = CHARACTERS[self.sel]
        slot = self.slot()
        locked = base["id"] not in slot["classes"] and len(slot["classes"]) > 0
        if not locked:
            self.start_run()
        elif slot["coins"] >= UNLOCK_COST:
            slot["coins"] -= UNLOCK_COST
            self.start_run()

    def spend_point(self, stat):
        base = CHARACTERS[self.sel]
        csave = self.slot()["classes"].get(base["id"])
        if csave and csave["unspent"] > 0:
            csave["unspent"] -= 1
            csave["points"][stat] += 1
            write_saves(self.slots)

    def start_run(self):
        base = CHARACTERS[self.sel]
        slot = self.slot()
        csave = ensure_class(slot, base["id"])
        write_saves(self.slots)
        self.char = effective_char(base, csave)
        self.inv = Inventory({"heal": 1})       # every run starts with one healing potion
        self.inv_snap = self.inv.copy()
        self.inv_open = False
        self.chapter = 0
        self.story_mode = "intro"
        self.story_page = 0
        self.scene = "story"

    def commit_progress(self):
        slot = self.slot()
        csave = slot["classes"].get(self.char["id"])
        if csave is None:
            self.levels_gained = 0
            return
        xp = self.game.xp_earned
        if self.game.state == "won":
            xp += 30 + 18 * self.chapter
        self.levels_gained = grant_xp(csave, xp)
        slot["coins"] += self.game.coins_earned
        write_saves(self.slots)

    def advance_story(self):
        lines = CHAPTERS[self.chapter][self.story_mode]
        self.story_page += 1
        if self.story_page >= len(lines):
            self.finish_story()

    def begin_outro(self):
        """Warp finished: fade in from the portal flash straight into the dialog."""
        self.flash = 1.0
        self.flash_col = lite(self.game.portal_col, 0.8)
        self.story_mode = "outro"
        self.story_page = 0
        self.scene = "story"

    def finish_story(self):
        if self.story_mode == "intro":
            self.game = self.make_game()
            self.scene = "play"
        else:
            self.chapter += 1
            if self.chapter >= len(CHAPTERS):
                self.scene = "credits"
            else:
                self.story_mode = "intro"
                self.story_page = 0
                self.scene = "story"

    # ---- update ----------------------------------------------------------
    def update(self, dt, keys, mpos, mdown):
        self.t += dt
        self.flash = max(0.0, self.flash - dt * 1.4)
        if self.scene == "play" and not self.paused and not self.inv_open:
            self.game.update(dt, keys, mpos, mdown)
            if self.game.state == "lost":
                self.scene = "result"
                self.commit_progress()
            elif self.game.state == "won":
                if not self.game.rewarded:      # first frame of the win: bank rewards
                    self.game.rewarded = True
                    self.commit_progress()
                if self.game.portal_done:
                    self.begin_outro()

    # ---- drawing ---------------------------------------------------------
    def card_rects(self):
        n = len(CHARACTERS)
        cw, chh, gap = 112, 132, 14
        total = n * cw + (n - 1) * gap
        x0 = W / 2 - total / 2
        return [pygame.Rect(x0 + i * (cw + gap), H - chh - 28, cw, chh) for i in range(n)]

    def confirm_rect(self):
        # top-right corner: nothing else is drawn there across any character,
        # unlike the lower info column which the button used to sit on top of
        return pygame.Rect(W - 226, 14, 210, 42)

    def back_rect(self):
        # placed differently per scene so it never sits under other UI:
        # the select screen already has a coin badge in the far top-left
        if self.scene == "select":
            return pygame.Rect(16, 50, 92, 28)
        return pygame.Rect(16, 16, 92, 30)

    def slot_rects(self):
        n = NUM_SLOTS
        cw, ch_, gap = 260, 320, 30
        total = n * cw + (n - 1) * gap
        x0 = W / 2 - total / 2
        y0 = H / 2 - ch_ / 2 - 10
        return [pygame.Rect(x0 + i * (cw + gap), y0, cw, ch_) for i in range(n)]

    def slot_delete_rect(self, i):
        r = self.slot_rects()[i]
        return pygame.Rect(r.right - 96, r.bottom - 40, 80, 26)

    def del_dialog_rect(self):
        return pygame.Rect(W / 2 - 250, H / 2 - 115, 500, 230)

    def del_dialog_buttons(self):
        d = self.del_dialog_rect()
        return (pygame.Rect(d.centerx - 170, d.bottom - 78, 150, 40),   # CANCEL
                pygame.Rect(d.centerx + 20, d.bottom - 78, 150, 40))    # DELETE

    def stat_rects(self):
        n = len(STAT_KEYS)
        bw, gap = 34, 6
        x0 = W - 300
        y = 424
        return [pygame.Rect(x0 + i * (bw + gap), y, bw, bw) for i in range(n)]

    def draw(self):
        sf = self.screen
        if self.scene == "title":
            self.draw_title(sf)
        elif self.scene == "saves":
            self.draw_saves(sf)
        elif self.scene == "diff":
            self.draw_diff(sf)
        elif self.scene == "select":
            self.draw_select(sf)
        elif self.scene == "story":
            self.draw_story(sf)
        elif self.scene == "play":
            self.game.draw(sf)
            if self.game.state == "won" and self.game.enter_t is None:
                self.draw_clear_panel(sf)
            if self.paused:
                self.draw_pause_menu(sf)
            elif self.inv_open:
                self.draw_inventory(sf)
        elif self.scene == "result":
            self.game.draw(sf)
            csave = self.slot()["classes"].get(self.char["id"], {})
            prog = "Coins +%d     XP +%d     LEVEL %d" % (
                self.game.coins_earned, self.game.xp_earned, csave.get("level", 1))
            if self.levels_gained:
                prog += "     LEVEL UP!"
            if self.game.state == "won":
                self.overlay(sf, "OBJECTIVE COMPLETE", [
                    "Kills: %d     Time: %0.1fs" % (self.game.kills, self.game.time),
                    (prog, YELLOW),
                    "ENTER to continue     C to change operative"], GREEN)
            else:
                self.overlay(sf, "YOU WENT DOWN", [
                    "Kills: %d     Time: %0.1fs" % (self.game.kills, self.game.time),
                    (prog, YELLOW),
                    "ENTER to retry     C to change operative"], RED)
        elif self.scene == "credits":
            self.draw_credits(sf)
        if self.flash > 0:
            fl = pygame.Surface((W, H))
            fl.fill(self.flash_col)
            fl.set_alpha(int(255 * self.flash))
            sf.blit(fl, (0, 0))

    def draw_clear_panel(self, sf):
        """Rewards + prompt shown along the bottom while the portal is open."""
        g = self.game
        csave = self.slot()["classes"].get(self.char["id"], {})
        prog = "Coins +%d     XP +%d     LEVEL %d" % (
            g.coins_earned, g.xp_earned + 30 + 18 * self.chapter, csave.get("level", 1))
        if self.levels_gained:
            prog += "     LEVEL UP!"
        # opaque strip (same look as the top HUD) so it replaces the controls footer
        pygame.draw.rect(sf, (12, 14, 20), (0, H - 70, W, 70))
        pygame.draw.line(sf, DGREY, (0, H - 70), (W, H - 70))
        im = self.mid.render(prog, True, YELLOW)
        sf.blit(im, (W / 2 - im.get_width() / 2, H - 58))
        if g.portal_ready():
            msg, col = "Walk into the portal to continue   (or press ENTER)", lite(g.portal_col, 0.6)
        else:
            msg, col = "Stage cleared...", GREY
        im = self.small.render(msg, True, col)
        sf.blit(im, (W / 2 - im.get_width() / 2, H - 30))

    def overlay(self, sf, title, lines, col=WHITE):
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        sf.blit(ov, (0, 0))
        img = self.big.render(title, True, col)
        sf.blit(img, (W / 2 - img.get_width() / 2, H / 2 - 60))
        for i, l in enumerate(lines):
            lcol = l[1] if isinstance(l, tuple) else WHITE
            ltext = l[0] if isinstance(l, tuple) else l
            im = self.mid.render(ltext, True, lcol)
            sf.blit(im, (W / 2 - im.get_width() / 2, H / 2 + i * 30))

    def inv_panel_rect(self):
        return pygame.Rect(W / 2 - 330, H / 2 - 260, 660, 520)

    def inv_rects(self):
        pr = self.inv_panel_rect()
        return [pygame.Rect(pr.x + 20, pr.y + 82 + i * 68, pr.w - 40, 62) for i in range(len(ITEM_ORDER))]

    def draw_inventory(self, sf):
        g = self.game
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 175))
        sf.blit(ov, (0, 0))
        pr = self.inv_panel_rect()
        pygame.draw.rect(sf, (20, 23, 32), pr, border_radius=10)
        pygame.draw.rect(sf, DGREY, pr, 2, border_radius=10)
        sf.blit(self.big.render("INVENTORY", True, WHITE), (pr.x + 24, pr.y + 16))
        sf.blit(self.small.render("Potions carry over between chapters. Fallen enemies drop them.", True, GREY),
                (pr.x + 24, pr.y + 52))
        for i, (iid, r) in enumerate(zip(ITEM_ORDER, self.inv_rects())):
            it = ITEMS[iid]
            col = it["col"]
            n = g.inv.count(iid)
            has = n > 0
            sel = i == self.inv_sel
            pygame.draw.rect(sf, (34, 38, 52) if sel else (26, 29, 40), r, border_radius=8)
            pygame.draw.rect(sf, col if sel else DGREY, r, 2 if sel else 1, border_radius=8)
            spr = potion_sprite(iid)
            if not has:
                spr = spr.copy()
                spr.set_alpha(80)
            sf.blit(spr, (r.x + 16, r.centery - spr.get_height() / 2))
            sf.blit(self.mid.render(it["name"], True, WHITE if has else DGREY), (r.x + 64, r.y + 10))
            sf.blit(self.small.render(it["desc"], True, GREY if has else DGREY), (r.x + 64, r.y + 36))
            sf.blit(self.small.render("[%d]" % (i + 1), True, col), (r.right - 186, r.centery - 8))
            cimg = self.mid.render("x%d / %d" % (n, it["cap"]), True, WHITE if has else DGREY)
            sf.blit(cimg, (r.right - 146, r.centery - cimg.get_height() / 2))
            ub = pygame.Rect(r.right - 62, r.y + 15, 50, 32)
            pygame.draw.rect(sf, col if has else (30, 33, 44), ub, border_radius=6)
            uimg = self.small.render("USE", True, BLACK if has else DGREY)
            sf.blit(uimg, (ub.centerx - uimg.get_width() / 2, ub.centery - uimg.get_height() / 2))
        ay = self.inv_rects()[-1].bottom + 14
        sf.blit(self.small.render("ACTIVE EFFECTS", True, GREY), (pr.x + 24, ay))
        x, y = pr.x + 24, ay + 24
        active = [(k, t) for k, t in g.player.pot.items() if t > 0]
        if not active:
            sf.blit(self.small.render("none", True, DGREY), (x, y))
        for k, t in active:
            img = self.small.render("%s  %ds" % (ITEMS[k]["tag"], math.ceil(t)), True, ITEMS[k]["col"])
            chip = pygame.Rect(x, y - 3, img.get_width() + 16, 24)
            pygame.draw.rect(sf, (30, 34, 46), chip, border_radius=6)
            pygame.draw.rect(sf, ITEMS[k]["col"], chip, 1, border_radius=6)
            sf.blit(img, (chip.x + 8, chip.y + 4))
            x += chip.w + 10
        hint = self.tiny.render("1-5 or click to drink     UP/DOWN + ENTER     TAB / ESC to close", True, DGREY)
        sf.blit(hint, (W / 2 - hint.get_width() / 2, pr.bottom - 26))

    def draw_pause_menu(self, sf):
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 175))
        sf.blit(ov, (0, 0))
        title = self.big.render("PAUSED", True, WHITE)
        sf.blit(title, (W / 2 - title.get_width() / 2, H / 2 - 130))
        for i, (label, r) in enumerate(zip(self.pause_items, self.pause_rects())):
            selp = (i == self.pause_sel)
            pygame.draw.rect(sf, (34, 38, 52) if selp else (24, 27, 37), r, border_radius=6)
            col = self.char["colors"][1] if self.char else CYAN
            pygame.draw.rect(sf, col if selp else DGREY, r, 3 if selp else 1, border_radius=6)
            im = self.mid.render(label, True, WHITE if selp else GREY)
            sf.blit(im, (r.centerx - im.get_width() / 2, r.centery - im.get_height() / 2))
        hint = self.tiny.render("UP/DOWN or mouse to choose   ENTER/click to confirm   ESC to resume", True, DGREY)
        sf.blit(hint, (W / 2 - hint.get_width() / 2, self.pause_rects()[-1].bottom + 18))

    def draw_title(self, sf):
        sf.fill(BG)
        for i in range(40):
            x = (i * 137 + int(self.t * 30)) % W
            pygame.draw.line(sf, GRID, (x, 0), (x - 60, H))
        t1 = pygame.font.Font(None, 96).render("ARCLIGHT", True, WHITE)
        t2 = self.big.render("F R O N T L I N E", True, CYAN)
        sf.blit(t1, (W / 2 - t1.get_width() / 2, 170 + OY))
        sf.blit(t2, (W / 2 - t2.get_width() / 2, 250 + OY))
        sub = "Seven operatives. Four chapters. One relay still lit."
        im = self.mid.render(sub, True, GREY)
        sf.blit(im, (W / 2 - im.get_width() / 2, 320 + OY))
        if math.sin(self.t * 3) > -0.3:
            im = self.mid.render("PRESS ANY KEY", True, YELLOW)
            sf.blit(im, (W / 2 - im.get_width() / 2, 420 + OY))
        im2 = self.tiny.render("F11 fullscreen", True, DGREY)
        sf.blit(im2, (W - im2.get_width() - 16, H - 22))

    def draw_back_button(self, sf, label="< BACK"):
        r = self.back_rect()
        pygame.draw.rect(sf, (26, 29, 40), r, border_radius=6)
        pygame.draw.rect(sf, DGREY, r, 1, border_radius=6)
        im = self.tiny.render(label, True, GREY)
        sf.blit(im, (r.centerx - im.get_width() / 2, r.centery - im.get_height() / 2))

    def draw_saves(self, sf):
        sf.fill(BG)
        self.draw_back_button(sf)
        im = self.big.render("SELECT SAVE FILE", True, WHITE)
        sf.blit(im, (W / 2 - im.get_width() / 2, 60))
        for i, r in enumerate(self.slot_rects()):
            slot = self.slots[i]
            selp = (i == self.slot_sel)
            pygame.draw.rect(sf, (30, 34, 46) if selp else (22, 25, 34), r, border_radius=8)
            pygame.draw.rect(sf, CYAN if selp else DGREY, r, 3 if selp else 1, border_radius=8)
            nm = self.big.render("SLOT %d" % (i + 1), True, WHITE if selp else GREY)
            sf.blit(nm, (r.centerx - nm.get_width() / 2, r.y + 22))
            if slot["classes"]:
                y = r.y + 84
                sf.blit(self.small.render("COINS: %d" % slot["coins"], True, YELLOW),
                        (r.x + 24, y))
                y += 32
                for cid, cs in list(slot["classes"].items())[:6]:
                    nm2 = CHAR_BY_ID[cid]["name"]
                    sf.blit(self.tiny.render("%s - LEVEL %d" % (nm2, cs["level"]), True, GREY),
                            (r.x + 24, y))
                    y += 20
            else:
                sf.blit(self.small.render("EMPTY", True, GREEN if selp else DGREY),
                        (r.centerx - 30, r.y + 100))
                sf.blit(self.tiny.render("first pick is free", True, DGREY),
                        (r.centerx - 52, r.y + 128))
            if slot.get("diff"):
                dname = next(d["name"] for d in DIFFICULTIES if d["id"] == slot["diff"])
                dcol = GREEN if dname == "EASY" else (RED if dname == "HARD" else YELLOW)
                sf.blit(self.tiny.render("DIFFICULTY: " + dname, True, dcol), (r.x + 24, r.bottom - 32))
            if slot_has_data(slot):
                dr = self.slot_delete_rect(i)
                hot = dr.collidepoint(pygame.mouse.get_pos()) and self.del_confirm is None
                pygame.draw.rect(sf, (74, 30, 34) if hot else (40, 24, 30), dr, border_radius=5)
                pygame.draw.rect(sf, RED, dr, 1, border_radius=5)
                dl = self.tiny.render("DELETE", True, RED if not hot else WHITE)
                sf.blit(dl, (dr.centerx - dl.get_width() / 2, dr.centery - dl.get_height() / 2))
        im = self.mid.render("UP/DOWN or click to choose   ENTER to open   DEL to delete slot",
                              True, DGREY)
        sf.blit(im, (W / 2 - im.get_width() / 2, H - 60))
        if self.del_confirm is not None:
            self.draw_delete_dialog(sf)

    def draw_delete_dialog(self, sf):
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 170))
        sf.blit(dim, (0, 0))
        d = self.del_dialog_rect()
        pygame.draw.rect(sf, (28, 22, 28), d, border_radius=10)
        pygame.draw.rect(sf, RED, d, 2, border_radius=10)
        t = self.big.render("DELETE SLOT %d?" % (self.del_confirm + 1), True, RED)
        sf.blit(t, (d.centerx - t.get_width() / 2, d.y + 20))
        y = d.y + 66
        for line in wrap(self.small, "All coins, levels and unlocked operatives in this save "
                                     "will be erased permanently. This can't be undone.", d.w - 60):
            im = self.small.render(line, True, GREY)
            sf.blit(im, (d.centerx - im.get_width() / 2, y))
            y += 22
        cancel_r, del_r = self.del_dialog_buttons()
        mp = pygame.mouse.get_pos()
        for idx, (br, label, col) in enumerate(((cancel_r, "CANCEL", GREY), (del_r, "DELETE", RED))):
            picked = (self.del_choice == idx) or br.collidepoint(mp)
            pygame.draw.rect(sf, (44, 48, 62) if idx == 0 else (92, 32, 38), br, border_radius=6)
            pygame.draw.rect(sf, WHITE if picked else col, br, 2 if picked else 1, border_radius=6)
            im = self.mid.render(label, True, WHITE if picked else col)
            sf.blit(im, (br.centerx - im.get_width() / 2, br.centery - im.get_height() / 2))
        hint = self.tiny.render("LEFT / RIGHT to choose   ENTER to confirm   ESC to cancel", True, DGREY)
        sf.blit(hint, (d.centerx - hint.get_width() / 2, d.bottom - 24))

    def diff_rects(self):
        n = len(DIFFICULTIES)
        cw, ch_, gap = 220, 260, 24
        total = n * cw + (n - 1) * gap
        x0 = W / 2 - total / 2
        y0 = H / 2 - ch_ / 2 - 10
        return [pygame.Rect(x0 + i * (cw + gap), y0, cw, ch_) for i in range(n)]

    def draw_diff(self, sf):
        sf.fill(BG)
        self.draw_back_button(sf)
        im = self.big.render("SELECT DIFFICULTY", True, WHITE)
        sf.blit(im, (W / 2 - im.get_width() / 2, 70))
        warn = self.tiny.render("This can't be changed later for this save slot.", True, ORANGE)
        sf.blit(warn, (W / 2 - warn.get_width() / 2, 100))
        for i, (d, r) in enumerate(zip(DIFFICULTIES, self.diff_rects())):
            selp = (i == self.diff_sel)
            col = {"EASY": GREEN, "NORMAL": YELLOW, "HARD": RED}[d["name"]]
            pygame.draw.rect(sf, (30, 34, 46) if selp else (22, 25, 34), r, border_radius=8)
            pygame.draw.rect(sf, col if selp else DGREY, r, 3 if selp else 1, border_radius=8)
            nm = self.big.render(d["name"], True, col if selp else GREY)
            sf.blit(nm, (r.centerx - nm.get_width() / 2, r.y + 24))
            y = r.y + 90
            for wl in wrap(self.small, d["desc"], r.w - 30):
                im2 = self.small.render(wl, True, WHITE if selp else GREY)
                sf.blit(im2, (r.centerx - im2.get_width() / 2, y))
                y += 22
            stat_lines = [
                "Enemy HP   x%.2f" % d["hp"],
                "Enemy DMG  x%.2f" % d["dmg"],
                "Spawn rate x%.2f" % (1.0 / d["interval"]),
            ]
            y = r.bottom - 78
            for sl in stat_lines:
                sf.blit(self.tiny.render(sl, True, DGREY if not selp else GREY), (r.centerx - 78, y))
                y += 20
        im = self.mid.render("A / D or click to choose   ENTER to confirm", True, DGREY)
        sf.blit(im, (W / 2 - im.get_width() / 2, H - 60))

    def draw_select(self, sf):
        sf.fill(BG)
        c = CHARACTERS[self.sel]
        slot = self.slot()
        csave = slot["classes"].get(c["id"])
        locked = csave is None and len(slot["classes"]) > 0
        pygame.draw.rect(sf, BG2, (0, 0, W, H - 176))
        pygame.draw.line(sf, DGREY, (0, H - 176), (W, H - 176))
        self.draw_back_button(sf)

        # left: big portrait + text
        big = pygame.transform.scale(hero_sprite(c), (180, 228))
        sf.blit(big, (72, 120))
        if locked:
            dim = pygame.Surface((180, 228), pygame.SRCALPHA)
            dim.fill((10, 11, 16, 150))
            sf.blit(dim, (72, 120))
        sf.blit(self.big.render(c["name"], True, WHITE), (290, 96))
        sf.blit(self.mid.render(c["title"], True, c["colors"][1]), (290, 134))
        sf.blit(self.small.render("%s  /  %s" % (c["role"], c["cls"]), True, GREY), (290, 162))

        y = 196
        sf.blit(self.small.render("PASSIVE - " + c["passive"][0], True, CYAN), (290, y))
        for l in wrap(self.tiny, c["passive"][1], 420):
            y += 18
            sf.blit(self.tiny.render(l, True, GREY), (290, y))
        y += 30
        for key, sk in (("Q", c["q"]), ("E", c["e"])):
            sf.blit(self.small.render("%s - %s  (%ss)" % (key, sk[0], sk[2]), True, YELLOW), (290, y))
            for l in wrap(self.tiny, sk[1], 420):
                y += 18
                sf.blit(self.tiny.render(l, True, GREY), (290, y))
            y += 26
        for l in wrap(self.tiny, '"' + c["bio"] + '"', 420):
            sf.blit(self.tiny.render(l, True, DGREY), (290, y))
            y += 17

        # right: radar
        draw_radar(sf, W - 190, 236, 108, c["stats"], c["colors"][1], self.tiny)
        sf.blit(self.small.render("HP %d   SPD %d   DMG %d" % (c["hp"], c["speed"], c["dmg"]),
                                  True, GREY), (W - 300, 374))

        # coin bank -- a persistent, obvious badge, not buried in the stat line
        coin_txt = "COIN BANK: %d" % slot["coins"]
        cimg = self.mid.render(coin_txt, True, YELLOW)
        pygame.draw.rect(sf, (30, 34, 46), (16, 12, cimg.get_width() + 24, 30), border_radius=6)
        pygame.draw.rect(sf, YELLOW, (16, 12, cimg.get_width() + 24, 30), 1, border_radius=6)
        sf.blit(cimg, (28, 18))

        # mastery panel: level/xp/stat points if owned, lock/unlock prompt otherwise
        if csave:
            lvl_txt = "LEVEL %d" % csave["level"]
            if csave["unspent"] > 0:
                lvl_txt += "   %d PT%s TO SPEND" % (csave["unspent"], "" if csave["unspent"] == 1 else "S")
            elif csave["level"] >= LEVEL_CAP:
                lvl_txt += "  (MAX)"
            sf.blit(self.small.render(lvl_txt, True, c["colors"][1]), (W - 300, 398))
            if csave["level"] < LEVEL_CAP:
                need = xp_for_level(csave["level"])
                bar = pygame.Rect(W - 300, 418, 226, 6)
                pygame.draw.rect(sf, DGREY, bar, border_radius=3)
                fill = bar.copy()
                fill.w = max(2, int(bar.w * clamp(csave["xp"] / need, 0, 1)))
                pygame.draw.rect(sf, c["colors"][1], fill, border_radius=3)
            for i, r in enumerate(self.stat_rects()):
                k = STAT_KEYS[i]
                can = csave["unspent"] > 0
                pygame.draw.rect(sf, (30, 34, 46), r, border_radius=4)
                pygame.draw.rect(sf, YELLOW if can else DGREY, r, 2 if can else 1, border_radius=4)
                sf.blit(self.tiny.render(k, True, WHITE if can else GREY), (r.x + 4, r.y + 3))
                sf.blit(self.tiny.render("+%d" % csave["points"][k], True, GREY), (r.x + 4, r.y + 17))
        elif locked:
            sf.blit(self.small.render("LOCKED", True, RED), (W - 300, 398))
            afford = slot["coins"] >= UNLOCK_COST
            sf.blit(self.tiny.render("UNLOCK FOR %d COINS" % UNLOCK_COST,
                                      True, YELLOW if afford else DGREY), (W - 300, 422))

        # bottom cards
        for i, r in enumerate(self.card_rects()):
            ch = CHARACTERS[i]
            selp = (i == self.sel)
            owned = ch["id"] in slot["classes"]
            pygame.draw.rect(sf, (30, 34, 46) if selp else (22, 25, 34), r, border_radius=6)
            pygame.draw.rect(sf, ch["colors"][1] if selp else DGREY, r, 3 if selp else 1, border_radius=6)
            sp = pygame.transform.scale(hero_sprite(ch), (54, 68))
            sf.blit(sp, (r.centerx - 27, r.y + 10))
            if not owned and slot["classes"]:
                dim = pygame.Surface((54, 68), pygame.SRCALPHA)
                dim.fill((10, 11, 16, 160))
                sf.blit(dim, (r.centerx - 27, r.y + 10))
            nm = self.small.render(ch["name"], True, WHITE if selp else GREY)
            sf.blit(nm, (r.centerx - nm.get_width() / 2, r.bottom - 38))
            cl = self.tiny.render(ch["cls"], True, ch["colors"][1] if selp else DGREY)
            sf.blit(cl, (r.centerx - cl.get_width() / 2, r.bottom - 20))
            if owned:
                sf.blit(self.tiny.render("Lv%d" % slot["classes"][ch["id"]]["level"], True, GREEN),
                        (r.x + 4, r.y + 4))

        cr = self.confirm_rect()
        if csave:
            label, col = "LOCK IN  (ENTER)", c["colors"][1]
        elif locked and slot["coins"] >= UNLOCK_COST:
            label, col = "UNLOCK & LOCK IN", YELLOW
        elif locked:
            label, col = "NEED MORE COINS", DGREY
        else:
            label, col = "LOCK IN  (ENTER)", c["colors"][1]
        pygame.draw.rect(sf, col, cr, border_radius=6)
        im = self.mid.render(label, True, BLACK)
        sf.blit(im, (cr.centerx - im.get_width() / 2, cr.centery - 9))
        sf.blit(self.tiny.render("A / D or click to browse operatives", True, DGREY), (40, H - 22))

    def draw_story(self, sf):
        sf.fill(BG)
        ch = CHAPTERS[self.chapter]
        lines = ch[self.story_mode]
        pygame.draw.rect(sf, BG2, (0, 120 + OY, W, 340))
        pygame.draw.line(sf, DGREY, (0, 120 + OY), (W, 120 + OY))
        pygame.draw.line(sf, DGREY, (0, 460 + OY), (W, 460 + OY))
        title = ch["name"] + ("" if self.story_mode == "intro" else "  -  AFTER ACTION")
        im = self.big.render(title, True, YELLOW)
        sf.blit(im, (80, 62 + OY))

        shown = lines[: self.story_page + 1]
        y = 170 + OY
        for i, l in enumerate(shown):
            col = WHITE if i == len(shown) - 1 else GREY
            for wl in wrap(self.mid, l, W - 200):
                sf.blit(self.mid.render(wl, True, col), (100, y))
                y += 32
            y += 12

        if self.story_mode == "intro":
            obj = {"kills": "OBJECTIVE: eliminate %d hostiles" % ch["target"],
                   "survive": "OBJECTIVE: survive %d seconds" % ch["target"],
                   "protect": "OBJECTIVE: keep the relay alive for %d seconds" % ch["target"],
                   "boss": "OBJECTIVE: defeat the Warden"}[ch["goal"]]
            sf.blit(self.small.render(obj, True, CYAN), (100, 492 + OY))
            tw = ch.get("twist")
            if tw:
                sf.blit(self.small.render("TWIST: %s - %s" % (tw["name"], tw["desc"]), True,
                                          PORTAL_COLORS[self.chapter % len(PORTAL_COLORS)]),
                        (100, 520 + OY))
        if math.sin(self.t * 4) > -0.4:
            im = self.small.render("ENTER to continue   /   ESC to skip", True, DGREY)
            sf.blit(im, (W - im.get_width() - 80, 560 + OY))

    def draw_credits(self, sf):
        sf.fill(BG)
        im = self.big.render("ACT ONE COMPLETE", True, CYAN)
        sf.blit(im, (W / 2 - im.get_width() / 2, 180 + OY))
        for i, l in enumerate([
            "Marrow Gate keeps its light.",
            "Three districts north are still dark.",
            "",
            "Played as: " + (self.char["name"] if self.char else "-"),
            "",
            "ARCLIGHT: FRONTLINE - prototype build",
        ]):
            im = self.mid.render(l, True, GREY)
            sf.blit(im, (W / 2 - im.get_width() / 2, 260 + OY + i * 32))


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
async def main():
    pygame.init()
    pygame.display.set_caption("ARCLIGHT: FRONTLINE")
    # SCALED lets the fixed W x H playfield stretch cleanly to fill any
    # window size or the monitor's native resolution in fullscreen.
    screen = pygame.display.set_mode((W, H), pygame.SCALED)
    clock = pygame.time.Clock()
    app = App(screen)
    fullscreen = False
    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
                continue
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_F11:
                fullscreen = not fullscreen
                flags = pygame.SCALED | (pygame.FULLSCREEN if fullscreen else 0)
                screen = pygame.display.set_mode((W, H), flags)
                app.screen = screen
                continue
            app.handle(ev)
        keys = pygame.key.get_pressed()
        mpos = pygame.mouse.get_pos()
        mdown = pygame.mouse.get_pressed()[0]
        app.update(dt, keys, mpos, mdown)
        app.draw()
        pygame.display.flip()
        await asyncio.sleep(0)
    pygame.quit()


def selftest():
    """Headless smoke test: every character through every chapter."""
    import os
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    app = App(screen)
    class FakeKeys(dict):
        def __missing__(self, k):
            return False

    keys = FakeKeys()
    for k in (pygame.K_d, pygame.K_w, pygame.K_j, pygame.K_r):
        keys[k] = True
    for c in CHARACTERS:
        for ci in range(len(CHAPTERS)):
            g = Game(c, ci, app.mid, app.big, app.small)
            casts = 0
            for f in range(420):
                # skills/dash are press-triggered now, so the test has to
                # release the key and press it again to fire them twice.
                held = (f // 7) % 2 == 0
                for k in (pygame.K_q, pygame.K_e, pygame.K_SPACE):
                    keys[k] = held
                before = (g.player.cdq, g.player.cde, g.player.cdd)
                g.update(1 / 60, keys, (random.randint(0, W), random.randint(0, H)), True)
                if any(a > b for a, b in zip((g.player.cdq, g.player.cde, g.player.cdd), before)):
                    casts += 1
                if f % 60 == 0:
                    g.draw(screen)
            assert casts >= 2, "skills never fired for %s" % c["id"]
            print("ok", c["id"], ci, "state=", g.state, "kills=", g.kills, "casts=", casts)

    # --- movement regression: WASD must move you, and must keep working
    #     while skill/dash keys are held down ---
    mk = FakeKeys()
    g = Game(CHARACTERS[0], 0, app.mid, app.big, app.small)
    for label, extra in (("plain", ()), ("holding Q/E/SPACE",
                                         (pygame.K_q, pygame.K_e, pygame.K_SPACE))):
        for code, axis, sign in ((pygame.K_d, "x", 1), (pygame.K_a, "x", -1),
                                 (pygame.K_w, "y", -1), (pygame.K_s, "y", 1)):
            for k in list(mk):
                mk[k] = False
            mk[code] = True
            for k in extra:
                mk[k] = True
            g.enemies.clear()
            g.player.pos = V2(ARENA.center)
            g.player.cdq = g.player.cde = g.player.cdd = 0.0
            # let any cast triggered by the held keys play out first --
            # a skill lunge is allowed to steer you, holding the key is not
            for _ in range(36):
                g.enemies.clear()
                g.update(1 / 60, mk, (ARENA.centerx + 200, ARENA.centery), False)
            g.player.pos = V2(ARENA.center)
            start = V2(g.player.pos)
            for _ in range(40):
                g.enemies.clear()
                g.update(1 / 60, mk, (ARENA.centerx + 200, ARENA.centery), False)
            moved = getattr(g.player.pos - start, axis) * sign
            assert moved > 30, "%s: key %s only moved %.1f" % (label, code, moved)
        print("ok movement", label)
    # --- chapter twists: each one must visibly change the game -------------
    idle = FakeKeys()
    aim = (ARENA.centerx + 200, ARENA.centery)

    def sim(g, secs, clear=False):
        for _ in range(int(secs * 60)):
            if clear:
                g.enemies.clear()
            g.update(1 / 60, idle, aim, False)

    # I  wind: standing still, gusts must carry the player away from the start
    g = Game(CHARACTERS[0], 0, app.mid, app.big, app.small)
    g.player.hp = g.player.maxhp = 1e6
    start, far = V2(g.player.pos), 0.0
    for _ in range(30 * 60):
        g.enemies.clear()
        g.update(1 / 60, idle, aim, False)
        far = max(far, g.player.pos.distance_to(start))
    assert far > 40, "crosswind never moved the player (%.1f)" % far
    print("ok twist wind", round(far))

    # II mortar: shells land, and one landing on the player hurts
    g = Game(CHARACTERS[0], 1, app.mid, app.big, app.small)
    g.player.hp = g.player.maxhp = 1e6
    sim(g, 14, clear=True)
    assert g.tw["det"] >= 2, "no mortar shells detonated"
    g.tw["shells"].append([V2(g.player.pos), 0.05, 1.5, 78])
    hp0 = g.player.hp
    g.player.iframe = 0.0
    sim(g, 0.2, clear=True)
    assert g.player.hp < hp0, "mortar blast did no damage"
    print("ok twist mortar", g.tw["det"])

    # III blackout: a surge stuns an enemy standing near the relay
    g = Game(CHARACTERS[0], 2, app.mid, app.big, app.small)
    foe = Enemy("grunt", V2(g.relay.pos) + V2(100, 0), g.scale)
    g.enemies.append(foe)
    g.tw["surge_t"] = 0.01
    sim(g, 0.1)
    assert g.tw["surges"] == 1 and foe.stun > 1.0, "relay surge did not stun"
    print("ok twist blackout")

    # IV ash ring: it closes in, and standing in the ash burns
    g = Game(CHARACTERS[0], 3, app.mid, app.big, app.small)
    boss = g.enemies[0]
    boss.hp = boss.maxhp * 0.15
    boss.stun = 99.0
    g.spawn_t = 1e9
    g.player.hp = g.player.maxhp = 1e6
    corner = V2(ARENA.left + 20, ARENA.top + 20)
    g.player.pos = V2(corner)
    hp0 = g.player.hp
    for _ in range(5 * 60):
        g.player.pos = V2(corner)
        g.update(1 / 60, idle, aim, False)
    assert g.tw["f"] > 0.3, "ash ring never closed"
    assert g.player.hp < hp0, "standing in the ash did no damage"
    print("ok twist ashring", round(g.tw["f"], 2))

    # --- inventory + potions ------------------------------------------------
    def fresh(ci=0):
        gg = Game(CHARACTERS[0], ci, app.mid, app.big, app.small)
        gg.enemies.clear()
        gg.spawn_t = 1e9
        return gg

    g = fresh()
    g.inv.add("heal")
    assert g.use_item("heal") is False and g.inv.count("heal") == 1      # full HP: not wasted
    g.player.hp = g.player.maxhp * 0.3
    assert g.use_item("heal") is True and g.inv.count("heal") == 0
    assert abs(g.player.hp - g.player.maxhp * 0.7) < 1, "heal should restore 40% max HP"
    assert g.use_item("heal") is False                                   # bag empty
    print("ok potion heal")

    g = fresh()
    base = g.player.move_speed()
    g.inv.add("speed")
    assert g.use_item("speed") and g.player.move_speed() > base * 1.3
    sim(g, ITEMS["speed"]["dur"] + 0.5, clear=True)
    assert abs(g.player.move_speed() - base) < 1e-6, "speed potion never wore off"
    print("ok potion speed")

    g = fresh()
    d0 = g.player.dmg_mult(100)
    g.inv.add("strength")
    g.use_item("strength")
    assert abs(g.player.dmg_mult(100) / d0 - 1.4) < 1e-6
    print("ok potion strength")

    g = fresh()
    hp0 = g.player.hp
    g.player.hurt(20, g)
    plain = hp0 - g.player.hp
    g = fresh()
    g.inv.add("ward")
    g.use_item("ward")
    hp0 = g.player.hp
    g.player.hurt(20, g)
    assert abs((hp0 - g.player.hp) - plain * 0.5) < 0.6, "ward should halve damage"
    print("ok potion ward")

    g = fresh()
    g.player.cdq = 10.0
    sim(g, 1.0, clear=True)
    plain_cd = g.player.cdq
    g = fresh()
    g.inv.add("focus")
    g.use_item("focus")
    g.player.cdq = 10.0
    sim(g, 1.0, clear=True)
    assert g.player.cdq < plain_cd - 1.0, "focus should speed up cooldowns"
    print("ok potion focus")

    # drops: pity timer guarantees them, bosses never drop, full stacks never drop
    g = fresh()
    for _ in range(40):
        g.maybe_drop(Enemy("grunt", V2(ARENA.center), 1.0))
    assert len(g.pickups) >= 3, "pity timer should force regular drops"
    n0 = len(g.pickups)
    g.maybe_drop(Enemy("warden", V2(ARENA.center), 1.0))
    assert len(g.pickups) == n0
    g = fresh()
    for k in ITEM_ORDER:
        for _ in range(ITEMS[k]["cap"]):
            g.inv.add(k)
    g.drought = 99
    g.maybe_drop(Enemy("brute", V2(ARENA.center), 1.0))
    assert not g.pickups, "a full bag should stop drops"
    print("ok drops")

    # pickups: walk-over collects, a full stack is left alone, old ones expire
    g = fresh()
    g.pickups = [Pickup(g.player.pos, "speed")]
    sim(g, 1.0, clear=True)
    assert g.inv.count("speed") == 1 and not g.pickups
    g = fresh()
    for _ in range(ITEMS["speed"]["cap"]):
        g.inv.add("speed")
    assert g.inv.add("speed") is False
    g.pickups = [Pickup(g.player.pos, "speed")]
    sim(g, 1.0, clear=True)
    assert len(g.pickups) == 1 and g.inv.count("speed") == ITEMS["speed"]["cap"]
    g.pickups[0].age = Pickup.LIFE - 0.05
    sim(g, 0.3, clear=True)
    assert not g.pickups, "pickup never expired"
    print("ok pickups")

    # the bag carries across chapters; a retry rewinds to the chapter start
    app.char = CHARACTERS[0]
    app.chapter = 0
    app.diff_sel = 1
    app.inv = Inventory({"heal": 2})
    g1 = app.make_game()
    assert g1.inv is app.inv
    g1.inv.take("heal")
    g2 = app.make_game(retry=True)
    assert g2.inv.count("heal") == 2, "retry should restore the chapter-start bag"
    g2.inv.add("speed")
    g3 = app.make_game()
    assert g3.inv.count("speed") == 1 and g3.inv.count("heal") == 2
    print("ok bag carry-over")

    # inventory screen: TAB opens (and freezes the game), keys and clicks drink
    app.scene = "play"
    app.paused = False
    app.inv = Inventory()
    app.game = app.make_game()
    app.inv.add("speed")
    app.inv.add("strength")
    app.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
    assert app.inv_open
    t0 = app.game.time
    app.update(1 / 60, idle, aim, False)
    assert app.game.time == t0, "game must freeze while the bag is open"
    app.draw()
    app.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_2))
    assert app.game.player.pot["speed"] > 0 and app.inv.count("speed") == 0
    row = app.inv_rects()[2]
    app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=row.center, button=1))
    assert app.game.player.pot["strength"] > 0, "clicking a row should drink it"
    app.draw()
    app.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert not app.inv_open and not app.paused
    app.inv.add("ward")
    app.handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4))
    assert app.game.player.pot["ward"] > 0, "number keys drink in play"
    app.draw()
    print("ok inventory screen")

    # UI scenes
    for scene in ("title", "select", "story", "credits"):
        app.scene = scene
        app.char = CHARACTERS[0]
        app.game = Game(CHARACTERS[0], 0, app.mid, app.big, app.small)
        app.draw()
        print("ok scene", scene)
    print("SELFTEST PASSED")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        asyncio.run(main())
