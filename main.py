import discord
from discord.ext import commands
import random
import asyncio
from pymongo import MongoClient
import datetime
import requests
from io import BytesIO
from PIL import Image, ImageFont, ImageDraw
import textwrap
import os
import json
import math
import aiohttp
import copy
# MongoDB setup
mongo_uri = os.getenv('MONGODB_URI')
if not mongo_uri:
    print("Warning: MONGODB_URI not found in environment variables")
    print("Using local fallback storage...")
    mongo_client = None
else:
    try:
        mongo_client = MongoClient(mongo_uri)
        # Test the connection
        mongo_client.admin.command('ping')
        print("Successfully connected to MongoDB!")
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        print("Using local fallback storage...")
        mongo_client = None
if mongo_client:
    db = mongo_client["owo_bot"]
    users = db["users"]
    servers = db["servers"]
    inventories = db["inventories"]
    marriages = db["marriages"]
else:
    # Fallback to local storage (in-memory)
    users_data = {}
    inventories_data = {}
    marriages_data = {}

    class FallbackCollection:
        def __init__(self, data_dict):
            self.data = data_dict

        def find_one(self, query):
            if isinstance(query, dict) and "_id" in query:
                return self.data.get(query["_id"])
            return None

        def insert_one(self, doc):
            if "_id" in doc:
                self.data[doc["_id"]] = doc

        def update_one(self, query, update):
            if isinstance(query, dict) and "_id" in query:
                user_id = query["_id"]
                if user_id in self.data and "$set" in update:
                    self.data[user_id].update(update["$set"])

        def find(self, query=None):
            return FallbackCursor(list(self.data.values()))

        def delete_one(self, query):
            if isinstance(query, dict) and "_id" in query:
                self.data.pop(query["_id"], None)

    class FallbackCursor:
        def __init__(self, data):
            self.data = data

        def sort(self, field, direction):
            if direction == -1:
                self.data = sorted(self.data, key=lambda x: x.get(field, 0), reverse=True)
            else:
                self.data = sorted(self.data, key=lambda x: x.get(field, 0))
            return self

        def limit(self, num):
            self.data = self.data[:num]
            return self

        def __iter__(self):
            return iter(self.data)

    users = FallbackCollection(users_data)
    inventories = FallbackCollection(inventories_data)
    marriages = FallbackCollection(marriages_data)
    servers = FallbackCollection({})

# Bot setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='owo ', intents=intents)
bot.remove_command('help')

# Owner ID and special AI response ID
OWNER_ID = 976543554295967765
SPECIAL_AI_ID = 1005469547479965726  # Gets polite responses but not owner commands

# Economy variables with level scaling
STARTING_BALANCE = 100
BASE_DAILY_AMOUNT = 500
BASE_WORK_AMOUNT = (100, 500)
BASE_CRIME_AMOUNT = (200, 800)
CRIME_SUCCESS_RATE = 0.7
CRIME_FAIL_PENALTY = 300

# Enhanced leveling system with massive bonuses
def calculate_level_bonus(level):
    """Calculate bonus based on level - heavily enhanced"""
    if level >= 100:
        return int(level * 500)  # 50,000+ for level 100+
    elif level >= 75:
        return int(level * 300)  # 22,500+ for level 75+
    elif level >= 50:
        return int(level * 200)  # 10,000+ for level 50+
    elif level >= 25:
        return int(level * 100)  # 2,500+ for level 25+
    else:
        return int(level * 50)   # Base scaling

def calculate_daily_bonus(level):
    """Calculate daily reward bonus based on level"""
    return BASE_DAILY_AMOUNT + (level * 100) + calculate_level_bonus(level)

def calculate_work_bonus(level):
    """Calculate work reward bonus based on level"""
    base_min, base_max = BASE_WORK_AMOUNT
    level_multiplier = 1 + (level * 0.1)
    return (int(base_min * level_multiplier), int(base_max * level_multiplier))

def calculate_crime_bonus(level):
    """Calculate crime reward bonus based on level"""
    base_min, base_max = BASE_CRIME_AMOUNT
    level_multiplier = 1 + (level * 0.15)
    return (int(base_min * level_multiplier), int(base_max * level_multiplier))

def calculate_xp_for_level(level):
    """Calculate XP required for a level"""
    return int(100 * (level ** 1.5))

# Simple bot responses for mentions
def get_simple_bot_response(message, user_id):
    """Simple bot responses for mentions"""
    message_lower = message.lower()

    # Greeting responses
    if any(word in message_lower for word in ["hello", "hi", "hey", "greetings"]):
        responses = [
            "Hello! How can I help you today?",
            "Hi there! What's up?",
            "Hey! Nice to see you!",
            "Greetings! What can I do for you?"
        ]
        return random.choice(responses)

    # Status responses
    elif any(word in message_lower for word in ["how are you", "how's it going", "what's up"]):
        responses = [
            "I'm doing great! Thanks for asking! 😊",
            "All good here! How about you?",
            "I'm running smoothly! What brings you here?"
        ]
        return random.choice(responses)

    # Thank you responses
    elif any(word in message_lower for word in ["thank", "thanks", "appreciate"]):
        responses = [
            "You're welcome! Happy to help! 😊",
            "No problem at all!",
            "Glad I could help!"
        ]
        return random.choice(responses)

    # Goodbye responses
    elif any(word in message_lower for word in ["bye", "goodbye", "see you", "farewell"]):
        responses = [
            "Goodbye! Have a great day! 👋",
            "See you later! 😊",
            "Take care! Come back anytime!"
        ]
        return random.choice(responses)

    # Help/capabilities
    elif any(word in message_lower for word in ["help", "what can you do", "commands"]):
        return "I'm a Discord bot with economy, games, and social features! Use `owo help` to see all my commands! 🎮"

    # Math questions
    elif any(word in message_lower for word in ["math", "calculate"]):
        return "I can do simple math! Try `owo math 2+2` for calculations! 🧮"

    # Fun responses
    elif any(word in message_lower for word in ["joke", "funny"]):
        jokes = [
            "Why don't scientists trust atoms? Because they make up everything! 😄",
            "I told my wife she was drawing her eyebrows too high. She looked surprised! 😂",
            "Why don't eggs tell jokes? They'd crack each other up! 🥚"
        ]
        return random.choice(jokes)

    # Default responses
    else:
        responses = [
            "That's interesting! Tell me more! 🤔",
            "I see! What would you like to know? 😊",
            "Cool! How can I help you today? ✨",
            "Nice! What brings you here? 🎮",
            "Awesome! What can I do for you? 🌟"
        ]
        return random.choice(responses)

# Tenor API Integration for Anime GIFs
TENOR_API_KEY = os.getenv('TENOR_API_KEY')

# Cache for GIF URLs to reduce API calls
gif_cache = {}
cache_expiry = {}

# Anime action search terms for Tenor API
ANIME_SEARCH_TERMS = {
    "hug": "anime hug",
    "kiss": "anime kiss",
    "slap": "anime slap",
    "punch": "anime punch",
    "cuddle": "anime cuddle",
    "pat": "anime pat headpat",
    "poke": "anime poke",
    "bite": "anime bite",
    "tickle": "anime tickle",
    "blush": "anime blush",
    "cry": "anime cry tears",
    "dance": "anime dance",
    "happy": "anime happy excited",
    "pout": "anime pout angry",
    "anime nsfw": "anime ecchi romantic",
    "anime kick": "anime kick martial arts"
}

async def get_anime_gif(action):
    """Get a random anime GIF from Tenor API"""
    if not TENOR_API_KEY:
        print("Warning: TENOR_API_KEY not found, using fallback GIF")
        # Return action-specific fallback GIFs
        fallback_gifs = {
            "hug": "https://media.tenor.com/K9lT_pKV0vMAAAAC/anime-hug.gif",
            "kiss": "https://media.tenor.com/LCYQBk_jcpoAAAAC/anime-kiss.gif",
            "slap": "https://media.tenor.com/6fJoVJaTgbAAAAAC/anime-slap.gif",
            "punch": "https://media.tenor.com/XN_5Q3Wok-YAAAAC/anime-punch.gif",
            "cuddle": "https://media.tenor.com/h_Wng1bWH40AAAAC/anime-cuddle.gif",
            "pat": "https://media.tenor.com/b60jfhRgcEcAAAAC/anime-pat.gif",
            "poke": "https://media.tenor.com/j1lMpnkGRwUAAAAC/anime-poke.gif",
            "bite": "https://media.tenor.com/kH1sr4JK8gsAAAAC/anime-bite.gif",
            "tickle": "https://media.tenor.com/lPCR_wQNF8QAAAAC/anime-tickle.gif",
            "blush": "https://media.tenor.com/lW-dHTqkxWAAAAAC/anime-blush.gif",
            "cry": "https://media.tenor.com/H_lKULYKuQkAAAAC/anime-cry.gif",
            "dance": "https://media.tenor.com/yMBovJrYSf8AAAAC/anime-dance.gif",
            "happy": "https://media.tenor.com/k6qgJeJTOgsAAAAC/anime-happy.gif",
            "pout": "https://media.tenor.com/T8LWyxT8A0cAAAAC/anime-pout.gif",
            "anime nsfw": "https://media.tenor.com/eKHuKbDxnXMAAAAC/anime-romantic.gif",
            "anime kick": "https://media.tenor.com/XN_5Q3Wok-YAAAAC/anime-martial-arts.gif"
        }
        return fallback_gifs.get(action, "https://media.tenor.com/eKHuKbDxnXMAAAAC/anime-happy.gif")

    # Check if we have cached GIFs for this action
    now = datetime.datetime.now()
    cache_key = action

    # If cache exists and is not expired (cache for 30 minutes)
    if (cache_key in gif_cache and
        cache_key in cache_expiry and
        now < cache_expiry[cache_key]):
        gifs = gif_cache[cache_key]
        if gifs:
            return random.choice(gifs)

    # Get search term for the action
    search_term = ANIME_SEARCH_TERMS.get(action, f"anime {action}")

    try:
        # Make API request to Tenor
        async with aiohttp.ClientSession() as session:
            url = f"https://tenor.googleapis.com/v2/search"
            params = {
                "q": search_term,
                "key": TENOR_API_KEY,
                "limit": 20,  # Get 20 GIFs for variety
                "media_filter": "gif",
                "contentfilter": "medium"
            }

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])

                    if results:
                        # Extract GIF URLs
                        gif_urls = []
                        for result in results:
                            media_formats = result.get("media_formats", {})
                            gif_url = media_formats.get("gif", {}).get("url")
                            if gif_url:
                                gif_urls.append(gif_url)

                        if gif_urls:
                            # Cache the GIFs for 30 minutes
                            gif_cache[cache_key] = gif_urls
                            cache_expiry[cache_key] = now + datetime.timedelta(minutes=30)

                            return random.choice(gif_urls)

                print(f"Failed to fetch GIF from Tenor API for {action}, status: {response.status}")

    except Exception as e:
        print(f"Error fetching GIF from Tenor API: {e}")

    # Fallback GIF if API fails
    fallback_gifs = {
        "hug": "https://media.tenor.com/K9lT_pKV0vMAAAAC/anime-hug.gif",
        "kiss": "https://media.tenor.com/LCYQBk_jcpoAAAAC/anime-kiss.gif",
        "slap": "https://media.tenor.com/6fJoVJaTgbAAAAAC/anime-slap.gif",
        "punch": "https://media.tenor.com/XN_5Q3Wok-YAAAAC/anime-punch.gif",
        "cuddle": "https://media.tenor.com/h_Wng1bWH40AAAAC/anime-cuddle.gif",
        "pat": "https://media.tenor.com/b60jfhRgcEcAAAAC/anime-pat.gif",
        "poke": "https://media.tenor.com/j1lMpnkGRwUAAAAC/anime-poke.gif",
        "bite": "https://media.tenor.com/kH1sr4JK8gsAAAAC/anime-bite.gif",
        "tickle": "https://media.tenor.com/lPCR_wQNF8QAAAAC/anime-tickle.gif",
        "blush": "https://media.tenor.com/lW-dHTqkxWAAAAAC/anime-blush.gif",
        "cry": "https://media.tenor.com/H_lKULYKuQkAAAAC/anime-cry.gif",
        "dance": "https://media.tenor.com/yMBovJrYSf8AAAAC/anime-dance.gif",
        "happy": "https://media.tenor.com/k6qgJeJTOgsAAAAC/anime-happy.gif",
        "pout": "https://media.tenor.com/T8LWyxT8A0cAAAAC/anime-pout.gif"
    }

    return fallback_gifs.get(action, "https://media.tenor.com/eKHuKbDxnXMAAAAC/anime-happy.gif")

HUNT_ITEMS = {
    # Common Animals (40% total)
    "rabbit": {"emoji": "🐇", "value": 50, "rarity": 0.15, "type": "common"},
    "squirrel": {"emoji": "🐿️", "value": 30, "rarity": 0.12, "type": "common"},
    "duck": {"emoji": "🦆", "value": 45, "rarity": 0.10, "type": "common"},
    "pigeon": {"emoji": "🕊️", "value": 25, "rarity": 0.08, "type": "common"},

    # Uncommon Animals (35% total)
    "deer": {"emoji": "🦌", "value": 150, "rarity": 0.12, "type": "uncommon"},
    "fox": {"emoji": "🦊", "value": 120, "rarity": 0.10, "type": "uncommon"},
    "boar": {"emoji": "🐗", "value": 200, "rarity": 0.08, "type": "uncommon"},
    "turkey": {"emoji": "🦃", "value": 100, "rarity": 0.05, "type": "uncommon"},

    # Rare Animals (20% total)
    "elk": {"emoji": "🫎", "value": 400, "rarity": 0.08, "type": "rare"},
    "wolf": {"emoji": "🐺", "value": 500, "rarity": 0.06, "type": "rare"},
    "bear": {"emoji": "🐻", "value": 800, "rarity": 0.04, "type": "rare"},
    "eagle": {"emoji": "🦅", "value": 350, "rarity": 0.02, "type": "rare"},

    # Epic Animals (4% total)
    "tiger": {"emoji": "🐅", "value": 1500, "rarity": 0.015, "type": "epic"},
    "lion": {"emoji": "🦁", "value": 1800, "rarity": 0.012, "type": "epic"},
    "leopard": {"emoji": "🐆", "value": 1200, "rarity": 0.008, "type": "epic"},
    "rhino": {"emoji": "🦏", "value": 2000, "rarity": 0.005, "type": "epic"},

    # Legendary Animals (0.8% total)
    "mammoth": {"emoji": "🦣", "value": 5000, "rarity": 0.003, "type": "legendary"},
    "white tiger": {"emoji": "🐅", "value": 8000, "rarity": 0.002, "type": "legendary"},
    "golden eagle": {"emoji": "🦅", "value": 6000, "rarity": 0.002, "type": "legendary"},
    "albino deer": {"emoji": "🦌", "value": 4000, "rarity": 0.001, "type": "legendary"},

    # Mythical Animals (0.2% total)
    "dragon": {"emoji": "🐉", "value": 25000, "rarity": 0.0008, "type": "mythical"},
    "unicorn": {"emoji": "🦄", "value": 20000, "rarity": 0.0006, "type": "mythical"},
    "phoenix": {"emoji": "🔥", "value": 30000, "rarity": 0.0004, "type": "mythical"},
    "griffin": {"emoji": "🦅", "value": 35000, "rarity": 0.0002, "type": "mythical"}
}

FISH_ITEMS = {
    "old boot": {"emoji": "👢", "value": 5, "rarity": 0.3},
    "tin can": {"emoji": "🥫", "value": 10, "rarity": 0.25},
    "fish": {"emoji": "🐟", "value": 40, "rarity": 0.3},
    "goldfish": {"emoji": "🐠", "value": 300, "rarity": 0.1},
    "shark": {"emoji": "🦈", "value": 1000, "rarity": 0.04},
    "whale": {"emoji": "🐋", "value": 2000, "rarity": 0.01},
    "kraken": {"emoji": "🐙", "value": 5000, "rarity": 0.001}
}

# Custom ranks system (owner-assigned)
CUSTOM_RANKS = {
    "Peasant": {"color": 0x8B4513, "emoji": "👨‍🌾", "perks": "Access to basic commands"},
    "Citizen": {"color": 0x696969, "emoji": "👨‍💼", "perks": "+5% daily bonus"},
    "Noble": {"color": 0x4169E1, "emoji": "👑", "perks": "+10% daily bonus, Reduced work cooldown (30min)"},
    "Knight": {"color": 0x32CD32, "emoji": "⚔️", "perks": "+15% all earnings, Hunt cooldown reduced"},
    "Lord": {"color": 0x800080, "emoji": "🏰", "perks": "+20% all earnings, Rob protection 1/day"},
    "Duke": {"color": 0xFF1493, "emoji": "💎", "perks": "+25% all earnings, 2x rare hunt chance"},
    "King": {"color": 0xFFD700, "emoji": "👑", "perks": "+30% all earnings, Crime always succeeds"},
    "Emperor": {"color": 0xFF4500, "emoji": "🔥", "perks": "+50% all earnings, All perks unlocked, VIP status"}
}

# Wealth-based ranks (automatic based on balance)
WEALTH_RANKS = {
    "Beggar": {"threshold": 0, "emoji": "🪙", "color": 0x808080, "perks": "Starting rank"},
    "Worker": {"threshold": 1000, "emoji": "👷", "color": 0x8B7355, "perks": "+2% work earnings"},
    "Trader": {"threshold": 10000, "emoji": "💼", "color": 0x4682B4, "perks": "+5% work earnings, +3% shop discounts"},
    "Merchant": {"threshold": 50000, "emoji": "🏪", "color": 0x32CD32, "perks": "+8% work earnings, +5% shop discounts"},
    "Entrepreneur": {"threshold": 100000, "emoji": "💰", "color": 0x9370DB, "perks": "+10% work earnings, +8% shop discounts, Free daily item"},
    "Tycoon": {"threshold": 500000, "emoji": "💎", "color": 0xFF1493, "perks": "+15% all earnings, +10% shop discounts, 2 free daily items"},
    "Mogul": {"threshold": 1000000, "emoji": "🏆", "color": 0xFFD700, "perks": "+20% all earnings, +15% shop discounts, VIP hunting"},
    "Billionaire": {"threshold": 10000000, "emoji": "👑", "color": 0xFF4500, "perks": "+30% all earnings, +20% shop discounts, Exclusive perks"}
}

# Level-based ranks (automatic based on level)
LEVEL_RANKS = {
    "Newbie": {"threshold": 1, "emoji": "🌱", "perks": "Learning the ropes"},
    "Intermediate": {"threshold": 10, "emoji": "📚", "perks": "+10% XP gain"},
    "Advanced": {"threshold": 25, "emoji": "⚡", "perks": "+20% XP gain, Unlock advanced commands"},
    "Expert": {"threshold": 50, "emoji": "🎯", "perks": "+30% XP gain, Better hunt drops"},
    "Master": {"threshold": 75, "emoji": "🏅", "perks": "+40% XP gain, Elite hunter status"},
    "Legendary": {"threshold": 100, "emoji": "🌟", "perks": "+50% XP gain, Maximum hunt potential"}
}

# Utility functions
async def get_user_data(user_id):
    user = users.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id,
            "balance": STARTING_BALANCE,
            "daily_streak": 0,
            "last_daily": None,
            "last_work": None,
            "last_crime": None,
            "last_hunt": None,
            "last_fish": None,
            "last_beg": None,
            "inventory": [],
            "pets": [],
            "married_to": None,
            "bio": "No bio set",
            "xp": 0,
            "level": 1,
            "rank": "Peasant",
            "title": "Newbie",
            "custom_rank": None
        }
        users.insert_one(user)
    return user

async def update_user_data(user_id, update):
    users.update_one({"_id": user_id}, {"$set": update})

def get_wealth_rank(balance):
    """Calculate wealth rank based on balance"""
    wealth_rank = "Beggar"
    for rank_name, rank_data in sorted(WEALTH_RANKS.items(), key=lambda x: x[1]["threshold"], reverse=True):
        if balance >= rank_data["threshold"]:
            wealth_rank = rank_name
            break
    return wealth_rank

async def add_xp(user_id, amount):
    """Add XP to user and check for level up"""
    user = await get_user_data(user_id)
    old_level = user.get("level", 1)
    new_xp = user.get("xp", 0) + amount

    # Calculate new level
    new_level = 1
    while calculate_xp_for_level(new_level) <= new_xp:
        new_level += 1
    new_level -= 1  # Go back one since we went over

    # Update rank based on level
    if new_level >= 100:
        rank = "Legendary"
    elif new_level >= 75:
        rank = "Master"
    elif new_level >= 50:
        rank = "Expert"
    elif new_level >= 25:
        rank = "Advanced"
    elif new_level >= 10:
        rank = "Intermediate"
    else:
        rank = "Newbie"

    await update_user_data(user_id, {"xp": new_xp, "level": new_level, "rank": rank})

    # Send level up message if user leveled up
    if new_level > old_level:
        try:
            user_obj = bot.get_user(user_id)
            if user_obj:
                # Find a channel to send the level up message
                # This will need to be called from a context where we have access to a channel
                pass
        except:
            pass

    return new_level > old_level, new_level

async def add_item(user_id, item_name, amount=1):
    inventory = inventories.find_one({"_id": user_id})
    if not inventory:
        inventory = {"_id": user_id, "items": {}}
        inventories.insert_one(inventory)

    items = inventory.get("items", {})
    items[item_name] = items.get(item_name, 0) + amount
    inventories.update_one({"_id": user_id}, {"$set": {"items": items}})

async def remove_item(user_id, item_name, amount=1):
    inventory = inventories.find_one({"_id": user_id})
    if inventory:
        items = inventory.get("items", {})
        if item_name in items and items[item_name] >= amount:
            items[item_name] -= amount
            if items[item_name] <= 0:
                del items[item_name]
            inventories.update_one({"_id": user_id}, {"$set": {"items": items}})
            return True
    return False

def create_aesthetic_embed(title, description="", color=discord.Color.purple(), thumbnail_url=None):
    """Create beautiful aesthetic embeds with advanced styling"""
    # Add decorative borders and styling
    styled_title = f"╭─── ✨ {title} ✨ ───╮"
    if description:
        styled_description = f"│ {description} │"
    else:
        styled_description = ""

    embed = discord.Embed(
        title=styled_title,
        description=styled_description,
        color=color,
        timestamp=datetime.datetime.now()
    )

    # Add aesthetic elements
    embed.set_footer(
        text="╰─── 🌟 Advanced OwO Bot • Superior Experience ───╯",
        icon_url="https://cdn.discordapp.com/emojis/878328329692819466.gif"
    )

    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    # Add subtle gradient effect with color variations
    if color == discord.Color.gold():
        embed.add_field(name="", value="⭐ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ⭐", inline=False)
    elif color == discord.Color.green():
        embed.add_field(name="", value="💚 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 💚", inline=False)
    elif color == discord.Color.red():
        embed.add_field(name="", value="❤️ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ❤️", inline=False)

    return embed

# Owner Commands
@bot.command()
async def take(ctx, member: discord.Member, amount: int):
    """Owner only: Take money from any user (money gets destroyed)"""
    if ctx.author.id != OWNER_ID:
        embed = create_aesthetic_embed("❌ Access Denied",
                                     "║ This command is for the bot owner only! ║",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    user = await get_user_data(member.id)

    if user["balance"] < amount:
        embed = create_aesthetic_embed("💸 Insufficient Funds",
                                     f"║ {member.display_name} only has {user['balance']:,} 💵 ║",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    new_balance = user["balance"] - amount
    await update_user_data(member.id, {"balance": new_balance})

    description = f"""
┌─────────────────────────────────┐
│  💀 **Money Destruction** 💀  │
├─────────────────────────────────┤
│ **Target:** {member.display_name}
│ **Amount Taken:** {amount:,} 💵
│ **New Balance:** {new_balance:,} 💵
│ **Status:** Money destroyed
└─────────────────────────────────┘
"""

    embed = create_aesthetic_embed("Royal Confiscation", description, discord.Color.dark_red(), member.display_avatar.url)
    embed.add_field(name="💥 Action Status", value="✅ **EXECUTED**", inline=True)
    embed.add_field(name="👑 Authority", value="**OWNER PRIVILEGE**", inline=True)
    embed.add_field(name="⏰ Timestamp", value=f"<t:{int(datetime.datetime.now().timestamp())}:F>", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def banuser(ctx, member: discord.Member):
    """Owner only: Ban a user from using the bot"""
    if ctx.author.id != OWNER_ID:
        embed = create_aesthetic_embed("❌ Access Denied",
                                     "║ This command is for the bot owner only! ║",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    await update_user_data(member.id, {"bot_banned": True})

    embed = create_aesthetic_embed("🔨 User Banned",
                                 f"║ **{member.display_name}** has been banned from using the bot! ║",
                                 discord.Color.dark_red())
    embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def unbanuser(ctx, member: discord.Member):
    """Owner only: Unban a user from using the bot"""
    if ctx.author.id != OWNER_ID:
        embed = create_aesthetic_embed("❌ Access Denied",
                                     "║ This command is for the bot owner only! ║",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    await update_user_data(member.id, {"bot_banned": False})

    embed = create_aesthetic_embed("✅ User Unbanned",
                                 f"║ **{member.display_name}** can now use the bot again! ║",
                                 discord.Color.green())
    embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def givemoney(ctx, member: discord.Member = None, amount: int = None):
    """Owner only: Give unlimited money to anyone"""
    if ctx.author.id != OWNER_ID:
        embed = create_aesthetic_embed("❌ Access Denied",
                                     "║ This command is for the bot owner only! ║",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    if member is None:
        member = ctx.author
    if amount is None:
        amount = 1000000

    user = await get_user_data(member.id)
    new_balance = user["balance"] + amount
    await update_user_data(member.id, {"balance": new_balance})

    description = f"""
┌─────────────────────────────────┐
│  💰 **Money Transfer Complete** 💰  │
├─────────────────────────────────┤
│ **Recipient:** {member.display_name}
│ **Amount Given:** {amount:,} 💵
│ **New Balance:** {new_balance:,} 💵
└─────────────────────────────────┘
"""

    embed = create_aesthetic_embed("Royal Treasury", description, discord.Color.gold(), member.display_avatar.url)
    embed.add_field(name="💎 Transaction Status", value="✅ **COMPLETED**", inline=True)
    embed.add_field(name="👑 Authority", value="**OWNER PRIVILEGE**", inline=True)
    embed.add_field(name="⏰ Timestamp", value=f"<t:{int(datetime.datetime.now().timestamp())}:F>", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def giverank(ctx, member: discord.Member, *, rank_name):
    """Owner only: Give custom ranks to users"""
    if ctx.author.id != OWNER_ID:
        embed = create_aesthetic_embed("❌ Access Denied",
                                     "This command is for the bot owner only!",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    rank_name = rank_name.title()
    if rank_name not in CUSTOM_RANKS:
        available_ranks = ", ".join(CUSTOM_RANKS.keys())
        embed = create_aesthetic_embed("❌ Invalid Rank",
                                     f"Available ranks: {available_ranks}",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    await update_user_data(member.id, {"custom_rank": rank_name})

    rank_info = CUSTOM_RANKS[rank_name]
    embed = create_aesthetic_embed("👑 Rank Bestowed",
                                 f"**{member.display_name}** has been granted the rank of **{rank_info['emoji']} {rank_name}**!",
                                 discord.Color(rank_info["color"]))
    embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def givelevel(ctx, member: discord.Member, level: int):
    """Owner only: Set any user's level"""
    if ctx.author.id != OWNER_ID:
        embed = create_aesthetic_embed("❌ Access Denied",
                                     "This command is for the bot owner only!",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    if level < 1 or level > 999:
        embed = create_aesthetic_embed("❌ Invalid Level",
                                     "Level must be between 1 and 999!",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    # Calculate XP for the given level
    required_xp = sum(calculate_xp_for_level(i) for i in range(1, level + 1))

    # Update rank based on level
    if level >= 100:
        rank = "Legendary"
    elif level >= 75:
        rank = "Master"
    elif level >= 50:
        rank = "Expert"
    elif level >= 25:
        rank = "Advanced"
    elif level >= 10:
        rank = "Intermediate"
    else:
        rank = "Newbie"

    await update_user_data(member.id, {
        "level": level,
        "xp": required_xp,
        "rank": rank
    })

    description = f"""
┌─────────────────────────────────┐
│  ⚡ **Level Assignment** ⚡  │
├─────────────────────────────────┤
│ **Target:** {member.display_name}
│ **New Level:** {level} ⭐
│ **New Rank:** {rank}
│ **Total XP:** {required_xp:,}
└─────────────────────────────────┘
"""

    embed = create_aesthetic_embed("Level Override", description, discord.Color.purple(), member.display_avatar.url)
    embed.add_field(name="⚡ Power Level", value=f"**{level}** ⭐", inline=True)
    embed.add_field(name="👑 Authority", value="**OWNER PRIVILEGE**", inline=True)
    embed.add_field(name="⏰ Timestamp", value=f"<t:{int(datetime.datetime.now().timestamp())}:F>", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def giveanimals(ctx, member: discord.Member, animal_name: str, quantity: int = 1):
    """Owner only: Give any animal to a user"""
    if ctx.author.id != OWNER_ID:
        embed = create_aesthetic_embed("❌ Access Denied",
                                     "This command is for the bot owner only!",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    if quantity <= 0:
        embed = create_aesthetic_embed("❌ Invalid Quantity",
                                     "Quantity must be positive!",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    # Check if animal exists in hunt items
    animal_lower = animal_name.lower()
    found_animal = None
    animal_data = None

    # Search for the animal in hunt items
    for item_name, item_info in HUNT_ITEMS.items():
        if animal_lower in item_name.lower() or item_name.lower() == animal_lower:
            found_animal = item_name
            animal_data = item_info
            break

    # If not found in hunt items, check fish items
    if not found_animal:
        for item_name, item_info in FISH_ITEMS.items():
            if animal_lower in item_name.lower() or item_name.lower() == animal_lower:
                found_animal = item_name
                animal_data = item_info
                break

    if not found_animal:
        # List available animals
        hunt_animals = list(HUNT_ITEMS.keys())[:10]
        fish_animals = list(FISH_ITEMS.keys())[:5]

        available_list = "**Hunt Animals:** " + ", ".join(hunt_animals)
        if len(HUNT_ITEMS) > 10:
            available_list += f" and {len(HUNT_ITEMS) - 10} more"
        available_list += f"\n**Fish:** " + ", ".join(fish_animals)

        embed = create_aesthetic_embed("❌ Animal Not Found",
                                     f"║ Animal '{animal_name}' not found! ║\n\n{available_list}",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    # Give the animal to the user
    for _ in range(quantity):
        await add_item(member.id, found_animal)

    # Calculate total value
    total_value = animal_data["value"] * quantity

    # Get rarity info for display
    rarity_info = ""
    if found_animal in HUNT_ITEMS:
        rarity = HUNT_ITEMS[found_animal].get("type", "common")
        rarity_emojis = {
            "mythical": "🔴",
            "legendary": "🟡",
            "epic": "🟣",
            "rare": "🔵",
            "uncommon": "🟢",
            "common": "⚪"
        }
        rarity_info = f"║ **Rarity:** {rarity_emojis.get(rarity, '⚪')} **{rarity.title()}**\n"

    description = f"""
╔════════════════════════════════════╗
║        🎁 **ANIMAL GIFT** 🎁        ║
╠════════════════════════════════════╣
║ **Recipient:** {member.display_name}
║ **Animal:** {animal_data['emoji']} **{found_animal.title()}**
║ **Quantity:** {quantity}
{rarity_info}║ **Total Value:** {total_value:,} 💵
║ **Gift Status:** Successfully Delivered
╚════════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Royal Gift", description, discord.Color.gold(), member.display_avatar.url)
    embed.add_field(name="🎁 Gift Type", value="**PREMIUM ANIMAL**", inline=True)
    embed.add_field(name="👑 Authority", value="**OWNER PRIVILEGE**", inline=True)
    embed.add_field(name="📦 Delivery", value="**INSTANT** ⚡", inline=True)
    embed.add_field(name="⏰ Timestamp", value=f"<t:{int(datetime.datetime.now().timestamp())}:F>", inline=False)

    await ctx.send(embed=embed)



# Simple Mention Handler
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Check if user is banned from using the bot
    if not message.author.bot:
        user_data = await get_user_data(message.author.id)
        if user_data.get("bot_banned", False) and message.author.id != OWNER_ID:
            return  # Silently ignore banned users

    if bot.user.mentioned_in(message) and not message.mention_everyone:
        print(f"Bot mentioned by {message.author.display_name} ({message.author.id})")

        # Clean message content (remove mention and clean up)
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()

        # Remove common bot prefixes if present
        prefixes_to_remove = ['owo ', 'OwO ', 'OWO ', '!', '?', '.']
        for prefix in prefixes_to_remove:
            if clean_content.startswith(prefix):
                clean_content = clean_content[len(prefix):].strip()
                break

        print(f"Cleaned content: '{clean_content}'")

        # Show typing indicator for better UX
        async with message.channel.typing():
            if not clean_content:  # Handle empty mentions
                if message.author.id == OWNER_ID:
                    response = "Hello there, Boss! I'm your OwO Bot. Use `owo help` to see all my commands! 👑"
                else:
                    response = "Hey! I'm OwO Bot with economy, games, and social features! Use `owo help` to see all my commands! 👋"
            else:
                # Generate simple bot response
                response = get_simple_bot_response(clean_content, message.author.id)

        try:
            await message.reply(response)
            print(f"Response sent successfully to {message.author.display_name}")
        except Exception as e:
            print(f"Error sending response: {e}")
            try:
                await message.reply("I encountered an error sending my response. Please try again!")
            except:
                pass
        
        # Don't process commands after responding to a mention
        return

    await bot.process_commands(message)

# Enhanced Economy commands
@bot.command(aliases=['bal', 'money', 'cash'])
async def balance(ctx, member: discord.Member = None):
    """Check your or someone else's balance with advanced display"""
    member = member or ctx.author
    user = await get_user_data(member.id)

    # Determine wealth status
    balance = user['balance']
    if balance >= 10000000:
        wealth_status = "🏆 **BILLIONAIRE**"
        status_color = discord.Color.from_rgb(255, 215, 0)  # Gold
    elif balance >= 1000000:
        wealth_status = "💎 **MILLIONAIRE**"
        status_color = discord.Color.from_rgb(148, 0, 211)  # Purple
    elif balance >= 100000:
        wealth_status = "💰 **WEALTHY**"
        status_color = discord.Color.from_rgb(50, 205, 50)  # Green
    elif balance >= 10000:
        wealth_status = "💵 **COMFORTABLE**"
        status_color = discord.Color.from_rgb(30, 144, 255)  # Blue
    else:
        wealth_status = "📊 **GROWING**"
        status_color = discord.Color.from_rgb(255, 165, 0)  # Orange

    # Custom rank display
    custom_rank = user.get("custom_rank")
    rank_display = ""
    if custom_rank and custom_rank in CUSTOM_RANKS:
        rank_info = CUSTOM_RANKS[custom_rank]
        rank_display = f"{rank_info['emoji']} **{custom_rank}**"

    # Create advanced description
    description = f"""
╔══════════════════════════════════╗
║  **{member.display_name}'s Financial Status**  ║
╠══════════════════════════════════╣
║ 💰 **Balance:** {balance:,} 💵
║ 📊 **Level:** {user.get('level', 1)} ⭐
║ 🏆 **Rank:** {user.get('rank', 'Newbie')}
║ 💎 **Status:** {wealth_status}
{f'║ 👑 **Title:** {rank_display}' if rank_display else ''}
╚══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Financial Portfolio", description, status_color, member.display_avatar.url)

    # Add progress bar for level
    current_xp = user.get('xp', 0)
    current_level = user.get('level', 1)
    xp_needed = calculate_xp_for_level(current_level + 1)
    xp_progress = min(current_xp / xp_needed, 1.0)
    progress_bar = "█" * int(xp_progress * 20) + "░" * (20 - int(xp_progress * 20))

    embed.add_field(name="📈 Level Progress", value=f"`{progress_bar}` {int(xp_progress * 100)}%", inline=False)
    embed.add_field(name="🔥 Daily Streak", value=f"**{user['daily_streak']}** days", inline=True)
    embed.add_field(name="⚡ Total XP", value=f"**{current_xp:,}** points", inline=True)

    await ctx.send(embed=embed)

@bot.command(aliases=['cowoncy'])
async def daily(ctx):
    """Claim your daily coins"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    if user["last_daily"]:
        last_daily = user["last_daily"].replace(tzinfo=None)
        if (now - last_daily).days < 1:
            next_daily = (last_daily + datetime.timedelta(days=1)).strftime("%H:%M %p")
            embed = create_aesthetic_embed("⏰ Already Claimed",
                                         f"You already claimed your daily today!\n"
                                         f"Come back at **{next_daily}**",
                                         discord.Color.orange())
            return await ctx.send(embed=embed)

    streak = user["daily_streak"] + 1
    level = user.get("level", 1)
    base_amount = calculate_daily_bonus(level) + (streak * 50)

    # Apply shop multipliers
    daily_multiplier = await get_active_multiplier(ctx.author.id, "daily")
    total_amount = int(base_amount * daily_multiplier)

    # Apply XP booster if active
    xp_gain = 50
    if await has_active_effect(ctx.author.id, "xp_booster"):
        xp_gain *= 2

    leveled_up, new_level = await add_xp(ctx.author.id, xp_gain)

    await update_user_data(ctx.author.id, {
        "balance": user["balance"] + total_amount,
        "daily_streak": streak,
        "last_daily": now
    })

    base_daily = BASE_DAILY_AMOUNT
    level_bonus = calculate_level_bonus(level)
    level_multiplier = level * 100
    streak_bonus = streak * 50

    description = f"💰 **{total_amount:,}** coins claimed!\n"
    description += f"📊 Base Daily: **+{base_daily:,}** 💵\n"
    description += f"⭐ Level {level} Multiplier: **+{level_multiplier:,}** 💵\n"
    description += f"🎯 Level Bonus: **+{level_bonus:,}** 💵\n"
    description += f"🔥 Streak Bonus: **+{streak_bonus:,}** 💵"

    if daily_multiplier > 1.0:
        description += f"\n🛍️ Shop Multiplier: **x{daily_multiplier}** ✨"

    if await has_active_effect(ctx.author.id, "xp_booster"):
        description += f"\n🚀 XP Boost: **+{xp_gain}** XP (Double XP active!)"

    if leveled_up:
        description += f"\n\n🎉 **LEVEL UP!** You're now level **{new_level}**!"

    embed = create_aesthetic_embed("💰 Daily Reward", description, discord.Color.gold())
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)

    # Send level up congratulations
    if leveled_up:
        congrats_embed = create_aesthetic_embed("🎊 Level Up!",
                                               f"║ Congratulations {ctx.author.mention}! ║\n"
                                               f"║ You are now level **{new_level}**! ║",
                                               discord.Color.gold())
        await ctx.send(embed=congrats_embed)

@bot.command()
async def work(ctx):
    """Work to earn money"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    # Check for energy drink effect (reduces cooldown by 50%)
    cooldown_time = 3600  # 1 hour default
    if await has_active_effect(ctx.author.id, "energy_drink"):
        cooldown_time = int(cooldown_time * 0.5)  # 30 minutes with energy drink

    if user["last_work"] and (now - user["last_work"].replace(tzinfo=None)).seconds < cooldown_time:
        remaining = cooldown_time - (now - user["last_work"].replace(tzinfo=None)).seconds
        cooldown_text = "⚡ Energy Drink active!" if cooldown_time < 3600 else "Normal cooldown"

        embed = create_aesthetic_embed("😴 Too Tired",
                                     f"You're too tired to work!\n"
                                     f"Try again in **{remaining//60}** minutes.\n"
                                     f"*{cooldown_text}*",
                                     discord.Color.orange())
        return await ctx.send(embed=embed)

    level = user.get("level", 1)
    work_range = calculate_work_bonus(level)
    base_amount = random.randint(*work_range)
    level_bonus = calculate_level_bonus(level)

    # Apply work multiplier from shop
    work_multiplier = await get_active_multiplier(ctx.author.id, "work")
    total_amount = int((base_amount + level_bonus) * work_multiplier)

    jobs = ["🖥️ Programmer", "⚕️ Doctor", "📚 Teacher", "📺 Streamer",
           "🎨 Artist", "👨‍🍳 Chef", "🔬 Scientist", "⚖️ Lawyer",
           "🔧 Engineer", "🎭 Designer"]
    job = random.choice(jobs)

    # Apply XP booster if active
    xp_gain = 30
    if await has_active_effect(ctx.author.id, "xp_booster"):
        xp_gain *= 2

    leveled_up, new_level = await add_xp(ctx.author.id, xp_gain)

    await update_user_data(ctx.author.id, {
        "balance": user["balance"] + total_amount,
        "last_work": now
    })

    description = f"You worked as a **{job}**\n"
    description += f"💰 Base Pay: **{base_amount:,}** 💵\n"
    description += f"⭐ Level {level} Bonus: **+{level_bonus:,}** 💵\n"

    if work_multiplier > 1.0:
        description += f"🛍️ Shop Multiplier: **x{work_multiplier}** ✨\n"

    description += f"💎 Total Earned: **{total_amount:,}** 💵"

    if await has_active_effect(ctx.author.id, "energy_drink"):
        description += f"\n⚡ Energy Drink: Reduced cooldown!"

    if await has_active_effect(ctx.author.id, "xp_booster"):
        description += f"\n🚀 XP Boost: **+{xp_gain}** XP (Double XP active!)"

    if leveled_up:
        description += f"\n\n🎉 **LEVEL UP!** You're now level **{new_level}**!"

    embed = create_aesthetic_embed("💼 Work Complete", description, discord.Color.blue())
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/878328329692819466.gif")
    await ctx.send(embed=embed)

    # Send level up congratulations
    if leveled_up:
        congrats_embed = create_aesthetic_embed("🎊 Level Up!",
                                               f"║ Congratulations {ctx.author.mention}! ║\n"
                                               f"║ You are now level **{new_level}**! ║",
                                               discord.Color.gold())
        await ctx.send(embed=congrats_embed)

# Enhanced Social commands with anime GIFs and advanced aesthetics
@bot.command()
async def hug(ctx, member: discord.Member):
    """Hug another user with anime GIF"""
    gif_url = await get_anime_gif("hug")

    embed = create_aesthetic_embed("💕 Warm Hug",
                                 f"**{ctx.author.display_name}** gives **{member.display_name}** a warm, loving hug! 🤗",
                                 discord.Color.from_rgb(255, 182, 193))
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def kiss(ctx, member: discord.Member):
    """Kiss another user with anime GIF"""
    gif_url = await get_anime_gif("kiss")

    embed = create_aesthetic_embed("💋 Sweet Kiss",
                                 f"**{ctx.author.display_name}** gives **{member.display_name}** a tender kiss! 😘",
                                 discord.Color.from_rgb(255, 20, 147))
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def slap(ctx, member: discord.Member):
    """Slap another user with anime GIF"""
    gif_url = await get_anime_gif("slap")

    embed = create_aesthetic_embed("👋 Anime Slap",
                                 f"**{ctx.author.display_name}** gives **{member.display_name}** a dramatic anime slap! 💥",
                                 discord.Color.from_rgb(255, 140, 0))
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def punch(ctx, member: discord.Member):
    """Punch another user with anime GIF"""
    gif_url = await get_anime_gif("punch")

    embed = create_aesthetic_embed("👊 Power Punch",
                                 f"**{ctx.author.display_name}** throws an epic punch at **{member.display_name}**! ⚡",
                                 discord.Color.from_rgb(220, 20, 60))
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def cuddle(ctx, member: discord.Member):
    """Cuddle with another user with anime GIF"""
    gif_url = await get_anime_gif("cuddle")

    embed = create_aesthetic_embed("🥰 Sweet Cuddle",
                                 f"**{ctx.author.display_name}** and **{member.display_name}** share a cozy cuddle! 💕",
                                 discord.Color.from_rgb(255, 192, 203))
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def pat(ctx, member: discord.Member):
    """Pat another user with anime GIF"""
    gif_url = await get_anime_gif("pat")

    embed = create_aesthetic_embed("😊 Gentle Pat",
                                 f"**{ctx.author.display_name}** gives **{member.display_name}** gentle head pats! 🌟",
                                 discord.Color.from_rgb(144, 238, 144))
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def poke(ctx, member: discord.Member):
    """Poke another user with anime GIF"""
    gif_url = await get_anime_gif("poke")

    embed = create_aesthetic_embed("👉 Playful Poke",
                                 f"**{ctx.author.display_name}** playfully pokes **{member.display_name}**! 😆",
                                 discord.Color.from_rgb(135, 206, 250))
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def bite(ctx, member: discord.Member):
    """Bite another user with anime GIF"""
    gif_url = await get_anime_gif("bite")

    embed = create_aesthetic_embed("🦷 Cute Bite",
                                 f"**{ctx.author.display_name}** gives **{member.display_name}** an adorable little bite! 😸",
                                 discord.Color.from_rgb(138, 43, 226))
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def tickle(ctx, member: discord.Member):
    """Tickle another user with anime GIF"""
    gif_url = await get_anime_gif("tickle")

    embed = create_aesthetic_embed("😂 Tickle Attack",
                                 f"**{ctx.author.display_name}** tickles **{member.display_name}**! 🤣",
                                 discord.Color.from_rgb(255, 255, 0))
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def fuck(ctx, member: discord.Member):
    """Adult action with another user with anime GIF"""
    gif_url = await get_anime_gif("anime nsfw")

    embed = create_aesthetic_embed("🔞 Adult Action",
                                 f"**{ctx.author.display_name}** and **{member.display_name}** are having an intimate moment! 😳",
                                 discord.Color.from_rgb(255, 69, 0))
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def kick(ctx, member: discord.Member):
    """Kick another user with anime GIF"""
    gif_url = await get_anime_gif("anime kick")

    embed = create_aesthetic_embed("🦵 Martial Arts Kick",
                                 f"**{ctx.author.display_name}** delivers a powerful kick to **{member.display_name}**! ⚡",
                                 discord.Color.from_rgb(255, 140, 0))
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

# Enhanced emote commands with anime GIFs
@bot.command()
async def blush(ctx):
    """Blush with anime GIF"""
    gif_url = await get_anime_gif("blush")

    embed = create_aesthetic_embed("😊 Blush",
                                 f"**{ctx.author.display_name}** is blushing adorably!",
                                 discord.Color.pink())
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def cry(ctx):
    """Cry with anime GIF"""
    gif_url = await get_anime_gif("cry")

    embed = create_aesthetic_embed("😭 Cry",
                                 f"**{ctx.author.display_name}** is crying dramatically!",
                                 discord.Color.blue())
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def dance(ctx):
    """Dance with anime GIF"""
    gif_url = await get_anime_gif("dance")

    embed = create_aesthetic_embed("💃 Dance",
                                 f"**{ctx.author.display_name}** is dancing with style!",
                                 discord.Color.gold())
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def happy(ctx):
    """Be happy with anime GIF"""
    gif_url = await get_anime_gif("happy")

    embed = create_aesthetic_embed("😄 Happy",
                                 f"**{ctx.author.display_name}** is radiating happiness!",
                                 discord.Color.yellow())
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def pout(ctx):
    """Pout with anime GIF"""
    gif_url = await get_anime_gif("pout")

    embed = create_aesthetic_embed("😤 Pout",
                                 f"**{ctx.author.display_name}** is pouting cutely!",
                                 discord.Color.orange())
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

# New commands to exceed 100 total




@bot.command()
async def leaderboard(ctx):
    """View server leaderboard"""
    guild_members = [member.id for member in ctx.guild.members if not member.bot]
    top_users = users.find({"_id": {"$in": guild_members}}).sort("balance", -1).limit(10)

    embed = create_aesthetic_embed("🏆 Server Leaderboard", color=discord.Color.gold())

    ranking = []
    for i, user_data in enumerate(top_users, 1):
        try:
            user = await bot.fetch_user(user_data["_id"])
            balance = user_data.get('balance', 0)
            ranking.append(f"**{i}.** {user.display_name} - **{balance:,}** 💵")
        except:
            continue

    embed.description = "\n".join(ranking) if ranking else "No users found!"
    await ctx.send(embed=embed)

# Additional commands to reach 100+ total commands

@bot.command()
async def weekly(ctx):
    """Claim weekly bonus"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    if user.get("last_weekly") and (now - user["last_weekly"].replace(tzinfo=None)).days < 7:
        embed = create_aesthetic_embed("⏰ Weekly Cooldown", "║ Come back next week for your bonus! ║", discord.Color.orange())
        return await ctx.send(embed=embed)

    amount = 5000 + (user.get("level", 1) * 200)
    new_balance = user["balance"] + amount

    await update_user_data(ctx.author.id, {"balance": new_balance, "last_weekly": now})

    embed = create_aesthetic_embed("🗓️ Weekly Bonus", f"║ Claimed **{amount:,}** 💵 weekly bonus! ║", discord.Color.gold())
    await ctx.send(embed=embed)

@bot.command()
async def monthly(ctx):
    """Claim monthly mega bonus"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    if user.get("last_monthly") and (now - user["last_monthly"].replace(tzinfo=None)).days < 30:
        embed = create_aesthetic_embed("📅 Monthly Cooldown", "║ Come back next month for mega bonus! ║", discord.Color.orange())
        return await ctx.send(embed=embed)

    amount = 50000 + (user.get("level", 1) * 1000)
    new_balance = user["balance"] + amount

    await update_user_data(ctx.author.id, {"balance": new_balance, "last_monthly": now})

    embed = create_aesthetic_embed("📅 Monthly Mega Bonus", f"║ Claimed **{amount:,}** 💵 monthly bonus! ║", discord.Color.gold())
    await ctx.send(embed=embed)

@bot.command()
async def dig(ctx):
    """Dig for treasure"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    if user.get("last_dig") and (now - user["last_dig"].replace(tzinfo=None)).seconds < 120:
        remaining = 120 - (now - user["last_dig"].replace(tzinfo=None)).seconds
        embed = create_aesthetic_embed("⛏️ Tired Arms", f"║ Rest for **{remaining}** seconds before digging again! ║", discord.Color.orange())
        return await ctx.send(embed=embed)

    treasures = [
        {"name": "💎 Diamond", "value": 1000, "rarity": 0.05},
        {"name": "🏆 Ancient Artifact", "value": 800, "rarity": 0.08},
        {"name": "💰 Gold Coins", "value": 500, "rarity": 0.15},
        {"name": "🪙 Silver Coins", "value": 200, "rarity": 0.25},
        {"name": "🗿 Old Relic", "value": 100, "rarity": 0.30},
        {"name": "🪨 Rock", "value": 10, "rarity": 0.17}
    ]

    # Random treasure based on rarity
    rand = random.random()
    cumulative = 0
    found_treasure = None

    for treasure in treasures:
        cumulative += treasure["rarity"]
        if rand <= cumulative:
            found_treasure = treasure
            break

    if not found_treasure:
        found_treasure = treasures[-1]  # Default to rock

    new_balance = user["balance"] + found_treasure["value"]
    await update_user_data(ctx.author.id, {"balance": new_balance, "last_dig": now})

    embed = create_aesthetic_embed("⛏️ Treasure Hunt", f"║ Found {found_treasure['name']} worth **{found_treasure['value']:,}** 💵! ║", discord.Color.green())
    await ctx.send(embed=embed)

@bot.command()
async def explore(ctx):
    """Explore mysterious places"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    if user.get("last_explore") and (now - user["last_explore"].replace(tzinfo=None)).seconds < 300:
        remaining = 300 - (now - user["last_explore"].replace(tzinfo=None)).seconds
        embed = create_aesthetic_embed("🗺️ Still Exploring", f"║ Continue exploring for **{remaining}** seconds! ║", discord.Color.orange())
        return await ctx.send(embed=embed)

    locations = ["🏰 Ancient Castle", "🌋 Volcanic Cave", "🏛️ Lost Temple", "🌊 Underwater Ruins", "🌟 Space Station"]
    rewards = [50, 100, 200, 500, 1000]

    location = random.choice(locations)
    reward = random.choice(rewards)
    new_balance = user["balance"] + reward

    await update_user_data(ctx.author.id, {"balance": new_balance, "last_explore": now})

    embed = create_aesthetic_embed("🗺️ Adventure", f"║ Explored {location} and found **{reward:,}** 💵! ║", discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command()
async def steal(ctx, member: discord.Member):
    """Attempt to steal from another user"""
    if member == ctx.author:
        embed = create_aesthetic_embed("❌ Invalid Target", "║ You can't steal from yourself! ║", discord.Color.red())
        return await ctx.send(embed=embed)

    user = await get_user_data(ctx.author.id)
    target = await get_user_data(member.id)
    now = datetime.datetime.now()

    if user.get("last_steal") and (now - user["last_steal"].replace(tzinfo=None)).seconds < 600:
        remaining = 600 - (now - user["last_steal"].replace(tzinfo=None)).seconds
        embed = create_aesthetic_embed("🕵️ Laying Low", f"║ Wait **{remaining}** seconds before attempting another theft! ║", discord.Color.orange())
        return await ctx.send(embed=embed)

    if target["balance"] < 100:
        embed = create_aesthetic_embed("💸 No Money", "║ Target is too poor to steal from! ║", discord.Color.red())
        return await ctx.send(embed=embed)

    # Check if target has crime protection
    if await has_active_effect(member.id, "crime_protection"):
        embed = create_aesthetic_embed("🛡️ Target Protected",
                                     f"║ {member.display_name} has crime protection active! ║",
                                     discord.Color.blue())
        return await ctx.send(embed=embed)

    success_rate = 0.4 + (user.get("level", 1) * 0.01)

    if random.random() < success_rate:
        stolen_amount = min(random.randint(50, 500), target["balance"] // 4)

        await update_user_data(ctx.author.id, {"balance": user["balance"] + stolen_amount, "last_steal": now})
        await update_user_data(member.id, {"balance": target["balance"] - stolen_amount})

        embed = create_aesthetic_embed("🦹 Theft Success", f"║ Stole **{stolen_amount:,}** 💵 from {member.display_name}! ║", discord.Color.green())
    else:
        penalty = 200
        await update_user_data(ctx.author.id, {"balance": max(0, user["balance"] - penalty), "last_steal": now})

        embed = create_aesthetic_embed("🚨 Caught Red-Handed", f"║ Failed to steal and lost **{penalty:,}** 💵! ║", discord.Color.red())

    await ctx.send(embed=embed)

@bot.command()
async def rob(ctx, member: discord.Member):
    """Rob another user for their money"""
    if member == ctx.author:
        embed = create_aesthetic_embed("❌ Invalid Target", "║ You can't rob yourself! ║", discord.Color.red())
        return await ctx.send(embed=embed)

    if member.bot:
        embed = create_aesthetic_embed("❌ Invalid Target", "║ You can't rob bots! ║", discord.Color.red())
        return await ctx.send(embed=embed)

    user = await get_user_data(ctx.author.id)
    target = await get_user_data(member.id)
    now = datetime.datetime.now()

    # Check cooldown - 10 minutes
    if user.get("last_rob") and (now - user["last_rob"].replace(tzinfo=None)).seconds < 600:
        remaining = 600 - (now - user["last_rob"].replace(tzinfo=None)).seconds
        minutes = remaining // 60
        seconds = remaining % 60
        embed = create_aesthetic_embed("🕵️ Laying Low",
                                     f"║ You're hiding from the authorities! Wait **{minutes}m {seconds}s** ║",
                                     discord.Color.orange())
        return await ctx.send(embed=embed)

    # Check if target has enough money
    if target["balance"] < 100:
        embed = create_aesthetic_embed("💸 Poor Target",
                                     f"║ {member.display_name} is too poor to rob! (Less than 100 💵) ║",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    # Check if target has crime protection
    if await has_active_effect(member.id, "crime_protection"):
        embed = create_aesthetic_embed("🛡️ Target Protected",
                                     f"║ {member.display_name} has crime protection active! ║\n"
                                     f"║ They cannot be robbed right now! ║",
                                     discord.Color.blue())
        return await ctx.send(embed=embed)

    # Base success rate of 45% (not affected by level)
    success_rate = 0.45

    # Rob scenarios
    rob_scenarios = [
        {"name": "🏠 House Break-in", "emoji": "🏠", "risk": "HIGH"},
        {"name": "💰 Wallet Snatch", "emoji": "💰", "risk": "MEDIUM"},
        {"name": "🏧 ATM Mugging", "emoji": "🏧", "risk": "HIGH"},
        {"name": "💳 Card Theft", "emoji": "💳", "risk": "MEDIUM"},
        {"name": "📱 Phone Robbery", "emoji": "📱", "risk": "LOW"},
        {"name": "🚗 Car Robbery", "emoji": "🚗", "risk": "EXTREME"}
    ]

    selected_scenario = random.choice(rob_scenarios)

    if random.random() < success_rate:
        # Success - steal 15-40% of target's balance
        steal_percentage = random.uniform(0.15, 0.40)
        stolen_amount = min(int(target["balance"] * steal_percentage), target["balance"])
        stolen_amount = max(stolen_amount, 100)  # Minimum steal amount

        # Update balances
        await update_user_data(ctx.author.id, {
            "balance": user["balance"] + stolen_amount,
            "last_rob": now
        })
        await update_user_data(member.id, {
            "balance": target["balance"] - stolen_amount
        })

        description = f"""
╔══════════════════════════════════╗
║         🦹 **ROBBERY SUCCESS** 🦹         ║
╠══════════════════════════════════╣
║ **Operation:** {selected_scenario['name']}
║ **Target:** {member.display_name}
║ **Risk Level:** {selected_scenario['risk']}
║ **Amount Stolen:** {stolen_amount:,} 💵
║ **Success Rate:** {int(success_rate * 100)}%
║ **Your New Balance:** {user['balance'] + stolen_amount:,} 💵
╚══════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Criminal Success", description, discord.Color.green(), ctx.author.display_avatar.url)
        embed.add_field(name="🎯 Heist Result", value="✅ **SUCCESSFUL**", inline=True)
        embed.add_field(name="💸 Stolen Amount", value=f"**{stolen_amount:,}** 💵", inline=True)
        embed.add_field(name="🚨 Heat Level", value="🔥 **MODERATE** 🔥", inline=True)

    else:
        # Failure - lose money and get caught
        penalty = random.randint(200, 800)
        penalty = min(penalty, user["balance"])  # Don't go negative

        fail_scenarios = [
            {"text": "🚔 Caught red-handed by police", "emoji": "🚔"},
            {"text": "🚨 Security cameras recorded everything", "emoji": "🚨"},
            {"text": "🔫 Target fought back successfully", "emoji": "🔫"},
            {"text": "🏃 Target escaped and called cops", "emoji": "🏃"},
            {"text": "👥 Witnesses called authorities", "emoji": "👥"},
            {"text": "🐕 Guard dog attacked you", "emoji": "🐕"}
        ]

        fail_scenario = random.choice(fail_scenarios)

        await update_user_data(ctx.author.id, {
            "balance": max(0, user["balance"] - penalty),
            "last_rob": now
        })

        description = f"""
╔══════════════════════════════════╗
║          ❌ **ROBBERY FAILED** ❌          ║
╠══════════════════════════════════╣
║ **Operation:** {selected_scenario['name']}
║ **Target:** {member.display_name}
║ **Failure:** {fail_scenario['text']}
║ **Penalty:** -{penalty:,} 💵
║ **New Balance:** {max(0, user['balance'] - penalty):,} 💵
╚══════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Criminal Justice", description, discord.Color.red(), ctx.author.display_avatar.url)
        embed.add_field(name="🚨 Arrest Status", value="❌ **CAUGHT**", inline=True)
        embed.add_field(name="💸 Fine Amount", value=f"**{penalty:,}** 💵", inline=True)
        embed.add_field(name="⚖️ Justice", value="🔨 **SERVED**", inline=True)

    await ctx.send(embed=embed)



@bot.command()
async def spin(ctx, amount: int):
    """Spin the wheel of fortune"""
    user = await get_user_data(ctx.author.id)

    if amount <= 0:
        embed = create_aesthetic_embed("❌ Invalid Bet", "║ Bet amount must be positive! ║", discord.Color.red())
        return await ctx.send(embed=embed)

    if user["balance"] < amount:
        embed = create_aesthetic_embed("💸 Insufficient Funds", f"║ You need **{amount:,}** 💵 to spin! ║", discord.Color.red())
        return await ctx.send(embed=embed)

    multipliers = [0, 0.5, 1, 1.5, 2, 3, 5, 10]
    weights = [30, 25, 20, 15, 5, 3, 1.5, 0.5]

    multiplier = random.choices(multipliers, weights=weights)[0]
    winnings = int(amount * multiplier) - amount
    new_balance = user["balance"] + winnings

    await update_user_data(ctx.author.id, {"balance": new_balance})

    if multiplier == 0:
        result = f"Lost **{amount:,}** 💵"
        color = discord.Color.red()
    elif multiplier < 1:
        result = f"Won **{int(amount * multiplier):,}** 💵"
        color = discord.Color.orange()
    elif multiplier == 1:
        result = "Broke even!"
        color = discord.Color.yellow()
    else:
        result = f"Won **{int(amount * multiplier):,}** 💵"
        color = discord.Color.green()

    embed = create_aesthetic_embed("🎡 Wheel of Fortune", f"║ Multiplier: **{multiplier}x** - {result} ║", color)
    await ctx.send(embed=embed)

@bot.command()
async def race(ctx, bet: int):
    """Bet on animal races"""
    user = await get_user_data(ctx.author.id)

    if bet <= 0:
        embed = create_aesthetic_embed("❌ Invalid Bet", "║ Bet amount must be positive! ║", discord.Color.red())
        return await ctx.send(embed=embed)

    if user["balance"] < bet:
        embed = create_aesthetic_embed("💸 Insufficient Funds", f"║ You need **{bet:,}** 💵 to bet! ║", discord.Color.red())
        return await ctx.send(embed=embed)

    animals = ["🐎 Horse", "🐕 Dog", "🐰 Rabbit", "🐢 Turtle", "🦆 Duck"]
    winner = random.choice(animals)
    your_pick = random.choice(animals)

    if winner == your_pick:
        winnings = bet * 4
        new_balance = user["balance"] + winnings
        result_text = f"Your {your_pick} won! Earned **{winnings:,}** 💵"
        color = discord.Color.green()
    else:
        new_balance = user["balance"] - bet
        result_text = f"Your {your_pick} lost. Winner was {winner}. Lost **{bet:,}** 💵"
        color = discord.Color.red()

    await update_user_data(ctx.author.id, {"balance": new_balance})

    embed = create_aesthetic_embed("🏁 Animal Race", f"║ {result_text} ║", color)
    await ctx.send(embed=embed)

@bot.command()
async def duel(ctx, member: discord.Member, amount: int):
    """Duel another user for money"""
    if member == ctx.author:
        embed = create_aesthetic_embed("❌ Invalid Target", "║ You can't duel yourself! ║", discord.Color.red())
        return await ctx.send(embed=embed)

    user = await get_user_data(ctx.author.id)
    target = await get_user_data(member.id)

    if user["balance"] < amount or target["balance"] < amount:
        embed = create_aesthetic_embed("💸 Insufficient Funds", "║ Both players need enough money for the duel! ║", discord.Color.red())
        return await ctx.send(embed=embed)

    # Simple random duel
    winner = random.choice([ctx.author, member])
    loser = member if winner == ctx.author else ctx.author

    winner_data = await get_user_data(winner.id)
    loser_data = await get_user_data(loser.id)

    await update_user_data(winner.id, {"balance": winner_data["balance"] + amount})
    await update_user_data(loser.id, {"balance": loser_data["balance"] - amount})

    embed = create_aesthetic_embed("⚔️ Duel Result", f"║ **{winner.display_name}** defeated **{loser.display_name}** and won **{amount:,}** 💵! ║", discord.Color.gold())
    await ctx.send(embed=embed)

# Extensive trivia question pool
TRIVIA_QUESTIONS = [
    # Geography Questions
    {"q": "What is the capital of Japan?", "a": "tokyo", "reward": 100, "category": "Geography"},
    {"q": "What is the largest ocean?", "a": "pacific", "reward": 180, "category": "Geography"},
    {"q": "How many continents are there?", "a": "7", "reward": 120, "category": "Geography"},
    {"q": "What is the capital of Australia?", "a": "canberra", "reward": 200, "category": "Geography"},
    {"q": "Which river is the longest in the world?", "a": "nile", "reward": 250, "category": "Geography"},
    {"q": "What is the smallest country in the world?", "a": "vatican city", "reward": 300, "category": "Geography"},
    {"q": "Which mountain range contains Mount Everest?", "a": "himalayas", "reward": 220, "category": "Geography"},
    {"q": "What is the capital of Canada?", "a": "ottawa", "reward": 180, "category": "Geography"},
    {"q": "Which desert is the largest in the world?", "a": "sahara", "reward": 200, "category": "Geography"},
    {"q": "What is the deepest ocean trench?", "a": "mariana trench", "reward": 350, "category": "Geography"},

    # Science Questions
    {"q": "What planet is closest to the sun?", "a": "mercury", "reward": 150, "category": "Science"},
    {"q": "What is the chemical symbol for gold?", "a": "au", "reward": 200, "category": "Science"},
    {"q": "How many bones are in the human body?", "a": "206", "reward": 250, "category": "Science"},
    {"q": "What gas do plants absorb from the atmosphere?", "a": "carbon dioxide", "reward": 180, "category": "Science"},
    {"q": "What is the speed of light?", "a": "299792458", "reward": 400, "category": "Science"},
    {"q": "What is the hardest natural substance?", "a": "diamond", "reward": 220, "category": "Science"},
    {"q": "How many chambers does a human heart have?", "a": "4", "reward": 160, "category": "Science"},
    {"q": "What is the largest planet in our solar system?", "a": "jupiter", "reward": 140, "category": "Science"},
    {"q": "What is the smallest unit of matter?", "a": "atom", "reward": 280, "category": "Science"},
    {"q": "What type of animal is a whale?", "a": "mammal", "reward": 120, "category": "Science"},

    # History Questions
    {"q": "In which year did World War 2 end?", "a": "1945", "reward": 200, "category": "History"},
    {"q": "Who was the first person to walk on the moon?", "a": "neil armstrong", "reward": 250, "category": "History"},
    {"q": "Which ancient wonder of the world was in Egypt?", "a": "great pyramid of giza", "reward": 300, "category": "History"},
    {"q": "Who painted the Mona Lisa?", "a": "leonardo da vinci", "reward": 180, "category": "History"},
    {"q": "In which year did the Titanic sink?", "a": "1912", "reward": 220, "category": "History"},
    {"q": "Who was the first President of the United States?", "a": "george washington", "reward": 150, "category": "History"},
    {"q": "Which empire was ruled by Julius Caesar?", "a": "roman empire", "reward": 200, "category": "History"},
    {"q": "In which year did the Berlin Wall fall?", "a": "1989", "reward": 240, "category": "History"},
    {"q": "Who discovered America?", "a": "christopher columbus", "reward": 160, "category": "History"},
    {"q": "Which war was fought between the North and South in America?", "a": "civil war", "reward": 180, "category": "History"},

    # Math Questions
    {"q": "What is 2+2?", "a": "4", "reward": 50, "category": "Math"},
    {"q": "What is 12 x 12?", "a": "144", "reward": 80, "category": "Math"},
    {"q": "What is the square root of 64?", "a": "8", "reward": 120, "category": "Math"},
    {"q": "What is 15% of 200?", "a": "30", "reward": 140, "category": "Math"},
    {"q": "What is pi rounded to 2 decimal places?", "a": "3.14", "reward": 160, "category": "Math"},
    {"q": "What is 7 x 8?", "a": "56", "reward": 70, "category": "Math"},
    {"q": "What is 100 divided by 4?", "a": "25", "reward": 60, "category": "Math"},
    {"q": "What is the next prime number after 7?", "a": "11", "reward": 180, "category": "Math"},
    {"q": "What is 9 squared?", "a": "81", "reward": 100, "category": "Math"},
    {"q": "What is 1000 - 237?", "a": "763", "reward": 120, "category": "Math"},

    # Entertainment Questions
    {"q": "Who created Mickey Mouse?", "a": "walt disney", "reward": 150, "category": "Entertainment"},
    {"q": "What is the highest-grossing film of all time?", "a": "avatar", "reward": 200, "category": "Entertainment"},
    {"q": "How many Harry Potter books are there?", "a": "7", "reward": 140, "category": "Entertainment"},
    {"q": "Who composed The Four Seasons?", "a": "vivaldi", "reward": 250, "category": "Entertainment"},
    {"q": "What is the longest-running animated TV series?", "a": "the simpsons", "reward": 220, "category": "Entertainment"},
    {"q": "Who directed the movie Jaws?", "a": "steven spielberg", "reward": 180, "category": "Entertainment"},
    {"q": "What instrument did Louis Armstrong play?", "a": "trumpet", "reward": 160, "category": "Entertainment"},
    {"q": "Which Shakespeare play features Romeo and Juliet?", "a": "romeo and juliet", "reward": 140, "category": "Entertainment"},
    {"q": "How many strings does a standard guitar have?", "a": "6", "reward": 100, "category": "Entertainment"},
    {"q": "Who wrote the Lord of the Rings trilogy?", "a": "j.r.r. tolkien", "reward": 200, "category": "Entertainment"},

    # Sports Questions
    {"q": "How many players are on a basketball team on court?", "a": "5", "reward": 120, "category": "Sports"},
    {"q": "What sport is played at Wimbledon?", "a": "tennis", "reward": 140, "category": "Sports"},
    {"q": "How many holes are on a standard golf course?", "a": "18", "reward": 160, "category": "Sports"},
    {"q": "What is the maximum score in ten-pin bowling?", "a": "300", "reward": 200, "category": "Sports"},
    {"q": "Which country won the 2018 FIFA World Cup?", "a": "france", "reward": 180, "category": "Sports"},
    {"q": "How many rings are on the Olympic flag?", "a": "5", "reward": 120, "category": "Sports"},
    {"q": "What sport is known as 'the beautiful game'?", "a": "soccer", "reward": 100, "category": "Sports"},
    {"q": "How long is a marathon in miles?", "a": "26.2", "reward": 220, "category": "Sports"},
    {"q": "What is the diameter of a basketball hoop in inches?", "a": "18", "reward": 240, "category": "Sports"},
    {"q": "Which sport uses terms like 'spike' and 'dig'?", "a": "volleyball", "reward": 160, "category": "Sports"},

    # Technology Questions
    {"q": "Who founded Microsoft?", "a": "bill gates", "reward": 180, "category": "Technology"},
    {"q": "What does 'WWW' stand for?", "a": "world wide web", "reward": 160, "category": "Technology"},
    {"q": "What year was the first iPhone released?", "a": "2007", "reward": 200, "category": "Technology"},
    {"q": "What does 'CPU' stand for?", "a": "central processing unit", "reward": 220, "category": "Technology"},
    {"q": "Who founded Apple Inc.?", "a": "steve jobs", "reward": 180, "category": "Technology"},
    {"q": "What does 'HTML' stand for?", "a": "hypertext markup language", "reward": 250, "category": "Technology"},
    {"q": "What social media platform has a bird as its logo?", "a": "twitter", "reward": 120, "category": "Technology"},
    {"q": "What does 'USB' stand for?", "a": "universal serial bus", "reward": 200, "category": "Technology"},
    {"q": "Who founded Facebook?", "a": "mark zuckerberg", "reward": 160, "category": "Technology"},
    {"q": "What programming language is known for its snake logo?", "a": "python", "reward": 240, "category": "Technology"},

    # Nature Questions
    {"q": "What is the tallest tree species in the world?", "a": "redwood", "reward": 220, "category": "Nature"},
    {"q": "How many legs does a spider have?", "a": "8", "reward": 100, "category": "Nature"},
    {"q": "What is the fastest land animal?", "a": "cheetah", "reward": 160, "category": "Nature"},
    {"q": "What is the largest mammal in the world?", "a": "blue whale", "reward": 200, "category": "Nature"},
    {"q": "How many hearts does an octopus have?", "a": "3", "reward": 240, "category": "Nature"},
    {"q": "What is the process by which plants make food?", "a": "photosynthesis", "reward": 180, "category": "Nature"},
    {"q": "What is a group of lions called?", "a": "pride", "reward": 140, "category": "Nature"},
    {"q": "How many wings does a bee have?", "a": "4", "reward": 120, "category": "Nature"},
    {"q": "What is the largest type of shark?", "a": "whale shark", "reward": 200, "category": "Nature"},
    {"q": "What do pandas mainly eat?", "a": "bamboo", "reward": 140, "category": "Nature"},
]

# Track asked questions per user to avoid repeats
user_trivia_history = {}

@bot.command()
async def trivia(ctx):
    """Answer trivia questions for rewards with extensive question pool"""
    user_id = ctx.author.id

    # Initialize user history if not exists
    if user_id not in user_trivia_history:
        user_trivia_history[user_id] = set()

    # Get available questions (not asked to this user yet)
    available_questions = [q for i, q in enumerate(TRIVIA_QUESTIONS) if i not in user_trivia_history[user_id]]

    # If all questions have been asked, reset their history
    if not available_questions:
        user_trivia_history[user_id] = set()
        available_questions = TRIVIA_QUESTIONS

    # Select random question from available ones
    question_index = TRIVIA_QUESTIONS.index(random.choice(available_questions))
    question = TRIVIA_QUESTIONS[question_index]

    # Mark question as asked for this user
    user_trivia_history[user_id].add(question_index)

    # Create enhanced embed with category info
    description = f"""
╔══════════════════════════════════╗
║         🧠 **TRIVIA TIME** 🧠         ║
╠══════════════════════════════════╣
║ **Category:** {question['category']}
║ **Question:** {question['q']}
║ **Reward:** {question['reward']:,} 💵
║ **Questions Answered:** {len(user_trivia_history[user_id])}/{len(TRIVIA_QUESTIONS)}
╚══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Brain Challenge", description, discord.Color.blue())
    embed.add_field(name="⏰ Time Limit", value="30 seconds", inline=True)
    embed.add_field(name="🎯 Difficulty", value=f"**{question['category']}**", inline=True)
    embed.add_field(name="💡 Hint", value="Think carefully!", inline=True)
    embed.set_footer(text="Type your answer below!")

    await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        answer = await bot.wait_for('message', check=check, timeout=30)

        # Check multiple possible correct answers
        correct_answers = [question['a'].lower().strip()]
        # Add alternative acceptable answers for some questions
        user_answer = answer.content.lower().strip()

        if user_answer in correct_answers or any(ans in user_answer for ans in correct_answers):
            user = await get_user_data(ctx.author.id)

            # Bonus for streak (every 5 questions in a row)
            streak_bonus = 0
            if len(user_trivia_history[user_id]) % 5 == 0 and len(user_trivia_history[user_id]) > 0:
                streak_bonus = question['reward'] // 2

            total_reward = question['reward'] + streak_bonus
            new_balance = user["balance"] + total_reward
            await update_user_data(ctx.author.id, {"balance": new_balance})

            # Add XP for correct answer
            leveled_up, new_level = await add_xp(ctx.author.id, 25)

            result_description = f"║ **Correct!** You earned **{total_reward:,}** 💵 ║"
            if streak_bonus > 0:
                result_description += f"\n║ **Streak Bonus:** +{streak_bonus:,} 💵 ║"
            if leveled_up:
                result_description += f"\n║ **LEVEL UP!** You're now level **{new_level}**! ║"

            embed = create_aesthetic_embed("✅ Brilliant!", result_description, discord.Color.green())
            embed.add_field(name="🧠 Knowledge Points", value="+25 XP", inline=True)
            embed.add_field(name="📊 Progress", value=f"{len(user_trivia_history[user_id])}/{len(TRIVIA_QUESTIONS)}", inline=True)
            embed.add_field(name="🎯 Category Mastery", value=question['category'], inline=True)
        else:
            result_description = f"║ **Wrong Answer** ║\n║ The correct answer was: **{question['a']}** ║"
            embed = create_aesthetic_embed("❌ Not Quite", result_description, discord.Color.red())
            embed.add_field(name="💡 Learn More", value=f"Study up on {question['category']}!", inline=True)

        await ctx.send(embed=embed)

    except asyncio.TimeoutError:
        result_description = f"║ **Time's Up!** ⏰ ║\n║ The correct answer was: **{question['a']}** ║"
        embed = create_aesthetic_embed("⏰ Too Slow", result_description, discord.Color.orange())
        embed.add_field(name="💨 Speed Tip", value="Think faster next time!", inline=True)
        await ctx.send(embed=embed)

# Extensive riddle collection
RIDDLE_COLLECTION = [
    # Classic Riddles
    {"q": "I am taken from a mine, and shut up in a wooden case, from which I am never released. What am I?", "a": ["pencil lead", "graphite", "lead"], "reward": 300, "difficulty": "Medium"},
    {"q": "The more you take, the more you leave behind. What am I?", "a": ["footsteps", "steps", "footprints"], "reward": 250, "difficulty": "Easy"},
    {"q": "What has keys but no locks, space but no room, and you can enter but not go inside?", "a": ["keyboard", "computer keyboard"], "reward": 280, "difficulty": "Medium"},
    {"q": "What gets wet while drying?", "a": ["towel", "a towel"], "reward": 200, "difficulty": "Easy"},
    {"q": "What has hands but cannot clap?", "a": ["clock", "a clock", "watch"], "reward": 220, "difficulty": "Easy"},

    # Logic Riddles
    {"q": "I have cities, but no houses. I have mountains, but no trees. I have water, but no fish. What am I?", "a": ["map", "a map"], "reward": 350, "difficulty": "Hard"},
    {"q": "What can travel around the world while staying in a corner?", "a": ["stamp", "postage stamp", "a stamp"], "reward": 320, "difficulty": "Medium"},
    {"q": "I'm tall when I'm young, and short when I'm old. What am I?", "a": ["candle", "a candle"], "reward": 240, "difficulty": "Easy"},
    {"q": "What has a head and a tail but no body?", "a": ["coin", "a coin"], "reward": 260, "difficulty": "Easy"},
    {"q": "What goes up but never comes down?", "a": ["age", "your age"], "reward": 280, "difficulty": "Medium"},

    # Wordplay Riddles
    {"q": "What has a neck but no head?", "a": ["bottle", "a bottle"], "reward": 230, "difficulty": "Easy"},
    {"q": "What has an eye but cannot see?", "a": ["needle", "a needle"], "reward": 250, "difficulty": "Medium"},
    {"q": "What has teeth but cannot bite?", "a": ["comb", "a comb", "zipper", "saw"], "reward": 270, "difficulty": "Medium"},
    {"q": "What has a ring but no finger?", "a": ["telephone", "phone", "tree"], "reward": 290, "difficulty": "Medium"},
    {"q": "What has a foot but no leg?", "a": ["ruler", "a ruler", "snail"], "reward": 260, "difficulty": "Medium"},

    # Mathematical Riddles
    {"q": "I am an odd number. Take away a letter and I become even. What number am I?", "a": ["seven", "7"], "reward": 380, "difficulty": "Hard"},
    {"q": "What three positive numbers give the same answer when multiplied and added together?", "a": ["1 2 3", "123", "one two three"], "reward": 400, "difficulty": "Hard"},
    {"q": "If there are three apples and you take away two, how many do you have?", "a": ["two", "2"], "reward": 200, "difficulty": "Easy"},
    {"q": "A man was outside in the rain without an umbrella or hat. His hair didn't get wet. Why?", "a": ["bald", "he was bald", "no hair"], "reward": 320, "difficulty": "Medium"},
    {"q": "What comes once in a minute, twice in a moment, but never in a thousand years?", "a": ["letter m", "m", "the letter m"], "reward": 360, "difficulty": "Hard"},

    # Object Riddles
    {"q": "I have a golden head and a golden tail, but no golden body. What am I?", "a": ["coin", "penny", "a coin"], "reward": 290, "difficulty": "Medium"},
    {"q": "What breaks but never falls, and what falls but never breaks?", "a": ["day breaks night falls", "dawn and dusk", "day and night"], "reward": 420, "difficulty": "Hard"},
    {"q": "I fly at night, I am not a bird, I have no feathers, I have no wings. What am I?", "a": ["bat", "a bat"], "reward": 280, "difficulty": "Medium"},
    {"q": "What room do ghosts avoid?", "a": ["living room", "the living room"], "reward": 300, "difficulty": "Medium"},
    {"q": "What goes through towns and hills but never moves?", "a": ["road", "a road", "highway"], "reward": 340, "difficulty": "Hard"},

    # Nature Riddles
    {"q": "I'm light as a feather, yet the strongest person can't hold me for five minutes. What am I?", "a": ["breath", "your breath"], "reward": 350, "difficulty": "Hard"},
    {"q": "What always runs but never walks, often murmurs but never talks, has a bed but never sleeps?", "a": ["river", "a river", "stream"], "reward": 380, "difficulty": "Hard"},
    {"q": "I'm found in socks, scarves and mittens, I'm found in the paws of playful kittens. What am I?", "a": ["yarn", "wool", "thread"], "reward": 270, "difficulty": "Medium"},
    {"q": "What has roots that nobody sees, is taller than trees, up, up it goes, yet never grows?", "a": ["mountain", "a mountain"], "reward": 330, "difficulty": "Hard"},
    {"q": "I have a cape but cannot fly, I have a stem but am not a flower. What am I?", "a": ["mushroom", "a mushroom"], "reward": 310, "difficulty": "Medium"},

    # Tricky Riddles
    {"q": "What belongs to you but others use it more than you do?", "a": ["name", "your name"], "reward": 320, "difficulty": "Medium"},
    {"q": "What can you catch but not throw?", "a": ["cold", "a cold", "illness"], "reward": 290, "difficulty": "Medium"},
    {"q": "What has many keys but can't open a single lock?", "a": ["piano", "a piano"], "reward": 260, "difficulty": "Easy"},
    {"q": "What gets bigger when more is taken away from it?", "a": ["hole", "a hole"], "reward": 340, "difficulty": "Hard"},
    {"q": "I shave every day, but my beard stays the same. What am I?", "a": ["barber", "a barber"], "reward": 300, "difficulty": "Medium"},

    # Brain Teasers
    {"q": "Forward I am heavy, but backward I am not. What am I?", "a": ["ton", "ton not"], "reward": 380, "difficulty": "Hard"},
    {"q": "What is so fragile that saying its name breaks it?", "a": ["silence"], "reward": 400, "difficulty": "Hard"},
    {"q": "I am not alive, but I grow; I don't have lungs, but I need air; I don't have a mouth, but water kills me. What am I?", "a": ["fire"], "reward": 420, "difficulty": "Hard"},
    {"q": "The more of this there is, the less you see. What is it?", "a": ["darkness", "dark"], "reward": 350, "difficulty": "Hard"},
    {"q": "What is always in front of you but can't be seen?", "a": ["future", "the future"], "reward": 330, "difficulty": "Medium"},

    # Modern Riddles
    {"q": "I have no body, but I have a voice. I have no form, but I can be heard. What am I?", "a": ["echo", "an echo"], "reward": 310, "difficulty": "Medium"},
    {"q": "What can fill a room but takes up no space?", "a": ["light", "sound"], "reward": 280, "difficulty": "Medium"},
    {"q": "I'm not alive, but I can die. I'm not solid, but I can be broken. What am I?", "a": ["promise", "a promise", "heart"], "reward": 360, "difficulty": "Hard"},
    {"q": "What has one eye but cannot see?", "a": ["needle", "storm", "hurricane"], "reward": 270, "difficulty": "Medium"},
    {"q": "What can you hold in your right hand but never in your left hand?", "a": ["left hand", "your left hand"], "reward": 320, "difficulty": "Medium"},

    # Creative Riddles
    {"q": "I dance on one leg and know only one shape. What am I?", "a": ["compass", "a compass"], "reward": 350, "difficulty": "Hard"},
    {"q": "I have no beginning, end, or middle. What am I?", "a": ["circle", "a circle"], "reward": 290, "difficulty": "Medium"},
    {"q": "What disappears as soon as you say its name?", "a": ["silence"], "reward": 380, "difficulty": "Hard"},
    {"q": "I am weightless, but you can see me. Put me in a bucket, and I'll make it lighter. What am I?", "a": ["hole", "a hole"], "reward": 360, "difficulty": "Hard"},
    {"q": "What invention lets you look right through a wall?", "a": ["window", "a window"], "reward": 250, "difficulty": "Easy"},
]

# Track asked riddles per user
user_riddle_history = {}

@bot.command()
async def riddle(ctx):
    """Solve riddles for bigger rewards with extensive riddle collection"""
    user_id = ctx.author.id

    # Initialize user history if not exists
    if user_id not in user_riddle_history:
        user_riddle_history[user_id] = set()

    # Get available riddles (not asked to this user yet)
    available_riddles = [r for i, r in enumerate(RIDDLE_COLLECTION) if i not in user_riddle_history[user_id]]

    # If all riddles have been asked, reset their history
    if not available_riddles:
        user_riddle_history[user_id] = set()
        available_riddles = RIDDLE_COLLECTION

    # Select random riddle from available ones
    riddle_index = RIDDLE_COLLECTION.index(random.choice(available_riddles))
    riddle = RIDDLE_COLLECTION[riddle_index]

    # Mark riddle as asked for this user
    user_riddle_history[user_id].add(riddle_index)

    # Create enhanced embed with difficulty info
    difficulty_colors = {
        "Easy": discord.Color.green(),
        "Medium": discord.Color.orange(),
        "Hard": discord.Color.red()
    }

    difficulty_emojis = {
        "Easy": "🟢",
        "Medium": "🟡",
        "Hard": "🔴"
    }

    color = difficulty_colors.get(riddle['difficulty'], discord.Color.purple())
    difficulty_emoji = difficulty_emojis.get(riddle['difficulty'], "🧩")

    description = f"""
╔══════════════════════════════════╗
║       🧩 **RIDDLE CHALLENGE** 🧩       ║
╠══════════════════════════════════╣
║ **Difficulty:** {difficulty_emoji} **{riddle['difficulty']}**
║ **Reward:** {riddle['reward']:,} 💵
║ **Riddles Solved:** {len(user_riddle_history[user_id])}/{len(RIDDLE_COLLECTION)}
║
║ **RIDDLE:**
║ {riddle['q']}
╚══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Mind Bender", description, color)
    embed.add_field(name="⏰ Time Limit", value="60 seconds", inline=True)
    embed.add_field(name="🎯 Difficulty", value=f"{difficulty_emoji} **{riddle['difficulty']}**", inline=True)
    embed.add_field(name="💡 Think Hard", value="Every word matters!", inline=True)
    embed.set_footer(text="Type your answer below! Think outside the box!")

    await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        answer = await bot.wait_for('message', check=check, timeout=60)

        # Check if answer matches any of the acceptable answers
        user_answer = answer.content.lower().strip()
        correct = any(ans.lower() in user_answer or user_answer in ans.lower() for ans in riddle['a'])

        if correct:
            user = await get_user_data(ctx.author.id)

            # Difficulty bonus
            difficulty_multiplier = {"Easy": 1.0, "Medium": 1.2, "Hard": 1.5}
            multiplier = difficulty_multiplier.get(riddle['difficulty'], 1.0)

            # Streak bonus (every 3 riddles)
            streak_bonus = 0
            if len(user_riddle_history[user_id]) % 3 == 0 and len(user_riddle_history[user_id]) > 0:
                streak_bonus = int(riddle['reward'] * 0.5)

            total_reward = int(riddle['reward'] * multiplier) + streak_bonus
            new_balance = user["balance"] + total_reward
            await update_user_data(ctx.author.id, {"balance": new_balance})

            # Add XP based on difficulty
            xp_rewards = {"Easy": 30, "Medium": 50, "Hard": 80}
            xp_gained = xp_rewards.get(riddle['difficulty'], 40)
            leveled_up, new_level = await add_xp(ctx.author.id, xp_gained)

            result_description = f"║ **🎉 RIDDLE SOLVED! 🎉** ║\n"
            result_description += f"║ Base Reward: {riddle['reward']:,} 💵 ║\n"
            if multiplier > 1.0:
                result_description += f"║ Difficulty Bonus: x{multiplier} ║\n"
            if streak_bonus > 0:
                result_description += f"║ Streak Bonus: +{streak_bonus:,} 💵 ║\n"
            result_description += f"║ **Total Earned: {total_reward:,} 💵** ║"

            if leveled_up:
                result_description += f"\n║ **LEVEL UP!** Now level **{new_level}**! ║"

            embed = create_aesthetic_embed("Genius Mind!", result_description, discord.Color.gold())
            embed.add_field(name="🧠 Wisdom Points", value=f"+{xp_gained} XP", inline=True)
            embed.add_field(name="📊 Progress", value=f"{len(user_riddle_history[user_id])}/{len(RIDDLE_COLLECTION)}", inline=True)
            embed.add_field(name="🏆 Master Level", value=riddle['difficulty'], inline=True)
        else:
            possible_answers = " / ".join(riddle['a'][:3])  # Show first 3 possible answers
            result_description = f"║ **Not Quite Right** ║\n║ Possible answers: **{possible_answers}** ║"
            embed = create_aesthetic_embed("❌ Keep Thinking", result_description, discord.Color.red())
            embed.add_field(name="💡 Hint", value="Try thinking differently!", inline=True)

        await ctx.send(embed=embed)

    except asyncio.TimeoutError:
        possible_answers = " / ".join(riddle['a'][:3])
        result_description = f"║ **Time's Up!** ⏰ ║\n║ Possible answers: **{possible_answers}** ║"
        embed = create_aesthetic_embed("⏰ Too Slow", result_description, discord.Color.orange())
        embed.add_field(name="💨 Speed Tip", value="Think faster next time!", inline=True)
        await ctx.send(embed=embed)

@bot.command()
async def quest(ctx):
    """Go on adventures for rewards"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    if user.get("last_quest") and (now - user["last_quest"].replace(tzinfo=None)).seconds < 1200:
        remaining = 1200 - (now - user["last_quest"].replace(tzinfo=None)).seconds
        embed = create_aesthetic_embed("🗡️ Already Questing", f"║ Complete current quest in **{remaining//60}m {remaining%60}s**! ║", discord.Color.orange())
        await ctx.send(embed=embed)
        return  # Early return to prevent further execution

    quests = [
        {"name": "🐉 Slay the Dragon", "reward": 2000, "xp": 100},
        {"name": "👑 Rescue the Princess", "reward": 1500, "xp": 80},
        {"name": "🏰 Defend the Castle", "reward": 1200, "xp": 70},
        {"name": "🌟 Find the Lost Artifact", "reward": 1800, "xp": 90},
        {"name": "🦄 Tame the Unicorn", "reward": 2500, "xp": 120}
    ]

    quest = random.choice(quests)
    success_rate = 0.6 + (user.get("level", 1) * 0.02)

    if random.random() < success_rate:
        new_balance = user["balance"] + quest["reward"]
        leveled_up, new_level = await add_xp(ctx.author.id, quest["xp"])

        await update_user_data(ctx.author.id, {"balance": new_balance, "last_quest": now})

        result_text = f"║ **Quest:** {quest['name']} ║\n║ **Reward:** {quest['reward']:,} 💵 ║\n║ **XP Gained:** {quest['xp']} ⭐ ║"
        if leveled_up:
            result_text += f"\n║ **LEVEL UP!** Now level {new_level}! ║"

        embed = create_aesthetic_embed("⚔️ Quest Complete!", result_text, discord.Color.gold())
    else:
        await update_user_data(ctx.author.id, {"last_quest": now})
        embed = create_aesthetic_embed("💀 Quest Failed", f"║ Failed the quest: {quest['name']} ║", discord.Color.red())

    await ctx.send(embed=embed)

# More social/action commands
@bot.command()
async def wave(ctx, member: discord.Member = None):
    """Wave at someone"""
    if member:
        embed = create_aesthetic_embed("👋 Wave", f"║ **{ctx.author.display_name}** waves at **{member.display_name}**! ║", discord.Color.blue())
    else:
        embed = create_aesthetic_embed("👋 Wave", f"║ **{ctx.author.display_name}** waves at everyone! ║", discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command()
async def boop(ctx, member: discord.Member):
    """Boop someone's nose"""
    embed = create_aesthetic_embed("👉 Boop", f"║ **{ctx.author.display_name}** boops **{member.display_name}**'s nose! ║", discord.Color.pink())
    await ctx.send(embed=embed)

@bot.command()
async def snuggle(ctx, member: discord.Member):
    """Snuggle with someone"""
    embed = create_aesthetic_embed("🤗 Snuggle", f"║ **{ctx.author.display_name}** snuggles with **{member.display_name}**! ║", discord.Color.pink())
    await ctx.send(embed=embed)

@bot.command()
async def handhold(ctx, member: discord.Member):
    """Hold hands with someone"""
    embed = create_aesthetic_embed("🤝 Hand Hold", f"║ **{ctx.author.display_name}** holds hands with **{member.display_name}**! ║", discord.Color.pink())
    await ctx.send(embed=embed)

@bot.command()
async def greet(ctx, member: discord.Member = None):
    """Greet someone"""
    if member:
        embed = create_aesthetic_embed("👋 Greeting", f"║ **{ctx.author.display_name}** greets **{member.display_name}**! ║", discord.Color.green())
    else:
        embed = create_aesthetic_embed("👋 Greeting", f"║ **{ctx.author.display_name}** greets everyone! ║", discord.Color.green())
    await ctx.send(embed=embed)

@bot.command()
async def bully(ctx, member: discord.Member):
    """Playfully bully someone"""
    embed = create_aesthetic_embed("😈 Bully", f"║ **{ctx.author.display_name}** playfully bullies **{member.display_name}**! ║", discord.Color.orange())
    await ctx.send(embed=embed)

@bot.command()
async def protect(ctx, member: discord.Member):
    """Protect someone"""
    embed = create_aesthetic_embed("🛡️ Protect", f"║ **{ctx.author.display_name}** protects **{member.display_name}**! ║", discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command()
async def feed(ctx, member: discord.Member):
    """Feed someone"""
    embed = create_aesthetic_embed("🍽️ Feed", f"║ **{ctx.author.display_name}** feeds **{member.display_name}**! ║", discord.Color.yellow())
    await ctx.send(embed=embed)

# More utility/fun commands
@bot.command()
async def dinosaur(ctx):
    """Make dinosaur sounds"""
    await ctx.send("rawr")

@bot.command()
async def flip(ctx):
    """Flip a table"""
    embed = create_aesthetic_embed("(╯°□°）╯︵ ┻━┻", "║ Table flipped in frustration! ║", discord.Color.red())
    await ctx.send(embed=embed)

@bot.command()
async def unflip(ctx):
    """Put the table back"""
    embed = create_aesthetic_embed("┬─┬ ノ( ゜-゜ノ)", "║ Table carefully placed back ║", discord.Color.green())
    await ctx.send(embed=embed)



@bot.command()
async def advice(ctx):
    """Get random life advice"""
    advice_list = [
        "💡 Believe in yourself and all that you are!",
        "🌟 Every accomplishment starts with the decision to try!",
        "💪 You are stronger than you think!",
        "🎯 Focus on progress, not perfection!",
        "🌈 After every storm comes a rainbow!",
        "⭐ You are capable of amazing things!",
        "🔥 Don't wait for opportunity, create it!",
        "💎 You are a diamond, they can't break you!"
    ]

    advice = random.choice(advice_list)
    embed = create_aesthetic_embed("💭 Life Advice", f"║ {advice} ║", discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command()
async def quote(ctx):
    """Get an inspirational quote"""
    quotes = [
        "💫 'The only way to do great work is to love what you do.' - Steve Jobs",
        "🚀 'Innovation distinguishes between a leader and a follower.' - Steve Jobs",
        "⭐ 'Life is what happens to you while you're busy making other plans.' - John Lennon",
        "💎 'The future belongs to those who believe in the beauty of their dreams.' - Eleanor Roosevelt",
        "🌟 'It is during our darkest moments that we must focus to see the light.' - Aristotle"
    ]

    quote = random.choice(quotes)
    embed = create_aesthetic_embed("📜 Inspirational Quote", f"║ {quote} ║", discord.Color.gold())
    await ctx.send(embed=embed)

@bot.command()
async def joke(ctx):
    """Get a random joke"""
    jokes = [
        "😂 Why don't scientists trust atoms? Because they make up everything!",
        "🤣 Why did the scarecrow win an award? He was outstanding in his field!",
        "😄 Why don't eggs tell jokes? They'd crack each other up!",
        "😆 What do you call a fake noodle? An impasta!",
        "🤪 Why did the math book look so sad? Because it had too many problems!"
    ]

    joke = random.choice(jokes)
    embed = create_aesthetic_embed("😂 Random Joke", f"║ {joke} ║", discord.Color.yellow())
    await ctx.send(embed=embed)

@bot.command()
async def fact(ctx):
    """Get a random fun fact"""
    facts = [
        "🐙 Octopuses have three hearts and blue blood!",
        "🦆 Ducks can sleep with one eye open!",
        "🍯 Honey never spoils - you can eat 1000-year-old honey!",
        "🐋 A whale's heart can weigh as much as a car!",
        "🌙 There are more possible games of chess than atoms in the universe!"
    ]

    fact = random.choice(facts)
    embed = create_aesthetic_embed("🧠 Fun Fact", f"║ {fact} ║", discord.Color.cyan())
    await ctx.send(embed=embed)

@bot.command()
async def weather(ctx, *, city="Unknown"):
    """Check the weather (placeholder)"""
    weather_types = ["☀️ Sunny", "🌧️ Rainy", "❄️ Snowy", "⛅ Cloudy", "🌈 Rainbow"]
    weather = random.choice(weather_types)
    temp = random.randint(10, 30)

    embed = create_aesthetic_embed("🌤️ Weather Report", f"║ **Location:** {city} ║\n║ **Condition:** {weather} ║\n║ **Temperature:** {temp}°C ║", discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command()
async def time(ctx):
    """Check current time"""
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    embed = create_aesthetic_embed("🕐 Current Time", f"║ **Time:** {current_time} UTC ║", discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    """Get detailed user information"""
    member = member or ctx.author
    user = await get_user_data(member.id)

    embed = create_aesthetic_embed(f"👤 {member.display_name}'s Info", "", discord.Color.blue(), member.display_avatar.url)
    embed.add_field(name="📅 Joined Discord", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="🏠 Joined Server", value=member.joined_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="🆔 User ID", value=member.id, inline=True)
    embed.add_field(name="💰 Balance", value=f"{user['balance']:,} 💵", inline=True)
    embed.add_field(name="📊 Level", value=user.get('level', 1), inline=True)
    embed.add_field(name="🏆 Rank", value=user.get('rank', 'Newbie'), inline=True)

    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    """Get server information"""
    guild = ctx.guild

    embed = create_aesthetic_embed(f"🏠 {guild.name}", "", discord.Color.blue())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(name="👥 Members", value=guild.member_count, inline=True)
    embed.add_field(name="📅 Created", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="👑 Owner", value=guild.owner.display_name if guild.owner else "Unknown", inline=True)
    embed.add_field(name="💬 Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="😀 Emojis", value=len(guild.emojis), inline=True)
    embed.add_field(name="🛡️ Verification", value=str(guild.verification_level).title(), inline=True)

    await ctx.send(embed=embed)

@bot.command()
async def crime(ctx):
    """Commit a crime for big rewards (or penalties) with enhanced visuals"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    # Check cooldown
    if user["last_crime"] and (now - user["last_crime"].replace(tzinfo=None)).seconds < 1800:
        remaining = 1800 - (now - user["last_crime"].replace(tzinfo=None)).seconds
        minutes = remaining // 60
        seconds = remaining % 60

        embed = create_aesthetic_embed("🕵️ Laying Low",
                                     f"║ You're hiding from authorities! Wait **{minutes}m {seconds}s** ║",
                                     discord.Color.orange())
        embed.add_field(name="🚨 Heat Level", value="🔥🔥🔥 **HIGH** 🔥🔥🔥", inline=True)
        embed.add_field(name="⏰ Cooldown", value="30 minutes", inline=True)
        return await ctx.send(embed=embed)

    level = user.get("level", 1)
    level_bonus = calculate_level_bonus(level)
    success_rate = min(CRIME_SUCCESS_RATE + (level * 0.01), 0.85)  # Level increases success rate
    crime_range = calculate_crime_bonus(level)

    # Crime types with different risk/reward
    crime_types = [
        {"name": "🏦 Bank Heist", "emoji": "🏦", "multiplier": 2.0, "risk": "EXTREME"},
        {"name": "🎨 Art Gallery Theft", "emoji": "🎨", "multiplier": 1.8, "risk": "HIGH"},
        {"name": "💎 Jewelry Store Robbery", "emoji": "💎", "multiplier": 1.6, "risk": "HIGH"},
        {"name": "💻 Cybercrime Operation", "emoji": "💻", "multiplier": 1.4, "risk": "MEDIUM"},
        {"name": "🎰 Casino Fraud", "emoji": "🎰", "multiplier": 1.3, "risk": "MEDIUM"},
        {"name": "🚗 Luxury Car Theft", "emoji": "🚗", "multiplier": 1.2, "risk": "LOW"}
    ]

    selected_crime = random.choice(crime_types)

    if random.random() < success_rate:
        # Success
        base_amount = random.randint(*crime_range)
        crime_bonus = int(base_amount * selected_crime["multiplier"])
        total_amount = base_amount + level_bonus + crime_bonus
        new_balance = user["balance"] + total_amount

        await update_user_data(ctx.author.id, {
            "balance": new_balance,
            "last_crime": now
        })

        description = f"""
╔══════════════════════════════════╗
║        🦹 **CRIME SUCCESS** 🦹        ║
╠══════════════════════════════════╣
║ **Operation:** {selected_crime['name']}
║ **Risk Level:** {selected_crime['risk']}
║ **Base Reward:** {base_amount:,} 💵
║ **Crime Bonus:** {crime_bonus:,} 💵
║ **Level Bonus:** {level_bonus:,} 💵
║ **Total Earned:** {total_amount:,} 💵
║ **New Balance:** {new_balance:,} 💵
╚══════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Criminal Mastermind", description, discord.Color.green(), ctx.author.display_avatar.url)
        embed.add_field(name="🎯 Success Rate", value=f"{int(success_rate * 100)}%", inline=True)
        embed.add_field(name="📈 Level", value=f"**{level}** ⭐", inline=True)
        embed.add_field(name="🏆 Status", value="✅ **SUCCESSFUL**", inline=True)

    else:
        # Failure
        penalty = CRIME_FAIL_PENALTY + (level * 50)  # Higher level = higher penalty
        fail_scenarios = [
            {"text": "🚔 Caught by police during escape", "emoji": "🚔"},
            {"text": "🚨 Triggered advanced security system", "emoji": "🚨"},
            {"text": "🤝 Betrayed by your criminal partner", "emoji": "🤝"},
            {"text": "📱 Left evidence at the crime scene", "emoji": "📱"},
            {"text": "🎭 Cover blown by undercover cop", "emoji": "🎭"}
        ]

        fail_scenario = random.choice(fail_scenarios)
        new_balance = max(0, user["balance"] - penalty)

        await update_user_data(ctx.author.id, {
            "balance": new_balance,
            "last_crime": now
        })

        description = f"""
╔══════════════════════════════════╗
║         ❌ **CRIME FAILED** ❌         ║
╠══════════════════════════════════╣
║ **Operation:** {selected_crime['name']}
║ **Failure:** {fail_scenario['text']}
║ **Penalty:** -{penalty:,} 💵
║ **New Balance:** {new_balance:,} 💵
╚══════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Crime Scene Investigation", description, discord.Color.red(), ctx.author.display_avatar.url)
        embed.add_field(name="🚨 Wanted Level", value="🔥🔥🔥 **HIGH** 🔥🔥🔥", inline=True)
        embed.add_field(name="⚖️ Justice", value="**SERVED**", inline=True)
        embed.add_field(name="🏥 Bail Cost", value=f"{penalty:,} 💵", inline=True)

    await ctx.send(embed=embed)

@bot.command()
async def ranks(ctx):
    """View all rank types, their conditions, and perks"""

    description = """
╔════════════════════════════════════╗
║       🏆 **RANK SYSTEM** 🏆       ║
╠════════════════════════════════════╣
║ Three rank types available:
║ • Level Ranks (XP-based)
║ • Wealth Ranks (Money-based)
║ • Special Ranks (Owner-assigned)
╚════════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Complete Rank System", description, discord.Color.gold())

    # Level-based ranks
    level_ranks_text = []
    for rank_name, rank_data in LEVEL_RANKS.items():
        level_ranks_text.append(
            f"{rank_data['emoji']} **{rank_name}** - Level {rank_data['threshold']}+\n"
            f"   └ *{rank_data['perks']}*"
        )

    embed.add_field(
        name="📊 Level Ranks (Automatic)",
        value="\n".join(level_ranks_text),
        inline=False
    )

    # Wealth-based ranks
    wealth_ranks_text = []
    for rank_name, rank_data in WEALTH_RANKS.items():
        wealth_ranks_text.append(
            f"{rank_data['emoji']} **{rank_name}** - {rank_data['threshold']:,}+ 💵\n"
            f"   └ *{rank_data['perks']}*"
        )

    embed.add_field(
        name="💰 Wealth Ranks (Automatic)",
        value="\n".join(wealth_ranks_text),
        inline=False
    )

    # Custom ranks (owner-assigned)
    custom_ranks_text = []
    for rank_name, rank_data in CUSTOM_RANKS.items():
        custom_ranks_text.append(
            f"{rank_data['emoji']} **{rank_name}**\n"
            f"   └ *{rank_data['perks']}*"
        )

    embed.add_field(
        name="👑 Special Ranks (Owner Only)",
        value="\n".join(custom_ranks_text),
        inline=False
    )

    embed.add_field(
        name="📌 How It Works",
        value="• **Level Ranks:** Earn XP to level up automatically\n"
              "• **Wealth Ranks:** Earn money to rank up automatically\n"
              "• **Special Ranks:** Only the bot owner can assign these\n"
              "• All ranks shown in `owo profile`",
        inline=False
    )

    embed.add_field(
        name="🎮 Quick Commands",
        value="`owo profile` - View your ranks\n"
              "`owo level` - Check level progress\n"
              "`owo balance` - Check wealth progress",
        inline=False
    )

    await ctx.send(embed=embed)

@bot.command()
async def animals(ctx):
    """View all huntable animals categorized by rarity"""
    # Organize animals by rarity
    rarity_categories = {
        "mythical": {"animals": [], "emoji": "🔴", "name": "Mythical Legends", "color": discord.Color.red()},
        "legendary": {"animals": [], "emoji": "🟡", "name": "Legendary Beasts", "color": discord.Color.gold()},
        "epic": {"animals": [], "emoji": "🟣", "name": "Epic Creatures", "color": discord.Color.purple()},
        "rare": {"animals": [], "emoji": "🔵", "name": "Rare Species", "color": discord.Color.blue()},
        "uncommon": {"animals": [], "emoji": "🟢", "name": "Uncommon Animals", "color": discord.Color.green()},
        "common": {"animals": [], "emoji": "⚪", "name": "Common Wildlife", "color": discord.Color.light_grey()}
    }

    # Sort animals into categories
    for animal_name, animal_data in HUNT_ITEMS.items():
        rarity = animal_data.get("type", "common")
        if rarity in rarity_categories:
            rarity_categories[rarity]["animals"].append({
                "name": animal_name,
                "emoji": animal_data["emoji"],
                "value": animal_data["value"],
                "rarity_chance": animal_data["rarity"]
            })

    # Sort animals within each category by value (highest first)
    for category in rarity_categories.values():
        category["animals"].sort(key=lambda x: x["value"], reverse=True)

    # Calculate total animals and statistics
    total_animals = len(HUNT_ITEMS)
    total_value = sum(animal["value"] for animal in HUNT_ITEMS.values())

    description = f"""
╔════════════════════════════════════╗
║       🏹 **HUNTABLE ANIMALS** 🏹       ║
╠════════════════════════════════════╣
║ **Total Species:** {total_animals}
║ **Combined Value:** {total_value:,} 💵
║ **Hunting Success:** Level dependent
║ **Collection Status:** Ready to hunt!
╚════════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Wildlife Encyclopedia", description, discord.Color.green())

    # Add each rarity category
    for rarity, category_data in rarity_categories.items():
        if category_data["animals"]:
            animal_list = []
            category_count = len(category_data["animals"])

            for animal in category_data["animals"]:
                # Show rarity percentage
                rarity_percent = f"{animal['rarity_chance']*100:.3f}%"
                animal_list.append(f"{animal['emoji']} **{animal['name'].title()}** - {animal['value']:,} 💵 ({rarity_percent})")

            field_name = f"{category_data['emoji']} {category_data['name']} ({category_count} species)"
            field_value = "\n".join(animal_list)

            # Limit field value to Discord's character limit
            if len(field_value) > 1024:
                # Show first few animals and indicate there are more
                shown_animals = []
                char_count = 0
                for animal_text in animal_list:
                    if char_count + len(animal_text) + 1 < 950:  # Leave room for "..."
                        shown_animals.append(animal_text)
                        char_count += len(animal_text) + 1
                    else:
                        break

                remaining = len(animal_list) - len(shown_animals)
                field_value = "\n".join(shown_animals)
                if remaining > 0:
                    field_value += f"\n... and {remaining} more {rarity} animals"

            embed.add_field(name=field_name, value=field_value, inline=False)

    # Add hunting tips and statistics
    embed.add_field(name="🎯 Hunting Tips",
                   value="• Higher levels increase rare animal chances\n"
                         "• Some hunting locations give bonus chances\n"
                         "• Multiple animals can be caught per hunt\n"
                         "• Rarity affects both value and catch rate",
                   inline=True)

    embed.add_field(name="📊 Rarity Statistics",
                   value=f"🔴 Mythical: {len(rarity_categories['mythical']['animals'])} species\n"
                         f"🟡 Legendary: {len(rarity_categories['legendary']['animals'])} species\n"
                         f"🟣 Epic: {len(rarity_categories['epic']['animals'])} species\n"
                         f"🔵 Rare: {len(rarity_categories['rare']['animals'])} species\n"
                         f"🟢 Uncommon: {len(rarity_categories['uncommon']['animals'])} species\n"
                         f"⚪ Common: {len(rarity_categories['common']['animals'])} species",
                   inline=True)

    embed.add_field(name="🎮 Quick Actions",
                   value="`owo hunt` - Start hunting\n"
                         "`owo zoo` - View your collection\n"
                         "`owo sell <animal>` - Sell animals",
                   inline=True)

    embed.set_footer(text="🌟 Percentages shown are base catch rates. Higher levels improve your chances!")

    await ctx.send(embed=embed)

@bot.command()
async def help(ctx, command: str = None):
    """Show all commands or help for a specific command"""
    if command:
        cmd = bot.get_command(command.lower())
        if not cmd:
            embed = create_aesthetic_embed("❌ Command Not Found",
                                         f"Command '{command}' doesn't exist!",
                                         discord.Color.red())
            return await ctx.send(embed=embed)

        embed = create_aesthetic_embed(f"owo {cmd.name}",
                                     cmd.help or "No description available",
                                     discord.Color.blue())
        return await ctx.send(embed=embed)

    embed = create_aesthetic_embed("🎯 Advanced OwO Bot Commands",
                                 "**Better than the original OwO bot!**\n"
                                 f"Total Commands: **{len(bot.commands)}**\n"
                                 "Use `owo help <command>` for detailed info",
                                 discord.Color.purple())

    categories = {
        "💰 Economy": ["balance", "daily", "work", "crime", "hunt", "fish", "sell", "give", "top", "weekly", "monthly", "beg", "dig", "explore"],
        "🛍️ Shop": ["shop"],
        "🎮 Gambling": ["slots", "coinflip", "blackjack", "hit", "stand", "spin", "race", "duel"],
        "🔫 Crime": ["steal", "rob", "crime"],
        "❤️ Social Actions": ["hug", "kiss", "slap", "cuddle", "pat", "poke", "punch", "bite", "tickle", "wave", "boop", "snuggle", "handhold", "greet", "bully", "protect", "feed", "fuck", "kick", "highfive"],
        "💍 Marriage": ["marry", "propose", "acceptmarriage", "declinemarriage", "divorce"],
        "📊 Profile": ["profile", "setbio", "inventory", "level", "avatar", "ship", "leaderboard", "userinfo", "serverinfo", "zoo", "animals", "ranks"],
        "😊 Emotes": ["blush", "cry", "dance", "happy", "pout", "smile", "wag", "thinking", "grin", "shrug"],
        "🎉 Fun & Games": ["meme", "cat", "dog", "eightball", "roll", "choose", "gif", "dinosaur", "flip", "unflip", "advice", "quote", "joke", "fact", "weather", "time", "truthordare", "roast", "compliment"],
        "🎯 Adventure": ["trivia", "riddle", "quest"],
        "🔬 Mathematics": ["math", "calculate", "solve", "stats", "convert", "derivative", "integral", "limit", "series", "mathhelp"],
        "🔧 Utility": ["ping", "invite", "botstats", "dashboard", "help"]
    }

    for category, commands in categories.items():
        embed.add_field(name=category,
                        value=" • ".join(f"`{cmd}`" for cmd in commands),
                        inline=False)

    embed.set_footer(text="✨ This bot has more features than the original OwO bot!")
    await ctx.send(embed=embed)

# Dashboard command
@bot.command()
async def dashboard(ctx):
    """Get the dashboard link"""
    dashboard_url = "https://myowobot.onrender.com"

    embed = create_aesthetic_embed("🖥️ Dashboard Access",
                                 "║ **Premium Bot Dashboard** ║\n\n"
                                 f"🔗 **Dashboard URL:** {dashboard_url}\n"
                                 "📊 **Features:** Real-time stats, user management, server overview\n"
                                 "🎨 **Design:** Premium glassmorphism aesthetic\n"
                                 "⚡ **Updates:** Live data refresh every 30 seconds\n\n"
                                 "Access your bot's advanced control panel with beautiful visualizations!",
                                 discord.Color.purple())
    embed.add_field(name="🌟 Dashboard Features",
                   value="• Real-time statistics\n• User management\n• Server overview\n• Activity tracking\n• Premium design",
                   inline=True)
    embed.add_field(name="📱 Responsive Design",
                   value="• Mobile friendly\n• Glassmorphism UI\n• Smooth animations\n• Interactive charts",
                   inline=True)
    embed.add_field(name="🔧 Quick Actions",
                   value="• Export data\n• Refresh stats\n• View logs\n• Invite bot",
                   inline=True)
    await ctx.send(embed=embed)

# Event handlers
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} servers')
    print(f'Total commands: {len(bot.commands)}')

    # Store bot start time for uptime calculation
    bot.start_time = datetime.datetime.now()

    # Start dashboard server
    try:
        import dashboard
        dashboard.start_dashboard()
        print("Dashboard and keep-alive server started on port 5000")
    except Exception as e:
        print(f"Failed to start dashboard: {e}")

    # Set status
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="owo help | Better than original OwO!")
    )

# Add bot ban check before processing commands
@bot.event
async def on_command(ctx):
    """Check if user is banned before processing commands"""
    if ctx.author.id != OWNER_ID:  # Owner can always use commands
        user_data = await get_user_data(ctx.author.id)
        if user_data.get("bot_banned", False):
            embed = create_aesthetic_embed("🚫 Banned",
                                         "║ You are banned from using this bot! ║",
                                         discord.Color.red())
            await ctx.send(embed=embed)
            return

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = create_aesthetic_embed("❌ Missing Argument",
                                     f"Missing required argument: **{error.param}**",
                                     discord.Color.red())
        await ctx.send(embed=embed)
    elif isinstance(error, commands.BadArgument):
        embed = create_aesthetic_embed("❌ Invalid Argument",
                                     "Please provide a valid argument!",
                                     discord.Color.red())
        await ctx.send(embed=embed)
    else:
        print(f"Error: {error}")

# Add remaining commands to reach 100+ (continuing existing commands with enhancements)
# [All other existing commands from the original code would be here with aesthetic improvements]

# Rankings
@bot.command()
async def top(ctx, category="balance"):
    """Show top users by balance, level, or xp"""
    if category.lower() in ["balance", "money", "cash"]:
        top_users = users.find().sort("balance", -1).limit(10)
        title = "💰 Top Richest Users"
        field_name = "Balance"
        emoji = "💵"
    elif category.lower() in ["level", "lvl"]:
        top_users = users.find().sort("level", -1).limit(10)
        title = "📊 Top Level Users"
        field_name = "Level"
        emoji = "⭐"
    elif category.lower() in ["xp", "experience"]:
        top_users = users.find().sort("xp", -1).limit(10)
        title = "⭐ Top XP Users"
        field_name = "XP"
        emoji = "✨"
    else:
        return await ctx.send("Valid categories: balance, level, xp")

    embed = discord.Embed(title=title, color=discord.Color.gold())

    ranking = []
    for i, user_data in enumerate(top_users, 1):
        try:
            user = await bot.fetch_user(user_data["_id"])
            if category.lower() in ["balance", "money", "cash"]:
                value = f"{user_data.get('balance', 0)} {emoji}"
            elif category.lower() in ["level", "lvl"]:
                value = f"{user_data.get('level', 1)} {emoji}"
            else:
                value = f"{user_data.get('xp', 0)} {emoji}"

            ranking.append(f"**{i}.** {user.display_name} - {value}")
        except:
            continue

    if ranking:
        embed.description = "\n".join(ranking)
    else:
        embed.description = "No users found!"

    await ctx.send(embed=embed)

# Animal commands
@bot.command()
async def hunt(ctx):
    """Hunt for multiple animals with enhanced visuals"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    if user["last_hunt"] and (now - user["last_hunt"].replace(tzinfo=None)).seconds < 2:
        remaining = 2 - (now - user["last_hunt"].replace(tzinfo=None)).seconds

        embed = create_aesthetic_embed("🏹 Bow Recharging",
                                     f"║ Your hunting equipment needs a quick rest! ║\n"
                                     f"║ Wait **{remaining}** seconds before hunting again ║",
                                     discord.Color.orange())
        embed.add_field(name="🎯 Hunter's Rest", value="⚡ Quick reload", inline=True)
        embed.add_field(name="⏰ Cooldown", value="2 seconds", inline=True)
        return await ctx.send(embed=embed)

    level = user.get("level", 1)

    # Determine number of animals caught based on level and luck
    base_catches = 1
    if level >= 50:
        max_catches = 5
    elif level >= 30:
        max_catches = 4
    elif level >= 15:
        max_catches = 3
    elif level >= 5:
        max_catches = 2
    else:
        max_catches = 2

    # Random number of catches (1 to max_catches)
    num_catches = random.randint(base_catches, max_catches)

    # Enhanced hunting scenarios
    hunt_scenarios = [
        {"name": "🌲 Forest Expedition", "emoji": "🌲", "bonus_chance": 0.1},
        {"name": "🏔️ Mountain Hunt", "emoji": "🏔️", "bonus_chance": 0.15},
        {"name": "🌊 Riverside Hunting", "emoji": "🌊", "bonus_chance": 0.12},
        {"name": "🌙 Moonlight Hunt", "emoji": "🌙", "bonus_chance": 0.20},
        {"name": "⚡ Lightning Hunt", "emoji": "⚡", "bonus_chance": 0.25}
    ]

    selected_scenario = random.choice(hunt_scenarios)

    caught_animals = []
    total_value = 0
    legendary_count = 0
    rare_count = 0

    for _ in range(num_catches):
        # Apply scenario bonus for rare catches
        bonus_multiplier = 1.0
        if random.random() < selected_scenario["bonus_chance"]:
            bonus_multiplier = 2.0  # Double chance for rare items

        # Use weighted random selection
        animals = list(HUNT_ITEMS.items())
        weights = [item_data["rarity"] * bonus_multiplier for _, item_data in animals]

        # Adjust weights for rarity selection
        selected_animal = random.choices(animals, weights=weights)[0]
        item_name, item_data = selected_animal

        await add_item(ctx.author.id, item_name)
        caught_animals.append((item_name, item_data))
        total_value += item_data["value"]

        # Count rarities
        if item_data["rarity"] <= 0.001:
            legendary_count += 1
        elif item_data["rarity"] <= 0.05:
            rare_count += 1

    await update_user_data(ctx.author.id, {"last_hunt": now})

    # Apply hunt multiplier to total value
    hunt_multiplier = await get_active_multiplier(ctx.author.id, "hunt")
    if hunt_multiplier > 1.0:
        total_value = int(total_value * hunt_multiplier)

    # Create enhanced hunt result display
    animals_display = []
    for item_name, item_data in caught_animals:
        rarity_indicator = ""
        if item_data["rarity"] <= 0.001:
            rarity_indicator = " ✨ **LEGENDARY** ✨"
        elif item_data["rarity"] <= 0.05:
            rarity_indicator = " 🌟 **RARE** 🌟"

        animals_display.append(f"{item_data['emoji']} **{item_name}**{rarity_indicator}")

    description = f"""
╔════════════════════════════════════╗
║        🏹 **HUNTING EXPEDITION** 🏹        ║
╠════════════════════════════════════╣
║ **Location:** {selected_scenario['name']}
║ **Animals Caught:** {num_catches}
║ **Total Value:** {total_value:,} 💵
║ **Hunter Level:** {level} ⭐
╠════════════════════════════════════╣
║ **CAUGHT ANIMALS:**
║ {chr(10).join('║ ' + animal for animal in animals_display)}
╚════════════════════════════════════╝
"""

    # Add shop effects info
    active_effects = []
    if await has_active_effect(ctx.author.id, "pocket_watch"):
        active_effects.append("⌚ Pocket Watch (+25% rare chance)")
    if await has_active_effect(ctx.author.id, "hunting_gear"):
        active_effects.append("🎯 Advanced Gear (+10% multi-catch)")
    if hunt_multiplier > 1.0:
        active_effects.append(f"🛍️ Value Multiplier (x{hunt_multiplier})")

    if active_effects:
        description += f"\n║ **Active Effects:** {', '.join(active_effects)}"

    # Determine embed color based on catches
    if legendary_count > 0:
        color = discord.Color.from_rgb(255, 215, 0)  # Gold for legendary
        achievement = "🎉 **LEGENDARY HUNTER!** 🎉"
    elif rare_count > 0:
        color = discord.Color.from_rgb(147, 112, 219)  # Purple for rare
        achievement = "⭐ **RARE HUNTER!** ⭐"
    elif num_catches >= 4:
        color = discord.Color.from_rgb(50, 205, 50)  # Green for multiple
        achievement = "🎯 **EXPERT HUNTER!** 🎯"
    else:
        color = discord.Color.from_rgb(30, 144, 255)  # Blue for normal
        achievement = "🏹 **SUCCESSFUL HUNT!** 🏹"

    embed = create_aesthetic_embed("Wild Game Hunter", description, color, ctx.author.display_avatar.url)
    embed.add_field(name="🏆 Achievement", value=achievement, inline=True)
    embed.add_field(name="📊 Success Rate", value="95% expedition success", inline=True)
    embed.add_field(name="🎁 Bonus Items", value=f"Level {level} Hunter Bonus", inline=True)

    # Add XP reward based on catches
    xp_gained = num_catches * 25 + (legendary_count * 100) + (rare_count * 50)
    leveled_up, new_level = await add_xp(ctx.author.id, xp_gained)

    if leveled_up:
        embed.add_field(name="🎊 LEVEL UP!", value=f"**Level {new_level}** achieved!", inline=False)

    # Set hunting GIF as thumbnail
    hunt_gifs = [
        "https://media.tenor.com/YQHzpBHswxcAAAAC/anime-bow.gif",
        "https://media.tenor.com/rK9Z_lXyJ_EAAAAC/anime-archer.gif",
        "https://media.tenor.com/gLnXKh7lD7QAAAAC/archery-anime.gif"
    ]
    embed.set_thumbnail(url=random.choice(hunt_gifs))

    await ctx.send(embed=embed)

@bot.command()
async def fish(ctx):
    """Go fishing and catch items"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    if user["last_fish"] and (now - user["last_fish"].replace(tzinfo=None)).seconds < 300:
        remaining = 300 - (now - user["last_fish"].replace(tzinfo=None)).seconds
        return await ctx.send(f"Your arms are tired! Try again in {remaining} seconds.")

    # Use rarity for random selection
    rand = random.random()
    cumulative = 0
    selected_item = None

    for item_name, item_data in FISH_ITEMS.items():
        cumulative += item_data["rarity"]
        if rand <= cumulative:
            selected_item = (item_name, item_data)
            break

    if not selected_item:
        selected_item = random.choice(list(FISH_ITEMS.items()))

    item_name, item_data = selected_item
    await add_item(ctx.author.id, item_name)
    await update_user_data(ctx.author.id, {"last_fish": now})

    rarity_text = ""
    if item_data["rarity"] <= 0.01:
        rarity_text = " ✨ **LEGENDARY!** ✨"
    elif item_data["rarity"] <= 0.05:
        rarity_text = " 🌟 **RARE!** 🌟"

    await ctx.send(f"🎣 You caught a {item_data['emoji']} **{item_name}**!{rarity_text}")

@bot.command()
async def zoo(ctx, member: discord.Member = None):
    """View your animal collection categorized by rarity"""
    member = member or ctx.author
    inventory = inventories.find_one({"_id": member.id})

    if not inventory or not inventory.get("items"):
        embed = create_aesthetic_embed("🏞️ Empty Zoo",
                                     f"║ {member.display_name}'s zoo is empty! ║\n"
                                     f"║ Use `owo hunt` to catch some animals! ║",
                                     discord.Color.orange())
        return await ctx.send(embed=embed)

    # Categorize animals by rarity
    categories = {
        "mythical": {"animals": [], "emoji": "🔴", "name": "Mythical Legends"},
        "legendary": {"animals": [], "emoji": "🟡", "name": "Legendary Beasts"},
        "epic": {"animals": [], "emoji": "🟣", "name": "Epic Creatures"},
        "rare": {"animals": [], "emoji": "🔵", "name": "Rare Species"},
        "uncommon": {"animals": [], "emoji": "🟢", "name": "Uncommon Animals"},
        "common": {"animals": [], "emoji": "⚪", "name": "Common Wildlife"},
        "aquatic": {"animals": [], "emoji": "🌊", "name": "Aquatic Life"}
    }

    total_animals = 0
    total_value = 0

    for item_name, quantity in inventory["items"].items():
        if item_name in HUNT_ITEMS:
            item_data = copy.deepcopy(HUNT_ITEMS[item_name])
            rarity = item_data.get("type", "common")
            value = item_data["value"] * quantity
            total_value += value
            total_animals += quantity

            categories[rarity]["animals"].append({
                "name": item_name,
                "emoji": item_data["emoji"],
                "quantity": quantity,
                "value": value
            })
        elif item_name in FISH_ITEMS:
            item_data = FISH_ITEMS[item_name]
            value = item_data["value"] * quantity
            total_value += value
            total_animals += quantity

            categories["aquatic"]["animals"].append({
                "name": item_name,
                "emoji": item_data["emoji"],
                "quantity": quantity,
                "value": value
            })

    if total_animals == 0:
        embed = create_aesthetic_embed("🏞️ Empty Zoo",
                                     f"║ {member.display_name} has no animals! ║",
                                     discord.Color.orange())
        return await ctx.send(embed=embed)

    # Create the zoo display
    description = f"""
╔════════════════════════════════════╗
║        🏞️ **{member.display_name.upper()}'S ZOO** 🏞️        ║
╠════════════════════════════════════╣
║ **Total Animals:** {total_animals}
║ **Total Collection Value:** {total_value:,} 💵
║ **Rarity Categories:** {sum(1 for cat in categories.values() if cat['animals'])}
╚════════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Wildlife Collection", description, discord.Color.green(), member.display_avatar.url)

    # Add each rarity category
    for rarity, category_data in categories.items():
        if category_data["animals"]:
            # Sort animals by value (highest first)
            sorted_animals = sorted(category_data["animals"], key=lambda x: x["value"], reverse=True)

            animal_list = []
            category_total = 0
            for animal in sorted_animals[:8]:  # Show max 8 animals per category
                animal_list.append(f"{animal['emoji']} **{animal['name'].title()}** x{animal['quantity']} ({animal['value']:,} 💵)")
                category_total += animal['quantity']

            if len(sorted_animals) > 8:
                remaining = len(sorted_animals) - 8
                animal_list.append(f"... and {remaining} more species")

            field_name = f"{category_data['emoji']} {category_data['name']} ({category_total} total)"
            field_value = "\n".join(animal_list)

            # Limit field value to Discord's character limit
            if len(field_value) > 1024:
                field_value = field_value[:1000] + "..."

            embed.add_field(name=field_name, value=field_value, inline=False)

    # Add collection stats
    embed.add_field(name="📊 Collection Stats",
                   value=f"🏆 Total Species: **{len([a for cat in categories.values() for a in cat['animals']])}**\n"
                         f"💰 Collection Worth: **{total_value:,}** 💵\n"
                         f"🎯 Completion: **{min(100, (total_animals * 2))}%**",
                   inline=True)

    embed.add_field(name="🎮 Quick Actions",
                   value="`owo hunt` - Catch more animals\n"
                         "`owo fish` - Catch aquatic life\n"
                         "`owo sell all` - Sell collection",
                   inline=True)

    await ctx.send(embed=embed)

# Shop System
SHOP_ITEMS = {
    # Boosts & Buffs
    "energy_drink": {
        "name": "Energy Drink",
        "emoji": "⚡",
        "price": 5000,
        "description": "Reduces all command cooldowns by 50% for 1 hour",
        "category": "boosts",
        "duration": 3600,  # 1 hour in seconds
        "daily_limit": 3
    },
    "pocket_watch": {
        "name": "Pocket Watch",
        "emoji": "⌚",
        "price": 8000,
        "description": "Increases hunt success rate for rare animals by 25% for 2 hours",
        "category": "boosts",
        "duration": 7200,  # 2 hours
        "daily_limit": 2
    },
    "xp_booster": {
        "name": "XP Booster",
        "emoji": "🚀",
        "price": 6000,
        "description": "Double XP gain from all activities for 1 hour",
        "category": "boosts",
        "duration": 3600,
        "daily_limit": 2
    },
    "crime_protection": {
        "name": "Crime Protection",
        "emoji": "🛡️",
        "price": 12000,
        "description": "Immunity from robbery and theft for 3 hours",
        "category": "boosts",
        "duration": 10800,  # 3 hours
        "daily_limit": 1
    },

    # Multipliers
    "daily_multiplier": {
        "name": "Daily Bonus Multiplier",
        "emoji": "💰",
        "price": 15000,
        "description": "1.5x daily reward for 24 hours",
        "category": "multipliers",
        "duration": 86400,  # 24 hours
        "daily_limit": 1
    },
    "work_multiplier": {
        "name": "Work Bonus Multiplier",
        "emoji": "💼",
        "price": 10000,
        "description": "1.3x work earnings for 12 hours",
        "category": "multipliers",
        "duration": 43200,  # 12 hours
        "daily_limit": 2
    },
    "hunt_multiplier": {
        "name": "Hunt Value Multiplier",
        "emoji": "🏹",
        "price": 18000,
        "description": "1.4x value from all hunted animals for 6 hours",
        "category": "multipliers",
        "duration": 21600,  # 6 hours
        "daily_limit": 1
    },

    # Practical Items
    "bank_vault": {
        "name": "Bank Vault Upgrade",
        "emoji": "🏦",
        "price": 50000,
        "description": "Protects 50% of your money from theft permanently",
        "category": "practical",
        "duration": -1,  # Permanent
        "daily_limit": 1
    },
    "fishing_rod": {
        "name": "Premium Fishing Rod",
        "emoji": "🎣",
        "price": 25000,
        "description": "Increases rare fish catch rate by 30% permanently",
        "category": "practical",
        "duration": -1,  # Permanent
        "daily_limit": 1
    },
    "hunting_gear": {
        "name": "Advanced Hunting Gear",
        "emoji": "🎯",
        "price": 35000,
        "description": "10% higher chance to catch multiple animals per hunt permanently",
        "category": "practical",
        "duration": -1,  # Permanent
        "daily_limit": 1
    }
}

# Track user shop purchases and active effects
user_shop_data = {}

async def get_user_shop_data(user_id):
    """Get user's shop data"""
    if user_id not in user_shop_data:
        user_shop_data[user_id] = {
            "daily_purchases": {},
            "active_effects": {},
            "permanent_items": [],
            "last_reset": datetime.datetime.now().date()
        }

    # Reset daily purchases if it's a new day
    today = datetime.datetime.now().date()
    if user_shop_data[user_id]["last_reset"] != today:
        user_shop_data[user_id]["daily_purchases"] = {}
        user_shop_data[user_id]["last_reset"] = today

    return user_shop_data[user_id]

async def check_daily_limit(user_id, item_id):
    """Check if user can still buy this item today"""
    shop_data = await get_user_shop_data(user_id)
    item = SHOP_ITEMS[item_id]

    purchased_today = shop_data["daily_purchases"].get(item_id, 0)
    return purchased_today < item["daily_limit"]

async def add_shop_effect(user_id, item_id):
    """Add an active effect to user"""
    shop_data = await get_user_shop_data(user_id)
    item = SHOP_ITEMS[item_id]

    if item["duration"] == -1:  # Permanent item
        if item_id not in shop_data["permanent_items"]:
            shop_data["permanent_items"].append(item_id)
    else:  # Temporary effect
        end_time = datetime.datetime.now() + datetime.timedelta(seconds=item["duration"])
        shop_data["active_effects"][item_id] = end_time

async def has_active_effect(user_id, effect_name):
    """Check if user has an active effect"""
    shop_data = await get_user_shop_data(user_id)
    now = datetime.datetime.now()

    # Check temporary effects
    if effect_name in shop_data["active_effects"]:
        if shop_data["active_effects"][effect_name] > now:
            return True
        else:
            # Effect expired, remove it
            del shop_data["active_effects"][effect_name]

    # Check permanent items
    return effect_name in shop_data["permanent_items"]

async def get_active_multiplier(user_id, multiplier_type):
    """Get active multiplier value for a specific type"""
    multiplier = 1.0

    if multiplier_type == "daily" and await has_active_effect(user_id, "daily_multiplier"):
        multiplier = 1.5
    elif multiplier_type == "work" and await has_active_effect(user_id, "work_multiplier"):
        multiplier = 1.3
    elif multiplier_type == "hunt" and await has_active_effect(user_id, "hunt_multiplier"):
        multiplier = 1.4

    return multiplier

@bot.command()
async def shop(ctx, action="view", *, item_name=""):
    """Browse and buy items from the shop"""
    user = await get_user_data(ctx.author.id)

    if action.lower() == "view" or not action:
        # Show shop categories
        categories = {
            "boosts": {"items": [], "emoji": "⚡", "name": "Boosts & Buffs"},
            "multipliers": {"items": [], "emoji": "📈", "name": "Multipliers"},
            "practical": {"items": [], "emoji": "🔧", "name": "Practical Items"}
        }

        # Organize items by category
        for item_id, item_data in SHOP_ITEMS.items():
            category = item_data["category"]
            if category in categories:
                categories[category]["items"].append((item_id, item_data))

        description = f"""
╔════════════════════════════════════╗
║          🛍️ **ITEM SHOP** 🛍️          ║
╠════════════════════════════════════╣
║ **Your Balance:** {user['balance']:,} 💵
║ **Daily Limits:** Reset every 24 hours
║ **Usage:** `owo shop buy <item_name>`
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Premium Shop", description, discord.Color.purple(), ctx.author.display_avatar.url)

        # Add each category
        for category_id, category_data in categories.items():
            if category_data["items"]:
                item_list = []
                for item_id, item_data in category_data["items"]:
                    can_buy = await check_daily_limit(ctx.author.id, item_id)
                    status = "✅" if can_buy else "❌"

                    duration_text = ""
                    if item_data["duration"] == -1:
                        duration_text = " (Permanent)"
                    else:
                        hours = item_data["duration"] // 3600
                        duration_text = f" ({hours}h)"

                    item_list.append(f"{status} {item_data['emoji']} **{item_data['name']}** - {item_data['price']:,} 💵{duration_text}")
                    item_list.append(f"   └ {item_data['description']}")
                    item_list.append(f"   └ Daily Limit: {item_data['daily_limit']}")
                    item_list.append("")

                field_name = f"{category_data['emoji']} {category_data['name']}"
                field_value = "\n".join(item_list[:1000])  # Discord limit

                embed.add_field(name=field_name, value=field_value, inline=False)

        embed.add_field(name="🛒 How to Buy",
                       value="`owo shop buy energy_drink`\n`owo shop buy pocket_watch`\n`owo shop effects` - View active items",
                       inline=True)

        await ctx.send(embed=embed)

    elif action.lower() == "buy":
        if not item_name:
            embed = create_aesthetic_embed("❌ Missing Item",
                                         "║ Please specify an item to buy! ║\n"
                                         "║ Use `owo shop` to see available items ║",
                                         discord.Color.red())
            return await ctx.send(embed=embed)

        # Find item (case insensitive, partial match)
        item_id = None
        item_data = None

        for shop_item_id, shop_item_data in SHOP_ITEMS.items():
            if (item_name.lower() in shop_item_id.lower() or
                item_name.lower() in shop_item_data["name"].lower()):
                item_id = shop_item_id
                item_data = shop_item_data
                break

        if not item_id:
            embed = create_aesthetic_embed("❌ Item Not Found",
                                         f"║ '{item_name}' not found in shop! ║\n"
                                         f"║ Use `owo shop` to see available items ║",
                                         discord.Color.red())
            return await ctx.send(embed=embed)

        # Check if user can afford it
        if user["balance"] < item_data["price"]:
            embed = create_aesthetic_embed("💸 Insufficient Funds",
                                         f"║ **{item_data['name']}** costs **{item_data['price']:,}** 💵 ║\n"
                                         f"║ You only have **{user['balance']:,}** 💵 ║",
                                         discord.Color.red())
            return await ctx.send(embed=embed)

        # Check daily limit
        if not await check_daily_limit(ctx.author.id, item_id):
            shop_data = await get_user_shop_data(ctx.author.id)
            purchased_today = shop_data["daily_purchases"].get(item_id, 0)

            embed = create_aesthetic_embed("🚫 Daily Limit Reached",
                                         f"║ **{item_data['name']}** daily limit: {item_data['daily_limit']} ║\n"
                                         f"║ You've already bought: {purchased_today} today ║\n"
                                         f"║ Limits reset every 24 hours ║",
                                         discord.Color.orange())
            return await ctx.send(embed=embed)

        # Check if they already have this permanent item
        if item_data["duration"] == -1 and await has_active_effect(ctx.author.id, item_id):
            embed = create_aesthetic_embed("⚠️ Already Owned",
                                         f"║ You already own **{item_data['name']}**! ║\n"
                                         f"║ Permanent items can only be bought once ║",
                                         discord.Color.orange())
            return await ctx.send(embed=embed)

        # Process purchase
        new_balance = user["balance"] - item_data["price"]
        await update_user_data(ctx.author.id, {"balance": new_balance})

        # Add to daily purchases
        shop_data = await get_user_shop_data(ctx.author.id)
        shop_data["daily_purchases"][item_id] = shop_data["daily_purchases"].get(item_id, 0) + 1

        # Add effect
        await add_shop_effect(ctx.author.id, item_id)

        # Create purchase confirmation
        duration_text = ""
        if item_data["duration"] == -1:
            duration_text = "Permanent upgrade!"
            status_emoji = "♾️"
        else:
            hours = item_data["duration"] // 3600
            minutes = (item_data["duration"] % 3600) // 60
            duration_text = f"Active for {hours}h {minutes}m"
            status_emoji = "⏰"

        description = f"""
╔════════════════════════════════════╗
║        🛒 **PURCHASE COMPLETE** 🛒        ║
╠════════════════════════════════════╣
║ **Item:** {item_data['emoji']} **{item_data['name']}**
║ **Price:** {item_data['price']:,} 💵
║ **Effect:** {item_data['description']}
║ **Duration:** {status_emoji} {duration_text}
║ **New Balance:** {new_balance:,} 💵
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Successful Purchase", description, discord.Color.green(), ctx.author.display_avatar.url)
        embed.add_field(name="🎯 Status", value="**ACTIVE** ✅", inline=True)
        embed.add_field(name="📊 Remaining Today",
                       value=f"{item_data['daily_limit'] - shop_data['daily_purchases'][item_id]}",
                       inline=True)
        embed.add_field(name="💡 Tip", value="Use `owo shop effects` to see active items!", inline=True)

        await ctx.send(embed=embed)

    elif action.lower() == "effects":
        # Show user's active effects
        shop_data = await get_user_shop_data(ctx.author.id)
        now = datetime.datetime.now()

        active_effects = []
        permanent_items = []

        # Check temporary effects
        for effect_id, end_time in shop_data["active_effects"].copy().items():
            if end_time > now:
                item_data = SHOP_ITEMS[effect_id]
                remaining = end_time - now
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60

                active_effects.append(f"{item_data['emoji']} **{item_data['name']}** - {hours}h {minutes}m left")
            else:
                # Remove expired effect
                del shop_data["active_effects"][effect_id]

        # Check permanent items
        for item_id in shop_data["permanent_items"]:
            if item_id in SHOP_ITEMS:
                item_data = SHOP_ITEMS[item_id]
                permanent_items.append(f"{item_data['emoji']} **{item_data['name']}** - Permanent")

        if not active_effects and not permanent_items:
            embed = create_aesthetic_embed("📦 No Active Effects",
                                         "║ You don't have any active shop items! ║\n"
                                         "║ Use `owo shop` to browse available items ║",
                                         discord.Color.orange())
            return await ctx.send(embed=embed)

        description = f"""
╔════════════════════════════════════╗
║       ✨ **ACTIVE EFFECTS** ✨       ║
╠════════════════════════════════════╣
║ **Temporary Effects:** {len(active_effects)}
║ **Permanent Items:** {len(permanent_items)}
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Your Active Items", description, discord.Color.blue(), ctx.author.display_avatar.url)

        if active_effects:
            embed.add_field(name="⏰ Temporary Effects",
                           value="\n".join(active_effects) or "None",
                           inline=False)

        if permanent_items:
            embed.add_field(name="♾️ Permanent Items",
                           value="\n".join(permanent_items) or "None",
                           inline=False)

        embed.add_field(name="🔄 Auto-Refresh",
                       value="Effects are automatically applied to your commands!",
                       inline=True)

        await ctx.send(embed=embed)

    else:
        embed = create_aesthetic_embed("❌ Invalid Action",
                                     "║ Valid actions: view, buy, effects ║\n"
                                     "║ Example: `owo shop buy energy_drink` ║",
                                     discord.Color.red())
        await ctx.send(embed=embed)

# More economy commands


@bot.command()
async def give(ctx, member: discord.Member, amount: int):
    """Give money to another user"""
    if member == ctx.author:
        return await ctx.send("You can't give money to yourself!")

    if amount <= 0:
        return await ctx.send("Amount must be positive!")

    user = await get_user_data(ctx.author.id)
    if user["balance"] < amount:
        return await ctx.send("You don't have enough money!")

    await update_user_data(ctx.author.id, {"balance": user["balance"] - amount})

    recipient = await get_user_data(member.id)
    await update_user_data(member.id, {"balance": recipient["balance"] + amount})

    await ctx.send(f"💸 {ctx.author.display_name} gave {amount} 💵 to {member.display_name}!")

# Inventory commands
@bot.command()
async def inventory(ctx, member: discord.Member = None):
    """View your or someone else's inventory"""
    member = member or ctx.author
    inventory = inventories.find_one({"_id": member.id})

    if not inventory or not inventory.get("items"):
        return await ctx.send(f"{member.display_name}'s inventory is empty!")

    items = []
    for item_name, quantity in inventory["items"].items():
        if item_name in HUNT_ITEMS:
            items.append(f"{HUNT_ITEMS[item_name]['emoji']} {item_name} x{quantity}")
        elif item_name in FISH_ITEMS:
            items.append(f"{FISH_ITEMS[item_name]['emoji']} {item_name} x{quantity}")
        else:
            items.append(f"❓ {item_name} x{quantity}")

    embed = discord.Embed(title=f"{member.display_name}'s Inventory",
                          description="\n".join(items) if items else "Empty",
                          color=discord.Color.green())
    await ctx.send(embed=embed)

@bot.command()
async def sell(ctx, *, args=""):
    """Sell items from your inventory with enhanced market system"""
    if not args:
        # Show sellable items
        inventory = inventories.find_one({"_id": ctx.author.id})
        if not inventory or not inventory.get("items"):
            embed = create_aesthetic_embed("📦 Empty Inventory",
                                         "║ You have no items to sell! ║",
                                         discord.Color.orange())
            return await ctx.send(embed=embed)

        sellable_items = []
        total_value = 0

        for item_name, quantity in inventory["items"].items():
            if item_name in HUNT_ITEMS:
                item_data = HUNT_ITEMS[item_name]
                value = item_data["value"] * quantity
                rarity_emoji = {
                    "common": "⚪",
                    "uncommon": "🟢",
                    "rare": "🔵",
                    "epic": "🟣",
                    "legendary": "🟡",
                    "mythical": "🔴"
                }.get(item_data["type"], "⚪")

                sellable_items.append(f"{rarity_emoji} {item_data['emoji']} **{item_name}** x{quantity} - {value:,} 💵")
                total_value += value
            elif item_name in FISH_ITEMS:
                item_data = FISH_ITEMS[item_name]
                value = item_data["value"] * quantity
                sellable_items.append(f"🌊 {item_data['emoji']} **{item_name}** x{quantity} - {value:,} 💵")
                total_value += value

        if not sellable_items:
            embed = create_aesthetic_embed("📦 No Sellable Items",
                                         "║ You have no items that can be sold! ║",
                                         discord.Color.orange())
            return await ctx.send(embed=embed)

        description = f"""
╔════════════════════════════════════╗
║        🏪 **MARKETPLACE** 🏪        ║
╠════════════════════════════════════╣
║ **Total Inventory Value:** {total_value:,} 💵
║
║ **SELLABLE ITEMS:**
║ {chr(10).join('║ ' + item for item in sellable_items[:15])}
╚════════════════════════════════════╝

**Usage:** `owo sell <item> [amount]` or `owo sell all`
"""

        embed = create_aesthetic_embed("Market Inventory", description, discord.Color.green(), ctx.author.display_avatar.url)
        embed.add_field(name="💰 Quick Actions", value="`owo sell all` - Sell everything", inline=True)
        embed.add_field(name="📈 Market Status", value="**🟢 STABLE**", inline=True)
        embed.add_field(name="🔄 Refresh Rate", value="Real-time pricing", inline=True)
        return await ctx.send(embed=embed)

    # Parse arguments
    parts = args.split()
    if parts[0].lower() == "all":
        # Sell all items
        inventory = inventories.find_one({"_id": ctx.author.id})
        if not inventory or not inventory.get("items"):
            embed = create_aesthetic_embed("📦 Empty Inventory",
                                         "║ You have no items to sell! ║",
                                         discord.Color.orange())
            return await ctx.send(embed=embed)

        total_value = 0
        sold_items = []

        for item_name, quantity in inventory["items"].copy().items():
            if item_name in HUNT_ITEMS:
                value = HUNT_ITEMS[item_name]["value"] * quantity
                total_value += value
                sold_items.append(f"{HUNT_ITEMS[item_name]['emoji']} {item_name} x{quantity}")
                await remove_item(ctx.author.id, item_name, quantity)
            elif item_name in FISH_ITEMS:
                value = FISH_ITEMS[item_name]["value"] * quantity
                total_value += value
                sold_items.append(f"{FISH_ITEMS[item_name]['emoji']} {item_name} x{quantity}")
                await remove_item(ctx.author.id, item_name, quantity)

        if total_value == 0:
            embed = create_aesthetic_embed("📦 No Sellable Items",
                                         "║ You have no items that can be sold! ║",
                                         discord.Color.orange())
            return await ctx.send(embed=embed)

        user = await get_user_data(ctx.author.id)
        old_balance = user["balance"]
        new_balance = user["balance"] + total_value
        await update_user_data(ctx.author.id, {"balance": new_balance})

        description = f"""
╔════════════════════════════════════╗
║        💰 **BULK SALE** 💰        ║
╠════════════════════════════════════╣
║ **Items Sold:** {len(sold_items)}
║ **Total Earned:** {total_value:,} 💵
║ **Previous Balance:** {old_balance:,} 💵
║ **New Balance:** {new_balance:,} 💵
║ **Profit:** +{total_value:,} 💵
╠════════════════════════════════════╣
║ **SOLD ITEMS:**
║ {chr(10).join('║ ' + item for item in sold_items[:10])}
{f'║ ...and {len(sold_items) - 10} more items' if len(sold_items) > 10 else ''}
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Market Transaction Complete! ✅", description, discord.Color.gold(), ctx.author.display_avatar.url)
        embed.add_field(name="💎 Transaction Type", value="**BULK SALE**", inline=True)
        embed.add_field(name="📈 Market Impact", value="**POSITIVE**", inline=True)
        embed.add_field(name="🎯 Efficiency", value="**MAXIMUM**", inline=True)
        embed.set_footer(text="✅ All items sold successfully! Check your balance with 'owo balance'")
        return await ctx.send(embed=embed)

    else:
        # Sell specific item
        if len(parts) == 1:
            item_name = parts[0].lower()
            amount = 1
        elif len(parts) == 2:
            item_name = parts[0].lower()
            try:
                amount = int(parts[1])
            except ValueError:
                embed = create_aesthetic_embed("❌ Invalid Amount",
                                             "║ Please provide a valid number! ║",
                                             discord.Color.red())
                return await ctx.send(embed=embed)
        else:
            embed = create_aesthetic_embed("❌ Invalid Format",
                                         "║ Use: `owo sell <item> [amount]` ║",
                                         discord.Color.red())
            return await ctx.send(embed=embed)

        if amount <= 0:
            embed = create_aesthetic_embed("❌ Invalid Amount",
                                         "║ Amount must be positive! ║",
                                         discord.Color.red())
            return await ctx.send(embed=embed)

        user = await get_user_data(ctx.author.id)
        inventory = inventories.find_one({"_id": ctx.author.id})

        if not inventory or not inventory.get("items"):
            embed = create_aesthetic_embed("📦 Empty Inventory",
                                         "║ You have no items to sell! ║",
                                         discord.Color.orange())
            return await ctx.send(embed=embed)

        # Find the item with case-insensitive partial matching
        found_item = None
        item_data = None

        # Search in hunt items
        for hunt_item_name, hunt_item_data in HUNT_ITEMS.items():
            if (item_name.lower() in hunt_item_name.lower() or
                hunt_item_name.lower() == item_name.lower()):
                if hunt_item_name in inventory["items"] and inventory["items"][hunt_item_name] > 0:
                    found_item = hunt_item_name
                    item_data = hunt_item_data
                    item_data["type"] = hunt_item_data.get("type", "common")
                    break

        # Search in fish items if not found in hunt items
        if not found_item:
            for fish_item_name, fish_item_data in FISH_ITEMS.items():
                if (item_name.lower() in fish_item_name.lower() or
                    fish_item_name.lower() == item_name.lower()):
                    if fish_item_name in inventory["items"] and inventory["items"][fish_item_name] > 0:
                        found_item = fish_item_name
                        item_data = fish_item_data
                        item_data["type"] = "aquatic"
                        break

        if not found_item:
            embed = create_aesthetic_embed("❌ Item Not Found",
                                         f"║ You don't have any **{item_name}** to sell! ║\n"
                                         f"║ Check your inventory with `owo inventory` ║",
                                         discord.Color.red())
            return await ctx.send(embed=embed)

        if inventory["items"][found_item] < amount:
            embed = create_aesthetic_embed("❌ Insufficient Quantity",
                                         f"║ You only have **{inventory['items'][found_item]}** {found_item}(s)! ║",
                                         discord.Color.red())
            return await ctx.send(embed=embed)

        value_per_item = item_data["value"]
        emoji = item_data["emoji"]
        rarity = item_data["type"]
        total_value = value_per_item * amount
        old_balance = user["balance"]
        new_balance = user["balance"] + total_value

        # Process the sale FIRST
        await remove_item(ctx.author.id, found_item, amount)
        await update_user_data(ctx.author.id, {"balance": new_balance})

        # Determine rarity color and bonus
        rarity_colors = {
            "common": discord.Color.light_grey(),
            "uncommon": discord.Color.green(),
            "rare": discord.Color.blue(),
            "epic": discord.Color.purple(),
            "legendary": discord.Color.gold(),
            "mythical": discord.Color.red(),
            "aquatic": discord.Color.cyan()
        }

        rarity_emojis = {
            "common": "⚪",
            "uncommon": "🟢",
            "rare": "🔵",
            "epic": "🟣",
            "legendary": "🟡",
            "mythical": "🔴",
            "aquatic": "🌊"
        }

        color = rarity_colors.get(rarity, discord.Color.green())
        rarity_emoji = rarity_emojis.get(rarity, "⚪")

        description = f"""
╔════════════════════════════════════╗
║        🏪 **SALE COMPLETE** 🏪        ║
╠════════════════════════════════════╣
║ **Item:** {emoji} **{found_item.title()}**
║ **Rarity:** {rarity_emoji} **{rarity.title()}**
║ **Quantity Sold:** {amount}
║ **Price Each:** {value_per_item:,} 💵
║ **Total Earned:** {total_value:,} 💵
║ **Previous Balance:** {old_balance:,} 💵
║ **New Balance:** {new_balance:,} 💵
║ **Profit:** +{total_value:,} 💵
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("✅ Sale Successful!", description, color, ctx.author.display_avatar.url)
        embed.add_field(name="💰 Transaction ID", value=f"#{random.randint(100000, 999999)}", inline=True)
        embed.add_field(name="📈 Market Value", value=f"{value_per_item:,} 💵 each", inline=True)
        embed.add_field(name="⏰ Timestamp", value=f"<t:{int(datetime.datetime.now().timestamp())}:R>", inline=True)
        embed.set_footer(text=f"✅ Successfully sold {amount} {found_item}(s)! Money added to your balance.")

        return await ctx.send(embed=embed)

# Gambling commands
@bot.command()
async def slots(ctx, amount):
    """Play slots with your money"""
    user = await get_user_data(ctx.author.id)

    # Handle "all" bet
    if isinstance(amount, str) and amount.lower() == "all":
        if user["balance"] <= 0:
            embed = create_aesthetic_embed("💸 Empty Balance",
                                         "║ You have no money to bet! ║",
                                         discord.Color.red())
            return await ctx.send(embed=embed)
        amount = user["balance"]
    else:
        try:
            amount = int(amount)
        except (ValueError, TypeError):
            embed = create_aesthetic_embed("❌ Invalid Amount",
                                         "║ Use a number or 'all' to bet everything! ║",
                                         discord.Color.red())
            return await ctx.send(embed=embed)

    if amount <= 0:
        return await ctx.send("You must bet a positive amount!")

    if user["balance"] < amount:
        return await ctx.send("You don't have enough money!")

    emojis = ["🍎", "🍊", "🍇", "🍒", "🍋", "💰", "7️⃣"]
    slots = [random.choice(emojis) for _ in range(3)]

    if slots[0] == slots[1] == slots[2]:
        if slots[0] == "7️⃣":
            multiplier = 10
        elif slots[0] == "💰":
            multiplier = 5
        else:
            multiplier = 3
        winnings = amount * multiplier
        result = f"JACKPOT! You won {winnings} 💵 (x{multiplier})"
        color = discord.Color.gold()
    elif slots[0] == slots[1] or slots[1] == slots[2]:
        winnings = amount
        result = f"You won {winnings} 💵 (x1)"
        color = discord.Color.green()
    else:
        winnings = -amount
        result = f"You lost {amount} 💵"
        color = discord.Color.red()

    new_balance = user["balance"] + winnings
    await update_user_data(ctx.author.id, {"balance": new_balance})

    embed = create_aesthetic_embed("🎰 Slots", f"║ {' | '.join(slots)} 🎰\n{result} ║", color)
    await ctx.send(embed=embed)

@bot.command(aliases=['cf'])
async def coinflip(ctx, amount):
    """Flip a coin with enhanced visuals and 7-second cooldown"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    # Check for 7-second cooldown
    if user.get("last_coinflip") and (now - user["last_coinflip"].replace(tzinfo=None)).seconds < 7:
        remaining = 7 - (now - user["last_coinflip"].replace(tzinfo=None)).seconds
        embed = create_aesthetic_embed("⏰ Cooldown Active",
                                     f"║ Coin is still spinning! Wait **{remaining}** seconds ║",
                                     discord.Color.orange())
        return await ctx.send(embed=embed)

    # Handle "all" option
    if isinstance(amount, str) and amount.lower() == "all":
        if user["balance"] <= 0:
            embed = create_aesthetic_embed("💸 Empty Balance",
                                         "║ You have no money to bet! ║",
                                         discord.Color.red())
            return await ctx.send(embed=embed)
        amount = user["balance"]
    else:
        try:
            amount = int(amount)
        except (ValueError, TypeError):
            embed = create_aesthetic_embed("❌ Invalid Amount",
                                         "║ Use a number or 'all' to bet everything! ║",
                                         discord.Color.red())
            return await ctx.send(embed=embed)

    if amount <= 0:
        embed = create_aesthetic_embed("❌ Invalid Bet",
                                     "║ You must bet a positive amount! ║",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    if user["balance"] < amount:
        embed = create_aesthetic_embed("💸 Insufficient Funds",
                                     f"║ You need **{amount:,}** 💵 but only have **{user['balance']:,}** 💵 ║",
                                     discord.Color.red())
        return await ctx.send(embed=embed)

    # Random coin flip
    result = random.choice(["heads", "tails"])

    # Determine win/loss
    win = random.choice([True, False])  # 50/50 chance

    if win:
        winnings = amount
        new_balance = user["balance"] + winnings
        outcome_text = "🎉 **VICTORY!** 🎉"
        outcome_color = discord.Color.green()
        result_emoji = "✅"
    else:
        winnings = -amount
        new_balance = user["balance"] - amount
        outcome_text = "💔 **DEFEAT!** 💔"
        outcome_color = discord.Color.red()
        result_emoji = "❌"

    # Update user data
    await update_user_data(ctx.author.id, {
        "balance": new_balance,
        "last_coinflip": now
    })

    # Create enhanced embed
    # Check if this was an all-in bet
    was_all_in = amount == user["balance"]
    all_in_text = " (ALL-IN! 🎰)" if was_all_in else ""

    description = f"""
╔══════════════════════════════════╗
║           🪙 **COINFLIP** 🪙           ║
╠══════════════════════════════════╣
║ **Bet Amount:** {amount:,} 💵{all_in_text}
║ **Result:** {result.upper()}
║ **Outcome:** {outcome_text}
║ **Balance Change:** {winnings:+,} 💵
║ **New Balance:** {new_balance:,} 💵
╚══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Coin Flip Casino", description, outcome_color, ctx.author.display_avatar.url)

    # Add result visualization
    coin_animation = "🪙" if result == "heads" else "🥈"
    embed.add_field(name="🎰 Coin Result", value=f"{coin_animation} **{result.upper()}** {result_emoji}", inline=True)
    embed.add_field(name="📊 Win Rate", value="50% chance", inline=True)
    embed.add_field(name="⏰ Cooldown", value="7 seconds", inline=True)

    await ctx.send(embed=embed)



# Blackjack game (keeping existing implementation)
blackjack_games = {}

def calculate_hand_value(hand):
    value = 0
    aces = 0
    for card in hand:
        if card in ['J', 'Q', 'K']:
            value += 10
        elif card == 'A':
            aces += 1
            value += 11
        else:
            value += int(card)

    while value > 21 and aces > 0:
        value -= 10
        aces -= 1

    return value

def deal_card():
    cards = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
    return random.choice(cards)

@bot.command()
async def blackjack(ctx, amount: int):
    """Play blackjack"""
    user = await get_user_data(ctx.author.id)

    if amount <= 0:
        return await ctx.send("You must bet a positive amount!")

    if user["balance"] < amount:
        return await ctx.send("You don't have enough money!")

    if ctx.author.id in blackjack_games:
        return await ctx.send("You're already in a blackjack game! Use `owo hit` or `owo stand`")

    player_hand = [deal_card(), deal_card()]
    dealer_hand = [deal_card(), deal_card()]

    blackjack_games[ctx.author.id] = {
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "bet": amount,
        "finished": False
    }

    player_value = calculate_hand_value(player_hand)
    dealer_shown = dealer_hand[0]

    embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.gold())
    embed.add_field(name="Your Hand", value=f"{' '.join(player_hand)} (Value: {player_value})", inline=False)
    embed.add_field(name="Dealer's Hand", value=f"{dealer_shown} ?", inline=False)

    if player_value == 21:
        winnings = int(amount * 1.5)
        await update_user_data(ctx.author.id, {"balance": user["balance"] + winnings})
        del blackjack_games[ctx.author.id]
        embed.add_field(name="Result", value=f"BLACKJACK! You won {winnings} 💵!", inline=False)
    else:
        embed.add_field(name="Actions", value="Use `owo hit` or `owo stand`", inline=False)

    await ctx.send(embed=embed)

@bot.command()
async def hit(ctx):
    """Hit in blackjack"""
    if ctx.author.id not in blackjack_games:
        return await ctx.send("You're not in a blackjack game! Use `owo blackjack <amount>` to start")

    game = blackjack_games[ctx.author.id]
    if game["finished"]:
        return await ctx.send("This game is already finished!")

    card = deal_card()
    game["player_hand"].append(card)
    player_value = calculate_hand_value(game["player_hand"])

    embed = discord.Embed(title="🃏 Blackjack - Hit", color=discord.Color.gold())
    embed.add_field(name="Your Hand", value=f"{' '.join(game['player_hand'])} (Value: {player_value})", inline=False)
    embed.add_field(name="Dealer's Hand", value=f"{game['dealer_hand'][0]} ?", inline=False)

    if player_value > 21:
        user = await get_user_data(ctx.author.id)
        await update_user_data(ctx.author.id, {"balance": user["balance"] - game["bet"]})
        del blackjack_games[ctx.author.id]
        embed.add_field(name="Result", value=f"BUST! You lost {game['bet']} 💵!", inline=False)
    else:
        embed.add_field(name="Actions", value="Use `owo hit` or `owo stand`", inline=False)

    await ctx.send(embed=embed)

@bot.command()
async def stand(ctx):
    """Stand in blackjack"""
    if ctx.author.id not in blackjack_games:
        return await ctx.send("You're not in a blackjack game! Use `owo blackjack <amount>` to start")

    game = blackjack_games[ctx.author.id]
    if game["finished"]:
        return await ctx.send("This game is already finished!")

    while calculate_hand_value(game["dealer_hand"]) < 17:
        game["dealer_hand"].append(deal_card())

    player_value = calculate_hand_value(game["player_hand"])
    dealer_value = calculate_hand_value(game["dealer_hand"])

    embed = discord.Embed(title="🃏 Blackjack - Final", color=discord.Color.gold())
    embed.add_field(name="Your Hand", value=f"{' '.join(game['player_hand'])} (Value: {player_value})", inline=False)
    embed.add_field(name="Dealer's Hand", value=f"{' '.join(game['dealer_hand'])} (Value: {dealer_value})", inline=False)

    user = await get_user_data(ctx.author.id)

    if dealer_value > 21:
        winnings = game["bet"]
        result = f"Dealer bust! You won {winnings} 💵!"
        await update_user_data(ctx.author.id, {"balance": user["balance"] + winnings})
    elif player_value > dealer_value:
        winnings = game["bet"]
        result = f"You won {winnings} 💵!"
        await update_user_data(ctx.author.id, {"balance": user["balance"] + winnings})
    elif dealer_value > player_value:
        result = f"Dealer wins! You lost {game['bet']} 💵!"
        await update_user_data(ctx.author.id, {"balance": user["balance"] - game["bet"]})
    else:
        result = "It's a tie! Your bet is returned."

    embed.add_field(name="Result", value=result, inline=False)
    del blackjack_games[ctx.author.id]
    await ctx.send(embed=embed)

# Social commands
@bot.command()
async def highfive(ctx, member: discord.Member):
    """High five another user"""
    await ctx.send(f"{ctx.author.display_name} gives {member.display_name} a high five! ✋")

# Marriage system
@bot.command(aliases=['propose'])
async def marry(ctx, member: discord.Member):
    """Propose to another user"""
    if member == ctx.author:
        return await ctx.send("You can't marry yourself!")

    proposer = await get_user_data(ctx.author.id)
    proposee = await get_user_data(member.id)

    if proposer["married_to"]:
        return await ctx.send("You're already married!")
    if proposee["married_to"]:
        return await ctx.send(f"{member.display_name} is already married!")

    existing_proposal = marriages.find_one({
        "proposer": member.id,
        "proposee": ctx.author.id,
        "accepted": False
    })

    if existing_proposal:
        marriages.update_one({"_id": existing_proposal["_id"]}, {
            "$set": {"accepted": True, "married_at": datetime.datetime.now()}
        })
        await update_user_data(ctx.author.id, {"married_to": member.id})
        await update_user_data(member.id, {"married_to": ctx.author.id})
        return await ctx.send(f"💍 {ctx.author.display_name} has accepted {member.display_name}'s marriage proposal! They are now married! ❤️")

    marriages.insert_one({
        "proposer": ctx.author.id,
        "proposee": member.id,
        "accepted": False,
        "proposed_at": datetime.datetime.now()
    })

    await ctx.send(f"💍 {ctx.author.display_name} has proposed to {member.display_name}! Type `owo acceptmarriage {ctx.author.mention}` to accept!")

@bot.command()
async def acceptmarriage(ctx, member: discord.Member):
    """Accept a marriage proposal"""
    proposal = marriages.find_one({
        "proposer": member.id,
        "proposee": ctx.author.id,
        "accepted": False
    })

    if not proposal:
        return await ctx.send(f"You don't have a pending proposal from {member.display_name}!")

    marriages.update_one({"_id": proposal["_id"]}, {
        "$set": {"accepted": True, "married_at": datetime.datetime.now()}
    })

    await update_user_data(ctx.author.id, {"married_to": member.id})
    await update_user_data(member.id, {"married_to": ctx.author.id})

    await ctx.send(f"💍 {ctx.author.display_name} has accepted {member.display_name}'s marriage proposal! They are now married! ❤️")

@bot.command()
async def declinemarriage(ctx, member: discord.Member):
    """Decline a marriage proposal"""
    proposal = marriages.find_one({
        "proposer": member.id,
        "proposee": ctx.author.id,
        "accepted": False
    })

    if not proposal:
        return await ctx.send(f"You don't have a pending proposal from {member.display_name}!")

    marriages.delete_one({"_id": proposal["_id"]})
    await ctx.send(f"💔 {ctx.author.display_name} has declined {member.display_name}'s marriage proposal.")

@bot.command()
async def divorce(ctx):
    """Divorce your current spouse"""
    user = await get_user_data(ctx.author.id)

    if not user["married_to"]:
        return await ctx.send("You're not married!")

    spouse_id = user["married_to"]
    spouse = await bot.fetch_user(spouse_id)

    await update_user_data(ctx.author.id, {"married_to": None})
    await update_user_data(spouse_id, {"married_to": None})

    marriages.update_one({
        "$or": [
            {"proposer": ctx.author.id, "proposee": spouse_id},
            {"proposer": spouse_id, "proposee": ctx.author.id}
        ],
        "accepted": True
    }, {"$set": {"divorced_at": datetime.datetime.now()}})

    await ctx.send(f"💔 {ctx.author.display_name} has divorced {spouse.display_name}. It's a sad day...")

# Profile commands
@bot.command()
async def profile(ctx, member: discord.Member = None):
    """View your or someone else's profile with all rank types"""
    member = member or ctx.author
    user = await get_user_data(member.id)

    # Get all rank types
    level_rank = user.get('rank', 'Newbie')
    wealth_rank = get_wealth_rank(user['balance'])
    custom_rank = user.get('custom_rank')

    # Get rank emojis and colors
    level_rank_emoji = LEVEL_RANKS.get(level_rank, {}).get("emoji", "🌱")
    wealth_rank_data = WEALTH_RANKS.get(wealth_rank, {})
    wealth_rank_emoji = wealth_rank_data.get("emoji", "🪙")

    # Determine profile color based on highest rank
    if custom_rank and custom_rank in CUSTOM_RANKS:
        profile_color = discord.Color(CUSTOM_RANKS[custom_rank]["color"])
    else:
        profile_color = discord.Color(wealth_rank_data.get("color", 0x808080))

    description = f"""
╔════════════════════════════════════╗
║     💎 **PROFILE OVERVIEW** 💎     ║
╠════════════════════════════════════╣
║ **Balance:** {user['balance']:,} 💵
║ **Level:** {user.get('level', 1)} ⭐ | **XP:** {user.get('xp', 0):,}
║ **Daily Streak:** {user['daily_streak']} 🔥
╚════════════════════════════════════╝
"""

    embed = create_aesthetic_embed(f"{member.display_name}'s Profile", description, profile_color, member.display_avatar.url)

    # Level-based rank
    level_perks = LEVEL_RANKS.get(level_rank, {}).get("perks", "None")
    embed.add_field(
        name=f"{level_rank_emoji} Level Rank: {level_rank}",
        value=f"**Perks:** {level_perks}",
        inline=False
    )

    # Wealth-based rank
    wealth_perks = wealth_rank_data.get("perks", "None")
    next_wealth_rank = None
    for rank_name, rank_data in sorted(WEALTH_RANKS.items(), key=lambda x: x[1]["threshold"]):
        if rank_data["threshold"] > user['balance']:
            next_wealth_rank = f"{rank_name} ({rank_data['threshold']:,} 💵)"
            break

    wealth_field_value = f"**Perks:** {wealth_perks}"
    if next_wealth_rank:
        wealth_field_value += f"\n**Next:** {next_wealth_rank}"

    embed.add_field(
        name=f"{wealth_rank_emoji} Wealth Rank: {wealth_rank}",
        value=wealth_field_value,
        inline=False
    )

    # Custom rank (owner-assigned)
    if custom_rank and custom_rank in CUSTOM_RANKS:
        custom_rank_data = CUSTOM_RANKS[custom_rank]
        embed.add_field(
            name=f"{custom_rank_data['emoji']} Special Rank: {custom_rank}",
            value=f"**Perks:** {custom_rank_data['perks']}\n*Granted by bot owner*",
            inline=False
        )
    else:
        embed.add_field(
            name="👑 Special Rank",
            value="No special rank assigned\n*Ask the owner for a special rank!*",
            inline=False
        )

    # Calculate XP needed for next level
    current_level = user.get('level', 1)
    xp_needed = calculate_xp_for_level(current_level + 1) - user.get('xp', 0)

    # Progress stats
    embed.add_field(name="📈 Level Progress", value=f"{xp_needed:,} XP needed", inline=True)
    embed.add_field(name="💰 Wealth Progress", value=f"{wealth_rank} tier", inline=True)
    embed.add_field(name="🎯 Total Ranks", value="3 types", inline=True)

    if user["married_to"]:
        spouse = await bot.fetch_user(user["married_to"])
        embed.add_field(name="💍 Married to", value=spouse.display_name, inline=False)

    if user["bio"]:
        embed.add_field(name="📝 Bio", value=user["bio"], inline=False)

    await ctx.send(embed=embed)

@bot.command()
async def setbio(ctx, *, bio: str):
    """Set your profile bio"""
    if len(bio) > 200:
        return await ctx.send("Bio must be 200 characters or less!")

    await update_user_data(ctx.author.id, {"bio": bio})
    await ctx.send("✅ Your bio has been updated!")

@bot.command()
async def level(ctx, member: discord.Member = None):
    """Check your or someone's level"""
    member = member or ctx.author
    user = await get_user_data(member.id)

    level = user.get('level', 1)
    xp = user.get('xp', 0)
    rank = user.get('rank', 'Newbie')

    xp_needed = calculate_xp_for_level(level + 1) - xp

    embed = discord.Embed(title=f"{member.display_name}'s Level", color=discord.Color.blue())
    embed.add_field(name="📊 Level", value=level, inline=True)
    embed.add_field(name="⭐ XP", value=xp, inline=True)
    embed.add_field(name="🏆 Rank", value=rank, inline=True)
    embed.add_field(name="📈 XP to Next Level", value=xp_needed, inline=False)

    await ctx.send(embed=embed)

# Fun commands
@bot.command()
async def meme(ctx):
    """Get a random meme with reliable meme API"""

    # High-quality fallback memes with working image URLs
    fallback_memes = [
        {
            "title": "This is Fine",
            "url": "https://i.imgflip.com/1wz3as.jpg",
            "subreddit": "memes",
            "author": "KC Green",
            "ups": 9999
        },
        {
            "title": "Drake Pointing",
            "url": "https://i.imgflip.com/30b1gx.jpg",
            "subreddit": "dankmemes",
            "author": "Drake",
            "ups": 8888
        },
        {
            "title": "Distracted Boyfriend",
            "url": "https://i.imgflip.com/1ur9b0.jpg",
            "subreddit": "memes",
            "author": "Antonio Guillem",
            "ups": 7777
        },
        {
            "title": "Woman Yelling at Cat",
            "url": "https://i.imgflip.com/345v97.jpg",
            "subreddit": "dankmemes",
            "author": "Reality TV",
            "ups": 6666
        },
        {
            "title": "Two Buttons",
            "url": "https://i.imgflip.com/1g8my4.jpg",
            "subreddit": "memes",
            "author": "Jake Clark",
            "ups": 5555
        },
        {
            "title": "Change My Mind",
            "url": "https://i.imgflip.com/24y43o.jpg",
            "subreddit": "dankmemes",
            "author": "Steven Crowder",
            "ups": 4444
        },
        {
            "title": "Bernie I Am Once Again Asking",
            "url": "https://i.imgflip.com/37x3mp.jpg",
            "subreddit": "PoliticalHumor",
            "author": "Bernie Sanders",
            "ups": 3333
        },
        {
            "title": "Surprised Pikachu",
            "url": "https://i.imgflip.com/2kbn1e.jpg",
            "subreddit": "dankmemes",
            "author": "Pokemon",
            "ups": 2222
        }
    ]

    try:
        # Try the primary meme API
        async with aiohttp.ClientSession() as session:
            async with session.get("https://meme-api.com/gimme", timeout=8) as response:
                if response.status == 200:
                    data = await response.json()

                    # Validate the response data
                    if (isinstance(data, dict) and
                        "url" in data and
                        "title" in data and
                        "subreddit" in data and
                        data.get("nsfw", False) is False):  # Skip NSFW content

                        # Verify it's actually an image URL
                        image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp")
                        if data["url"].lower().endswith(image_extensions):

                            description = f"""
╔══════════════════════════════════╗
║         😂 **FRESH MEME** 😂         ║
╠══════════════════════════════════╣
║ **Title:** {data['title'][:45]}{'...' if len(data['title']) > 45 else ''}
║ **Source:** r/{data.get('subreddit', 'unknown')}
║ **Author:** u/{data.get('author', 'anonymous')}
║ **Quality:** Premium Internet Content
╚══════════════════════════════════╝
"""

                            embed = create_aesthetic_embed("Meme Central", description, discord.Color.random())
                            embed.set_image(url=data["url"])
                            embed.add_field(name="📊 Reddit Stats",
                                          value=f"👍 {data.get('ups', 'N/A'):,} upvotes",
                                          inline=True)
                            embed.add_field(name="🏷️ Category",
                                          value=f"r/{data.get('subreddit', 'memes')}",
                                          inline=True)
                            embed.add_field(name="🎭 Humor Level",
                                          value="**MAXIMUM** 😂",
                                          inline=True)
                            embed.add_field(name="🔗 Original Post",
                                          value=f"[View on Reddit]({data.get('postLink', '#')})",
                                          inline=False)

                            return await ctx.send(embed=embed)

        # If primary API fails, try alternative meme subreddit
        subreddits = ["memes", "dankmemes", "wholesomememes", "funny", "memeeconomy"]
        for subreddit in subreddits:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://meme-api.com/gimme/{subreddit}", timeout=6) as response:
                        if response.status == 200:
                            data = await response.json()

                            if (isinstance(data, dict) and
                                "url" in data and
                                "title" in data and
                                data.get("nsfw", False) is False):

                                image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp")
                                if data["url"].lower().endswith(image_extensions):

                                    description = f"""
╔══════════════════════════════════╗
║         🔥 **HOT MEME** 🔥         ║
╠══════════════════════════════════╣
║ **Title:** {data['title'][:45]}{'...' if len(data['title']) > 45 else ''}
║ **Source:** r/{subreddit}
║ **Quality:** Subreddit Special
╚══════════════════════════════════╝
"""

                                    embed = create_aesthetic_embed("Meme Central", description, discord.Color.orange())
                                    embed.set_image(url=data["url"])
                                    embed.add_field(name="📊 Stats",
                                                  value=f"👍 {data.get('ups', 0):,} upvotes",
                                                  inline=True)
                                    embed.add_field(name="🎯 Subreddit",
                                                  value=f"r/{subreddit}",
                                                  inline=True)
                                    embed.add_field(name="⚡ Freshness",
                                                  value="**JUST POSTED** 🆕",
                                                  inline=True)

                                    return await ctx.send(embed=embed)

            except Exception as e:
                print(f"Subreddit {subreddit} meme fetch failed: {e}")
                continue

        # If all APIs fail, use curated fallback memes
        fallback_meme = random.choice(fallback_memes)

        description = f"""
╔══════════════════════════════════╗
║       🏆 **CLASSIC MEME** 🏆       ║
╠══════════════════════════════════╣
║ **Title:** {fallback_meme['title']}
║ **Source:** r/{fallback_meme['subreddit']}
║ **Status:** Hall of Fame
║ **Reliability:** 100% Guaranteed
╚══════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Meme Vault", description, discord.Color.gold())
        embed.set_image(url=fallback_meme["url"])
        embed.add_field(name="📊 Legacy Stats",
                      value=f"👍 {fallback_meme['ups']:,} upvotes",
                      inline=True)
        embed.add_field(name="🏛️ Archive Status",
                      value="**HALL OF FAME** 🏆",
                      inline=True)
        embed.add_field(name="🎭 Humor Level",
                      value="**TIMELESS** ♾️",
                      inline=True)

        await ctx.send(embed=embed)

    except Exception as e:
        print(f"Meme command error: {e}")

        # Emergency fallback - guaranteed to work
        emergency_meme = random.choice(fallback_memes)

        embed = create_aesthetic_embed("🚨 Emergency Meme Supply",
                                     f"║ **{emergency_meme['title']}** ║\n"
                                     f"║ From the emergency meme vault! ║",
                                     discord.Color.from_rgb(255, 165, 0))
        embed.set_image(url=emergency_meme["url"])
        embed.add_field(name="🔧 Status", value="Emergency Protocol", inline=True)
        embed.add_field(name="⚡ Reliability", value="**GUARANTEED** ✅", inline=True)
        embed.add_field(name="😂 Quality", value="**PREMIUM** 💎", inline=True)

        await ctx.send(embed=embed)

@bot.command()
async def cat(ctx):
    """Get a random cat picture"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.thecatapi.com/v1/images/search") as response:
                if response.status == 200:
                    data = await response.json()
                    embed = discord.Embed(title="🐱 Random Cat", color=discord.Color.random())
                    embed.set_image(url=data[0]["url"])
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("Failed to fetch a cat picture. Try again later.")
    except Exception as e:
        print(f"Cat command error: {e}")
        await ctx.send("Failed to fetch a cat picture. Try again later.")

@bot.command()
async def dog(ctx):
    """Get a random dog picture"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://dog.ceo/api/breeds/image/random") as response:
                if response.status == 200:
                    data = await response.json()
                    embed = discord.Embed(title="🐶 Random Dog", color=discord.Color.random())
                    embed.set_image(url=data["message"])
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("Failed to fetch a dog picture. Try again later.")
    except Exception as e:
        print(f"Dog command error: {e}")
        await ctx.send("Failed to fetch a dog picture. Try again later.")

@bot.command()
async def eightball(ctx, *, question):
    """Ask the magic 8-ball a question"""
    responses = [
        "It is certain", "It is decidedly so", "Without a doubt", "Yes definitely",
        "You may rely on it", "As I see it, yes", "Most likely", "Outlook good",
        "Yes", "Signs point to yes", "Reply hazy, try again", "Ask again later",
        "Better not tell you now", "Cannot predict now", "Concentrate and ask again",
        "Don't count on it", "My reply is no", "My sources say no", "Outlook not so good",
        "Very doubtful"
    ]

    embed = discord.Embed(title="🎱 Magic 8-Ball", color=discord.Color.purple())
    embed.add_field(name="Question", value=question, inline=False)
    embed.add_field(name="Answer", value=random.choice(responses), inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def roll(ctx, sides: int = 6):
    """Roll a dice"""
    if sides < 2:
        return await ctx.send("Dice must have at least 2 sides!")

    result = random.randint(1, sides)
    await ctx.send(f"🎲 You rolled a {result} on a {sides}-sided dice!")

@bot.command()
async def choose(ctx, *choices):
    """Choose between multiple options"""
    if len(choices) < 2:
        return await ctx.send("Please provide at least 2 choices!")

    choice = random.choice(choices)
    await ctx.send(f"🤔 I choose: **{choice}**")

@bot.command()
async def gif(ctx, *, search_term):
    """Get a random gif based on search term"""
    if not TENOR_API_KEY:
        # Fallback to popular GIF URLs if no API key
        fallback_gifs = {
            "happy": "https://media.tenor.com/k6qgJeJTOgsAAAAC/anime-happy.gif",
            "sad": "https://media.tenor.com/H_lKULYKuQkAAAAC/anime-cry.gif",
            "laugh": "https://media.tenor.com/7zApBJtX0S8AAAAC/anime-laugh.gif",
            "dance": "https://media.tenor.com/yMBovJrYSf8AAAAC/anime-dance.gif",
            "excited": "https://media.tenor.com/eKHuKbDxnXMAAAAC/anime-excited.gif",
            "confused": "https://media.tenor.com/5xtJNvmF8K0AAAAC/anime-confused.gif",
            "angry": "https://media.tenor.com/T8LWyxT8A0cAAAAC/anime-angry.gif",
            "love": "https://media.tenor.com/LCYQBk_jcpoAAAAC/anime-love.gif",
            "surprised": "https://media.tenor.com/2kbn1eAAAAC/surprised-pikachu.gif",
            "thinking": "https://media.tenor.com/5xtJNvmF8K0AAAAC/anime-thinking.gif"
        }

        # Try to match search term with fallback GIFs
        search_lower = search_term.lower()
        for key, gif_url in fallback_gifs.items():
            if key in search_lower:
                embed = create_aesthetic_embed("🎬 GIF Result",
                                             f"║ **Search:** {search_term} ║\n"
                                             f"║ **Source:** Fallback Collection ║",
                                             discord.Color.purple())
                embed.set_image(url=gif_url)
                embed.add_field(name="⚠️ Note", value="Using fallback GIF - Add TENOR_API_KEY for more results!", inline=True)
                return await ctx.send(embed=embed)

        # Default fallback
        embed = create_aesthetic_embed("🎬 GIF Result",
                                     f"║ **Search:** {search_term} ║\n"
                                     f"║ **Source:** Default Collection ║",
                                     discord.Color.orange())
        embed.set_image(url=fallback_gifs["happy"])
        embed.add_field(name="⚠️ Note", value="Add TENOR_API_KEY for better search results!", inline=True)
        return await ctx.send(embed=embed)

    try:
        # Search for GIF using Tenor API
        async with aiohttp.ClientSession() as session:
            url = "https://tenor.googleapis.com/v2/search"
            params = {
                "q": search_term,
                "key": TENOR_API_KEY,
                "limit": 20,  # Get multiple options
                "media_filter": "gif",
                "contentfilter": "medium",  # Filter out inappropriate content
                "random": "true"  # Get random results
            }

            async with session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])

                    if results:
                        # Select a random GIF from results
                        selected_gif = random.choice(results)
                        gif_url = selected_gif.get("media_formats", {}).get("gif", {}).get("url")

                        if gif_url:
                            description = f"""
╔══════════════════════════════════╗
║        🎬 **GIF SEARCH** 🎬        ║
╠══════════════════════════════════╣
║ **Search Term:** {search_term}
║ **Title:** {selected_gif.get('title', 'Untitled')[:40]}...
║ **Source:** Tenor API
║ **Content Rating:** Family Friendly
╚══════════════════════════════════╝
"""

                            embed = create_aesthetic_embed("Perfect Match!", description, discord.Color.random())
                            embed.set_image(url=gif_url)
                            embed.add_field(name="🎯 Search Quality", value="**HIGH** ✨", inline=True)
                            embed.add_field(name="🔄 Randomized", value="**YES** 🎲", inline=True)
                            embed.add_field(name="📱 Mobile Friendly", value="**OPTIMIZED** 📱", inline=True)

                            # Add link to original if available
                            if selected_gif.get("url"):
                                embed.add_field(name="🔗 Original Post",
                                              value=f"[Open in Tenor]({selected_gif['url']})",
                                              inline=False)

                            return await ctx.send(embed=embed)

                # If Tenor API fails, try alternative search
                print(f"Tenor API returned status {response.status} for search: {search_term}")

        # Try alternative Tenor endpoint
        async with aiohttp.ClientSession() as session:
            url = "https://tenor.googleapis.com/v2/featured"
            params = {
                "key": TENOR_API_KEY,
                "limit": 10,
                "media_filter": "gif",
                "contentfilter": "medium"
            }

            async with session.get(url, params=params, timeout=8) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("results", [])

                    if results:
                        selected_gif = random.choice(results)
                        gif_url = selected_gif.get("media_formats", {}).get("gif", {}).get("url")

                        if gif_url:
                            description = f"""
╔══════════════════════════════════╗
║       🌟 **FEATURED GIF** 🌟       ║
╠══════════════════════════════════╣
║ **Search:** {search_term}
║ **Result:** Featured/Trending GIF
║ **Source:** Tenor Featured
║ **Quality:** Premium
╚══════════════════════════════════╝
"""

                            embed = create_aesthetic_embed("Trending GIF", description, discord.Color.gold())
                            embed.set_image(url=gif_url)
                            embed.add_field(name="⭐ Status", value="**FEATURED** 🌟", inline=True)
                            embed.add_field(name="🔥 Popularity", value="**TRENDING** 📈", inline=True)
                            embed.add_field(name="✨ Quality", value="**PREMIUM** 💎", inline=True)

                            return await ctx.send(embed=embed)

        # If all else fails, use curated GIF collection
        curated_gifs = [
            "https://media.tenor.com/k6qgJeJTOgsAAAAC/anime-happy.gif",
            "https://media.tenor.com/yMBovJrYSf8AAAAC/anime-dance.gif",
            "https://media.tenor.com/eKHuKbDxnXMAAAAC/anime-excited.gif",
            "https://media.tenor.com/7zApBJtX0S8AAAAC/anime-laugh.gif",
            "https://media.tenor.com/LCYQBk_jcpoAAAAC/anime-love.gif"
        ]

        fallback_gif = random.choice(curated_gifs)

        description = f"""
╔══════════════════════════════════╗
║       🎪 **CURATED GIF** 🎪       ║
╠══════════════════════════════════╣
║ **Search:** {search_term}
║ **Result:** Curated Collection
║ **Source:** Premium Vault
║ **Reliability:** 100% Guaranteed
╚══════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Premium Collection", description, discord.Color.purple())
        embed.set_image(url=fallback_gif)
        embed.add_field(name="🎪 Collection", value="**CURATED** 🎨", inline=True)
        embed.add_field(name="✅ Reliability", value="**GUARANTEED** 💯", inline=True)
        embed.add_field(name="🎭 Quality", value="**HAND-PICKED** ✋", inline=True)

        await ctx.send(embed=embed)

    except asyncio.TimeoutError:
        embed = create_aesthetic_embed("⏰ Search Timeout",
                                     f"║ Search for '{search_term}' took too long! ║\n"
                                     f"║ Try a simpler search term ║",
                                     discord.Color.orange())
        await ctx.send(embed=embed)

    except Exception as e:
        print(f"GIF command error: {e}")

        # Emergency fallback
        emergency_gif = "https://media.tenor.com/k6qgJeJTOgsAAAAC/anime-happy.gif"

        embed = create_aesthetic_embed("🚨 Emergency GIF",
                                     f"║ Search for '{search_term}' failed! ║\n"
                                     f"║ Here's a backup GIF instead! ║",
                                     discord.Color.red())
        embed.set_image(url=emergency_gif)
        embed.add_field(name="🔧 Status", value="Emergency Mode", inline=True)
        embed.add_field(name="🛡️ Backup", value="Always Ready", inline=True)

        await ctx.send(embed=embed)

# Emote commands
@bot.command()
async def smile(ctx):
    """Smile"""
    await ctx.send(f"{ctx.author.display_name} is smiling! 😊")

@bot.command()
async def shrug(ctx):
    """Shrug"""
    await ctx.send(f"{ctx.author.display_name} shrugs! 🤷")

@bot.command()
async def wag(ctx):
    """Wag tail"""
    await ctx.send(f"{ctx.author.display_name} is wagging their tail! 🐕")

@bot.command()
async def thinking(ctx):
    """Think"""
    await ctx.send(f"{ctx.author.display_name} is thinking... 🤔")

@bot.command()
async def grin(ctx):
    """Grin"""
    await ctx.send(f"{ctx.author.display_name} is grinning! 😁")

# Utility commands
@bot.command()
async def ping(ctx):
    """Check bot latency"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! {latency}ms")

@bot.command()
async def invite(ctx):
    """Get bot invite link"""
    await ctx.send("📧 Invite me to your server! (Feature coming soon)")

@bot.command()
async def botstats(ctx):
    """Show bot statistics"""
    embed = discord.Embed(title="📊 Bot Statistics", color=discord.Color.blue())
    embed.add_field(name="Servers", value=len(bot.guilds), inline=True)
    embed.add_field(name="Users", value=len(bot.users), inline=True)
    embed.add_field(name="Commands", value=len(bot.commands), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def math(ctx, *, expression):
    """Calculate a basic math expression"""
    try:
        # Simple math evaluation (be careful with eval!)
        allowed_chars = "0123456789+-*/.() "
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            embed = create_aesthetic_embed("🧮 Basic Calculator",
                                         f"║ **Expression:** {expression} ║\n"
                                         f"║ **Result:** {result} ║",
                                         discord.Color.blue())
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Invalid characters! Use `owo calc` for advanced operations.")
    except Exception as e:
        await ctx.send(f"❌ Invalid expression! Error: {str(e)}")

@bot.command(aliases=['calculator', 'calc'])
async def calculate(ctx, *, expression):
    """Advanced scientific calculator with trigonometry, logarithms, and more"""
    try:
        import math as m
        import cmath

        # Create safe evaluation environment
        safe_dict = {
            # Basic operations
            'abs': abs, 'round': round, 'pow': pow,
            # Math constants
            'pi': m.pi, 'e': m.e, 'tau': m.tau,
            # Trigonometric functions
            'sin': m.sin, 'cos': m.cos, 'tan': m.tan,
            'asin': m.asin, 'acos': m.acos, 'atan': m.atan,
            'sinh': m.sinh, 'cosh': m.cosh, 'tanh': m.tanh,
            # Logarithms and exponentials
            'log': m.log, 'log10': m.log10, 'log2': m.log2,
            'exp': m.exp, 'sqrt': m.sqrt,
            # Other functions
            'factorial': m.factorial, 'gcd': m.gcd,
            'degrees': m.degrees, 'radians': m.radians,
            'floor': m.floor, 'ceil': m.ceil,
            # Complex numbers
            'complex': complex, 'real': lambda x: x.real if isinstance(x, complex) else x,
            'imag': lambda x: x.imag if isinstance(x, complex) else 0,
        }

        # Evaluate expression
        result = eval(expression, {"__builtins__": {}}, safe_dict)

        # Format result
        if isinstance(result, complex):
            result_str = f"{result.real:.6f} + {result.imag:.6f}i" if result.imag >= 0 else f"{result.real:.6f} - {abs(result.imag):.6f}i"
        elif isinstance(result, float):
            result_str = f"{result:.6f}".rstrip('0').rstrip('.')
        else:
            result_str = str(result)

        description = f"""
╔════════════════════════════════════╗
║    🔬 **SCIENTIFIC CALCULATOR** 🔬    ║
╠════════════════════════════════════╣
║ **Expression:** {expression[:40]}{'...' if len(expression) > 40 else ''}
║ **Result:** {result_str}
║ **Type:** {type(result).__name__}
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Advanced Calculation", description, discord.Color.purple())
        embed.add_field(name="📐 Available Functions",
                       value="sin, cos, tan, log, sqrt, exp, factorial, etc.",
                       inline=True)
        embed.add_field(name="🎯 Constants",
                       value="pi, e, tau",
                       inline=True)
        embed.add_field(name="💡 Example",
                       value="`owo calc sin(pi/2)`",
                       inline=True)

        await ctx.send(embed=embed)

    except Exception as e:
        embed = create_aesthetic_embed("❌ Calculation Error",
                                     f"║ **Error:** {str(e)} ║\n"
                                     f"║ Use `owo mathhelp` for function list ║",
                                     discord.Color.red())
        await ctx.send(embed=embed)

@bot.command()
async def solve(ctx, equation_type, *, equation):
    """Solve equations (linear, quadratic, or system)"""
    try:
        import re

        equation_type = equation_type.lower()

        if equation_type in ['linear', 'l']:
            # Solve linear equation: ax + b = c
            match = re.match(r'([+-]?\d*\.?\d*)x\s*([+-])\s*(\d+\.?\d*)\s*=\s*(\d+\.?\d*)', equation.replace(' ', ''))
            if match:
                a = float(match.group(1) or '1')
                sign = match.group(2)
                b = float(match.group(3))
                c = float(match.group(4))

                b = -b if sign == '-' else b
                x = (c - b) / a if a != 0 else None

                if x is not None:
                    description = f"""
╔════════════════════════════════════╗
║      ➗ **LINEAR EQUATION** ➗      ║
╠════════════════════════════════════╣
║ **Equation:** {equation}
║ **Solution:** x = {x:.6f}
║ **Verification:** {a}({x:.6f}) + {b} = {a*x + b:.6f}
╚════════════════════════════════════╝
"""
                    embed = create_aesthetic_embed("Equation Solved", description, discord.Color.green())
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ No solution exists (division by zero)!")
            else:
                await ctx.send("❌ Invalid linear equation format! Use: `ax + b = c`")

        elif equation_type in ['quadratic', 'q']:
            # Solve quadratic equation: ax^2 + bx + c = 0
            match = re.match(r'([+-]?\d*\.?\d*)x\^2\s*([+-])\s*(\d*\.?\d*)x\s*([+-])\s*(\d+\.?\d*)\s*=\s*0', equation.replace(' ', ''))
            if match:
                a = float(match.group(1) or '1')
                sign1 = match.group(2)
                b = float(match.group(3) or '1')
                sign2 = match.group(4)
                c = float(match.group(5))

                b = -b if sign1 == '-' else b
                c = -c if sign2 == '-' else c

                discriminant = b**2 - 4*a*c

                if discriminant > 0:
                    x1 = (-b + discriminant**0.5) / (2*a)
                    x2 = (-b - discriminant**0.5) / (2*a)
                    solutions = f"x₁ = {x1:.6f}, x₂ = {x2:.6f}"
                    sol_type = "Two real solutions"
                elif discriminant == 0:
                    x = -b / (2*a)
                    solutions = f"x = {x:.6f}"
                    sol_type = "One real solution"
                else:
                    real_part = -b / (2*a)
                    imag_part = (abs(discriminant)**0.5) / (2*a)
                    solutions = f"x₁ = {real_part:.6f} + {imag_part:.6f}i\nx₂ = {real_part:.6f} - {imag_part:.6f}i"
                    sol_type = "Two complex solutions"

                description = f"""
╔════════════════════════════════════╗
║     📐 **QUADRATIC EQUATION** 📐     ║
╠════════════════════════════════════╣
║ **Equation:** {equation}
║ **Discriminant:** {discriminant:.6f}
║ **Type:** {sol_type}
║ **Solutions:**
║ {solutions}
╚════════════════════════════════════╝
"""
                embed = create_aesthetic_embed("Quadratic Solved", description, discord.Color.blue())
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Invalid quadratic equation! Use: `ax^2 + bx + c = 0`")
        else:
            await ctx.send("❌ Invalid equation type! Use: `linear` or `quadratic`")

    except Exception as e:
        await ctx.send(f"❌ Error solving equation: {str(e)}")

@bot.command()
async def stats(ctx, operation, *, numbers):
    """Calculate statistics (mean, median, mode, stddev)"""
    try:
        import statistics as stats_lib

        # Parse numbers
        num_list = [float(x.strip()) for x in numbers.replace(',', ' ').split()]

        if len(num_list) == 0:
            return await ctx.send("❌ Please provide numbers!")

        operation = operation.lower()

        if operation in ['mean', 'average', 'avg']:
            result = stats_lib.mean(num_list)
            op_name = "Mean (Average)"
            formula = "Σx / n"
        elif operation in ['median', 'med']:
            result = stats_lib.median(num_list)
            op_name = "Median"
            formula = "Middle value"
        elif operation in ['mode']:
            try:
                result = stats_lib.mode(num_list)
                op_name = "Mode"
                formula = "Most frequent value"
            except stats_lib.StatisticsError:
                return await ctx.send("❌ No unique mode found!")
        elif operation in ['stddev', 'std', 'stdev']:
            if len(num_list) < 2:
                return await ctx.send("❌ Need at least 2 numbers for standard deviation!")
            result = stats_lib.stdev(num_list)
            op_name = "Standard Deviation"
            formula = "√(Σ(x - μ)² / (n-1))"
        elif operation in ['variance', 'var']:
            if len(num_list) < 2:
                return await ctx.send("❌ Need at least 2 numbers for variance!")
            result = stats_lib.variance(num_list)
            op_name = "Variance"
            formula = "Σ(x - μ)² / (n-1)"
        elif operation in ['all', 'summary']:
            mean_val = stats_lib.mean(num_list)
            median_val = stats_lib.median(num_list)

            description = f"""
╔════════════════════════════════════╗
║     📊 **STATISTICAL SUMMARY** 📊     ║
╠════════════════════════════════════╣
║ **Count:** {len(num_list)} numbers
║ **Mean:** {mean_val:.6f}
║ **Median:** {median_val:.6f}
║ **Min:** {min(num_list):.6f}
║ **Max:** {max(num_list):.6f}
║ **Range:** {max(num_list) - min(num_list):.6f}
"""
            if len(num_list) >= 2:
                description += f"║ **Std Dev:** {stats_lib.stdev(num_list):.6f}\n"
                description += f"║ **Variance:** {stats_lib.variance(num_list):.6f}\n"

            description += "╚════════════════════════════════════╝"

            embed = create_aesthetic_embed("Statistics", description, discord.Color.gold())
            embed.add_field(name="📈 Data Set",
                           value=f"{', '.join(map(str, num_list[:10]))}{'...' if len(num_list) > 10 else ''}",
                           inline=False)
            return await ctx.send(embed=embed)
        else:
            return await ctx.send("❌ Invalid operation! Use: mean, median, mode, stddev, variance, or all")

        description = f"""
╔════════════════════════════════════╗
║       📊 **{op_name.upper()}** 📊       ║
╠════════════════════════════════════╣
║ **Operation:** {op_name}
║ **Formula:** {formula}
║ **Result:** {result:.6f}
║ **Sample Size:** {len(num_list)} numbers
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Statistical Analysis", description, discord.Color.teal())
        embed.add_field(name="📈 Data Set",
                       value=f"{', '.join(map(str, num_list[:10]))}{'...' if len(num_list) > 10 else ''}",
                       inline=False)

        await ctx.send(embed=embed)

    except ValueError:
        await ctx.send("❌ Invalid numbers provided!")
    except Exception as e:
        await ctx.send(f"❌ Error calculating statistics: {str(e)}")

@bot.command()
async def convert(ctx, value: float, from_unit, to_unit):
    """Convert between units (length, weight, temperature, etc.)"""
    try:
        from_unit = from_unit.lower()
        to_unit = to_unit.lower()

        # Length conversions (to meters)
        length_units = {
            'm': 1, 'meter': 1, 'meters': 1,
            'km': 1000, 'kilometer': 1000, 'kilometers': 1000,
            'cm': 0.01, 'centimeter': 0.01, 'centimeters': 0.01,
            'mm': 0.001, 'millimeter': 0.001, 'millimeters': 0.001,
            'mi': 1609.34, 'mile': 1609.34, 'miles': 1609.34,
            'ft': 0.3048, 'foot': 0.3048, 'feet': 0.3048,
            'in': 0.0254, 'inch': 0.0254, 'inches': 0.0254,
            'yd': 0.9144, 'yard': 0.9144, 'yards': 0.9144,
        }

        # Weight conversions (to kilograms)
        weight_units = {
            'kg': 1, 'kilogram': 1, 'kilograms': 1,
            'g': 0.001, 'gram': 0.001, 'grams': 0.001,
            'mg': 0.000001, 'milligram': 0.000001, 'milligrams': 0.000001,
            'lb': 0.453592, 'pound': 0.453592, 'pounds': 0.453592,
            'oz': 0.0283495, 'ounce': 0.0283495, 'ounces': 0.0283495,
            'ton': 1000, 'tons': 1000, 'tonne': 1000, 'tonnes': 1000,
        }

        # Temperature conversions
        if from_unit in ['c', 'celsius'] and to_unit in ['f', 'fahrenheit']:
            result = (value * 9/5) + 32
            unit_type = "Temperature"
        elif from_unit in ['f', 'fahrenheit'] and to_unit in ['c', 'celsius']:
            result = (value - 32) * 5/9
            unit_type = "Temperature"
        elif from_unit in ['c', 'celsius'] and to_unit in ['k', 'kelvin']:
            result = value + 273.15
            unit_type = "Temperature"
        elif from_unit in ['k', 'kelvin'] and to_unit in ['c', 'celsius']:
            result = value - 273.15
            unit_type = "Temperature"
        elif from_unit in ['f', 'fahrenheit'] and to_unit in ['k', 'kelvin']:
            result = (value - 32) * 5/9 + 273.15
            unit_type = "Temperature"
        # Length conversions
        elif from_unit in length_units and to_unit in length_units:
            meters = value * length_units[from_unit]
            result = meters / length_units[to_unit]
            unit_type = "Length"
        # Weight conversions
        elif from_unit in weight_units and to_unit in weight_units:
            kg = value * weight_units[from_unit]
            result = kg / weight_units[to_unit]
            unit_type = "Weight"
        else:
            return await ctx.send("❌ Invalid unit combination! Supported: length, weight, temperature")

        description = f"""
╔════════════════════════════════════╗
║       🔄 **UNIT CONVERSION** 🔄       ║
╠════════════════════════════════════╣
║ **Type:** {unit_type}
║ **From:** {value} {from_unit.upper()}
║ **To:** {result:.6f} {to_unit.upper()}
║ **Conversion Rate:** 1 {from_unit} = {result/value:.6f} {to_unit}
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Conversion Complete", description, discord.Color.blue())
        embed.add_field(name="📏 Original", value=f"{value} {from_unit}", inline=True)
        embed.add_field(name="🎯 Result", value=f"{result:.6f} {to_unit}", inline=True)

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Conversion error: {str(e)}")

@bot.command()
async def derivative(ctx, *, expression):
    """Calculate the derivative of an expression"""
    try:
        from sympy import symbols, diff, sympify, latex
        from sympy.parsing.sympy_parser import parse_expr

        x = symbols('x')

        # Parse the expression
        expr = parse_expr(expression, transformations='all')

        # Calculate derivative
        derivative_expr = diff(expr, x)

        # Simplify
        derivative_simplified = derivative_expr.simplify()

        description = f"""
╔════════════════════════════════════╗
║      📐 **DERIVATIVE** 📐      ║
╠════════════════════════════════════╣
║ **Original:** f(x) = {expr}
║ **Derivative:** f'(x) = {derivative_simplified}
║ **Method:** Symbolic differentiation
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Calculus - Derivative", description, discord.Color.blue())
        embed.add_field(name="📚 Notation", value="d/dx", inline=True)
        embed.add_field(name="🎯 Variable", value="x", inline=True)
        embed.add_field(name="✨ Simplified", value="Yes", inline=True)

        await ctx.send(embed=embed)

    except Exception as e:
        embed = create_aesthetic_embed("❌ Derivative Error",
                                     f"║ **Error:** {str(e)} ║\n"
                                     f"║ Example: `owo derivative x^2 + 3*x + 1` ║",
                                     discord.Color.red())
        await ctx.send(embed=embed)

@bot.command()
async def integral(ctx, *, expression):
    """Calculate the integral of an expression"""
    try:
        from sympy import symbols, integrate, sympify
        from sympy.parsing.sympy_parser import parse_expr

        x = symbols('x')

        # Parse the expression
        expr = parse_expr(expression, transformations='all')

        # Calculate integral
        integral_expr = integrate(expr, x)

        description = f"""
╔════════════════════════════════════╗
║      ∫ **INTEGRAL** ∫      ║
╠════════════════════════════════════╣
║ **Original:** f(x) = {expr}
║ **Integral:** ∫f(x)dx = {integral_expr} + C
║ **Method:** Symbolic integration
║ **Note:** Don't forget + C!
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Calculus - Integral", description, discord.Color.green())
        embed.add_field(name="📚 Type", value="Indefinite Integral", inline=True)
        embed.add_field(name="🎯 Variable", value="x", inline=True)
        embed.add_field(name="➕ Constant", value="+ C", inline=True)

        await ctx.send(embed=embed)

    except Exception as e:
        embed = create_aesthetic_embed("❌ Integral Error",
                                     f"║ **Error:** {str(e)} ║\n"
                                     f"║ Example: `owo integral 2*x + 3` ║",
                                     discord.Color.red())
        await ctx.send(embed=embed)

@bot.command()
async def limit(ctx, expression, point, direction="both"):
    """Calculate the limit of an expression"""
    try:
        from sympy import symbols, limit as sym_limit, sympify, oo
        from sympy.parsing.sympy_parser import parse_expr

        x = symbols('x')

        # Parse the expression
        expr = parse_expr(expression, transformations='all')

        # Parse the point
        if point.lower() == 'inf' or point.lower() == 'infinity':
            point_val = oo
        elif point.lower() == '-inf' or point.lower() == '-infinity':
            point_val = -oo
        else:
            point_val = parse_expr(point)

        # Calculate limit based on direction
        direction = direction.lower()
        if direction in ['left', '-', 'minus']:
            result = sym_limit(expr, x, point_val, '-')
            dir_text = "from the left (x → a⁻)"
        elif direction in ['right', '+', 'plus']:
            result = sym_limit(expr, x, point_val, '+')
            dir_text = "from the right (x → a⁺)"
        else:
            result = sym_limit(expr, x, point_val)
            dir_text = "from both sides"

        description = f"""
╔════════════════════════════════════╗
║      🎯 **LIMIT** 🎯      ║
╠════════════════════════════════════╣
║ **Expression:** f(x) = {expr}
║ **Point:** x → {point_val}
║ **Direction:** {dir_text}
║ **Result:** {result}
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Calculus - Limit", description, discord.Color.purple())
        embed.add_field(name="📍 Approaching", value=str(point_val), inline=True)
        embed.add_field(name="🧭 Direction", value=direction.title(), inline=True)
        embed.add_field(name="✨ Result", value=str(result), inline=True)

        await ctx.send(embed=embed)

    except Exception as e:
        embed = create_aesthetic_embed("❌ Limit Error",
                                     f"║ **Error:** {str(e)} ║\n"
                                     f"║ Example: `owo limit (x^2-1)/(x-1) 1` ║",
                                     discord.Color.red())
        await ctx.send(embed=embed)

@bot.command()
async def series(ctx, expression, n: int = 5):
    """Calculate Taylor/Maclaurin series expansion"""
    try:
        from sympy import symbols, series as sym_series, sympify
        from sympy.parsing.sympy_parser import parse_expr

        x = symbols('x')

        # Parse the expression
        expr = parse_expr(expression, transformations='all')

        # Calculate series expansion around 0 (Maclaurin series)
        series_expansion = sym_series(expr, x, 0, n)

        description = f"""
╔════════════════════════════════════╗
║   📊 **SERIES EXPANSION** 📊   ║
╠════════════════════════════════════╣
║ **Function:** f(x) = {expr}
║ **Expansion Point:** x = 0
║ **Terms:** {n}
║ **Series:** {series_expansion}
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Calculus - Taylor Series", description, discord.Color.gold())
        embed.add_field(name="📐 Type", value="Maclaurin Series", inline=True)
        embed.add_field(name="🔢 Order", value=f"{n} terms", inline=True)
        embed.add_field(name="📍 Center", value="x = 0", inline=True)

        await ctx.send(embed=embed)

    except Exception as e:
        embed = create_aesthetic_embed("❌ Series Error",
                                     f"║ **Error:** {str(e)} ║\n"
                                     f"║ Example: `owo series sin(x) 5` ║",
                                     discord.Color.red())
        await ctx.send(embed=embed)

@bot.command()
async def mathhelp(ctx):
    """Show all available math commands and functions"""

    description = """
╔════════════════════════════════════╗
║    🔬 **MATHEMATICS SYSTEM** 🔬    ║
╚════════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Advanced Mathematics Help", description, discord.Color.purple())

    embed.add_field(
        name="🧮 Basic Calculator",
        value="`owo math 2 + 2`\nSimple arithmetic operations",
        inline=False
    )

    embed.add_field(
        name="🔬 Scientific Calculator",
        value="`owo calc sin(pi/2)`\n"
              "**Functions:** sin, cos, tan, asin, acos, atan, sinh, cosh, tanh\n"
              "**Logarithms:** log, log10, log2, exp\n"
              "**Others:** sqrt, factorial, abs, round, floor, ceil\n"
              "**Constants:** pi, e, tau",
        inline=False
    )

    embed.add_field(
        name="📐 Calculus",
        value="`owo derivative x^2 + 3*x`\n"
              "`owo integral 2*x + 1`\n"
              "`owo limit (x^2-1)/(x-1) 1`\n"
              "`owo series sin(x) 5`\n"
              "**Operations:** derivative, integral, limit, series",
        inline=False
    )

    embed.add_field(
        name="➗ Equation Solver",
        value="`owo solve linear 2x + 3 = 7`\n"
              "`owo solve quadratic x^2 + 5x + 6 = 0`\n"
              "Solve linear and quadratic equations",
        inline=False
    )

    embed.add_field(
        name="📊 Statistics",
        value="`owo stats mean 1 2 3 4 5`\n"
              "`owo stats all 1 2 3 4 5`\n"
              "**Operations:** mean, median, mode, stddev, variance, all",
        inline=False
    )

    embed.add_field(
        name="🔄 Unit Converter",
        value="`owo convert 100 cm m`\n"
              "`owo convert 32 f c`\n"
              "**Types:** Length, Weight, Temperature",
        inline=False
    )

    embed.add_field(
        name="💡 Examples",
        value="• `owo calc sqrt(16) + log(10)`\n"
              "• `owo derivative x^3 - 2*x^2 + x`\n"
              "• `owo integral cos(x)`\n"
              "• `owo solve quadratic x^2 - 4 = 0`\n"
              "• `owo stats all 10 20 30 40 50`\n"
              "• `owo convert 5 km mi`",
        inline=False
    )

    await ctx.send(embed=embed)



@bot.command()
async def truthordare(ctx, member: discord.Member = None):
    """Play truth or dare"""
    member = member or ctx.author

    truth_questions = [
        "What's your most embarrassing moment?",
        "Who was your first crush?",
        "What's the weirdest thing you've eaten?",
        "What's your biggest fear?",
        "Have you ever had a crush on a friend?",
        "What's the most childish thing you still do?",
        "What's your biggest pet peeve?",
        "Who do you have a secret crush on?",
        "What's the most trouble you've been in?",
        "What's your most embarrassing habit?",
        "If you could date anyone in this server, who would it be?",
        "What's the last lie you told?",
        "What's your guilty pleasure?",
        "Who's the last person you stalked on social media?",
        "What's something you've never told anyone?"
    ]

    dare_challenges = [
        "Do your best impression of a Discord mod",
        "Send a selfie in this channel",
        "Sing your favorite song in voice chat",
        "Do 20 push-ups and post a video",
        "Change your nickname to something embarrassing for 24 hours",
        "Text your crush 'hey' right now",
        "Post an embarrassing childhood photo",
        "Do a funny dance on camera",
        "Let someone else send a message from your account",
        "Say something nice about everyone online",
        "Speak in rhymes for the next 10 minutes",
        "Do your best animal impression",
        "Tell a joke in the worst possible way",
        "Compliment the person above you in the most dramatic way",
        "Share your most played song on Spotify"
    ]

    choice = random.choice(["truth", "dare"])

    if choice == "truth":
        question = random.choice(truth_questions)
        emoji = "🤔"
        color = discord.Color.blue()
        challenge_type = "TRUTH"
    else:
        question = random.choice(dare_challenges)
        emoji = "😈"
        color = discord.Color.red()
        challenge_type = "DARE"

    description = f"""
╔══════════════════════════════════╗
║      {emoji} **{challenge_type} OR DARE** {emoji}      ║
╠══════════════════════════════════╣
║ **Player:** {member.display_name}
║ **Challenge Type:** **{challenge_type}**
║
║ **{challenge_type}:**
║ {question}
╚══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Truth or Dare Game", description, color, member.display_avatar.url)
    embed.add_field(name="🎮 Game Rules", value="Complete the challenge or face the consequences!", inline=True)
    embed.add_field(name="⏰ Time Limit", value="60 seconds to respond!", inline=True)
    embed.add_field(name="🏆 Courage Level", value="**MAXIMUM**" if choice == "dare" else "**HIGH**", inline=True)

    await ctx.send(embed=embed)



@bot.command()
async def roast(ctx, member: discord.Member = None):
    """Roast someone (playfully)"""
    member = member or ctx.author

    roasts = [
        f"{member.display_name} is so slow, they make Internet Explorer look fast! 🐌",
        f"If {member.display_name} was any more basic, they'd be pH 14! 🧪",
        f"{member.display_name}'s brain has more empty space than a parking lot on Black Friday! 🧠",
        f"I'd roast {member.display_name}, but my mom said I shouldn't burn trash! 🔥",
        f"{member.display_name} is like a software update - nobody wants you, but you keep showing up! 💻",
        f"If ignorance is bliss, {member.display_name} must be the happiest person alive! 😊",
        f"{member.display_name} brings everyone so much joy... when they leave! 🚪",
        f"I'm not saying {member.display_name} is dumb, but they'd struggle with a one-piece puzzle! 🧩",
        f"{member.display_name} is proof that evolution can go in reverse! 🐒",
        f"If {member.display_name} was any more dense, they'd collapse into a black hole! 🕳️"
    ]

    selected_roast = random.choice(roasts)

    description = f"""
╔══════════════════════════════════╗
║         🔥 **ROAST TIME** 🔥         ║
╠══════════════════════════════════╣
║ **Target:** {member.display_name}
║ **Roast Level:** MAXIMUM DAMAGE
║
║ {selected_roast}
╚══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Roast Session", description, discord.Color.from_rgb(255, 69, 0), member.display_avatar.url)
    embed.add_field(name="🔥 Burn Level", value="**THIRD DEGREE** 🏥", inline=True)
    embed.add_field(name="😂 Comedy Rating", value="**COMEDY GOLD** 🏆", inline=True)
    embed.add_field(name="💊 Recovery Time", value="3-5 business days", inline=True)
    embed.set_footer(text="💝 All roasts are made with love! This is just for fun!")

    await ctx.send(embed=embed)

@bot.command()
async def compliment(ctx, member: discord.Member = None):
    """Give someone a nice compliment"""
    member = member or ctx.author

    compliments = [
        f"{member.display_name} has the most amazing personality! ✨",
        f"The world is a better place with {member.display_name} in it! 🌟",
        f"{member.display_name} always knows how to make people smile! 😊",
        f"Everyone loves {member.display_name}'s positive energy! ⚡",
        f"{member.display_name} is incredibly talented and smart! 🧠",
        f"You're absolutely wonderful, {member.display_name}! 💖",
        f"{member.display_name} brings out the best in everyone! 🎯",
        f"The server is so much better with {member.display_name} here! 🏠",
        f"{member.display_name} has such a kind and generous heart! ❤️",
        f"You're an inspiration to us all, {member.display_name}! 🌈"
    ]

    selected_compliment = random.choice(compliments)

    description = f"""
╔══════════════════════════════════╗
║       💖 **COMPLIMENT TIME** 💖       ║
╠══════════════════════════════════╣
║ **Amazing Person:** {member.display_name}
║ **Positivity Level:** MAXIMUM
║
║ {selected_compliment}
╚══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Spreading Positivity", description, discord.Color.from_rgb(255, 182, 193), member.display_avatar.url)
    embed.add_field(name="💝 Kindness Level", value="**OVERFLOWING** 🌊", inline=True)
    embed.add_field(name="✨ Mood Boost", value="**+1000 HAPPINESS** 📈", inline=True)
    embed.add_field(name="🌟 You're Special", value="**ABSOLUTELY** 💯", inline=True)

    await ctx.send(embed=embed)

@bot.command()
async def avatar(ctx, member: discord.Member = None):
    """Get user's avatar"""
    member = member or ctx.author
    embed = discord.Embed(title=f"{member.display_name}'s Avatar", color=member.color)
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def ship(ctx, member1: discord.Member, member2: discord.Member = None):
    """Ship two users"""
    if member2 is None:
        member2 = ctx.author

    compatibility = random.randint(0, 100)

    if compatibility >= 90:
        rating = "Perfect match! 💕"
    elif compatibility >= 70:
        rating = "Great couple! ❤️"
    elif compatibility >= 50:
        rating = "Good potential! 💙"
    elif compatibility >= 30:
        rating = "Could work... 💛"
    else:
        rating = "Not meant to be... 💔"

    embed = discord.Embed(title="💘 Love Calculator", color=discord.Color.pink())
    embed.add_field(name="Ship", value=f"{member1.display_name} x {member2.display_name}", inline=False)
    embed.add_field(name="Compatibility", value=f"{compatibility}%", inline=True)
    embed.add_field(name="Rating", value=rating, inline=True)
    await ctx.send(embed=embed)

# Run the bot
if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("Error: DISCORD_TOKEN environment variable not set!")
        print("Please set your Discord bot token in the Secrets tab.")
        exit(1)

    # Add retry logic for rate limiting
    import time
    max_retries = 3
    retry_delay = 30  # seconds

    for attempt in range(max_retries):
        try:
            print(f"Starting bot (attempt {attempt + 1}/{max_retries})...")
            bot.run(token)
            break
        except discord.errors.HTTPException as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                if attempt < max_retries - 1:
                    print(f"Rate limited. Waiting {retry_delay} seconds before retry...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print("Max retries reached. Please wait longer before restarting.")
                    exit(1)
            else:
                print(f"HTTP Error: {e}")
                exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}")
            exit(1)