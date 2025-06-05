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

# DeepSeek AI Integration
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

async def get_deepseek_response(message, user_id):
    """Get AI response from DeepSeek API"""
    if not DEEPSEEK_API_KEY:
        print("Warning: DEEPSEEK_API_KEY not found, using fallback responses")
        return get_simple_bot_response(message, user_id)
    
    try:
        # Determine personality based on user
        if user_id == OWNER_ID:
            personality = "You are a helpful and respectful AI assistant for a Discord bot. You serve as the bot's AI companion and should be professional yet friendly. You have access to economy, gaming, and social features."
        elif user_id == SPECIAL_AI_ID:
            personality = "You are a polite and helpful AI assistant for a Discord bot. You should be especially courteous and helpful. You can discuss the bot's features like economy games, social commands, and fun activities."
        else:
            personality = "You are a friendly AI companion for a Discord bot named OwO Bot. You should be casual, fun, and engaging. You can mention the bot's features like economy systems, games, social commands, and entertainment. Keep responses concise and Discord-appropriate."
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": personality
                },
                {
                    "role": "user", 
                    "content": message
                }
            ],
            "max_tokens": 200,
            "temperature": 0.7,
            "stream": False
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if "choices" in data and len(data["choices"]) > 0:
                        ai_response = data["choices"][0]["message"]["content"].strip()
                        
                        # Ensure response isn't too long for Discord
                        if len(ai_response) > 1800:
                            ai_response = ai_response[:1800] + "..."
                        
                        return ai_response
                    else:
                        print(f"Unexpected DeepSeek API response format: {data}")
                        return get_simple_bot_response(message, user_id)
                        
                else:
                    print(f"DeepSeek API error: {response.status}")
                    return get_simple_bot_response(message, user_id)
                    
    except asyncio.TimeoutError:
        print("DeepSeek API timeout")
        return get_simple_bot_response(message, user_id)
    except Exception as e:
        print(f"DeepSeek API error: {e}")
        return get_simple_bot_response(message, user_id)

def get_simple_bot_response(message, user_id):
    """Fallback simple responses when AI is unavailable"""
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
        return "https://media.tenor.com/eKHuKbDxnXMAAAAC/anime-happy.gif"
    
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

# Custom ranks system
CUSTOM_RANKS = {
    "Peasant": {"color": 0x8B4513, "emoji": "👨‍🌾"},
    "Citizen": {"color": 0x696969, "emoji": "👨‍💼"},
    "Noble": {"color": 0x4169E1, "emoji": "👑"},
    "Knight": {"color": 0x32CD32, "emoji": "⚔️"},
    "Lord": {"color": 0x800080, "emoji": "🏰"},
    "Duke": {"color": 0xFF1493, "emoji": "💎"},
    "King": {"color": 0xFFD700, "emoji": "👑"},
    "Emperor": {"color": 0xFF4500, "emoji": "🔥"}
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
                                     "║ This command is for the supreme owner only! ║", 
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
                                     "║ This command is for the supreme owner only! ║", 
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
                                     "║ This command is for the supreme owner only! ║", 
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
                                     "║ This command is for the supreme owner only! ║", 
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
                                     "This command is for the supreme owner only!", 
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
                                     "This command is for the supreme owner only!", 
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

    embed = create_aesthetic_embed("Divine Ascension", description, discord.Color.purple(), member.display_avatar.url)
    embed.add_field(name="⚡ Power Level", value=f"**{level}** ⭐", inline=True)
    embed.add_field(name="👑 Authority", value="**OWNER PRIVILEGE**", inline=True)
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
        # Clean message content (remove mention)
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').replace(f'<@!{bot.user.id}>', '').strip()
        
        if not clean_content:  # Handle empty mentions
            if message.author.id == OWNER_ID:
                response = "Hello there! How may I assist you today?"
            elif message.author.id == SPECIAL_AI_ID:
                response = "Hi there! You mentioned me - how can I help you today? 😊"
            else:
                response = "Hey! What's up? 👋"
        else:
            # Generate AI response using DeepSeek
            response = await get_deepseek_response(clean_content, message.author.id)
        
        await message.reply(response)

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
    total_amount = calculate_daily_bonus(level) + (streak * 50)

    leveled_up, new_level = await add_xp(ctx.author.id, 50)

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

    if leveled_up:
        description += f"\n\n🎉 **LEVEL UP!** You're now level **{new_level}**!"

    embed = create_aesthetic_embed("💰 Daily Reward", description, discord.Color.gold())
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def work(ctx):
    """Work to earn money"""
    user = await get_user_data(ctx.author.id)
    now = datetime.datetime.now()

    if user["last_work"] and (now - user["last_work"].replace(tzinfo=None)).seconds < 3600:
        remaining = 3600 - (now - user["last_work"].replace(tzinfo=None)).seconds
        embed = create_aesthetic_embed("😴 Too Tired", 
                                     f"You're too tired to work!\n"
                                     f"Try again in **{remaining//60}** minutes.",
                                     discord.Color.orange())
        return await ctx.send(embed=embed)

    level = user.get("level", 1)
    work_range = calculate_work_bonus(level)
    base_amount = random.randint(*work_range)
    level_bonus = calculate_level_bonus(level)
    total_amount = base_amount + level_bonus

    jobs = ["🖥️ Programmer", "⚕️ Doctor", "📚 Teacher", "📺 Streamer", 
           "🎨 Artist", "👨‍🍳 Chef", "🔬 Scientist", "⚖️ Lawyer", 
           "🔧 Engineer", "🎭 Designer"]
    job = random.choice(jobs)

    leveled_up, new_level = await add_xp(ctx.author.id, 30)

    await update_user_data(ctx.author.id, {
        "balance": user["balance"] + total_amount,
        "last_work": now
    })

    description = f"You worked as a **{job}**\n"
    description += f"💰 Base Pay: **{base_amount:,}** 💵\n"
    description += f"⭐ Level {level} Bonus: **+{level_bonus:,}** 💵\n"
    description += f"💎 Total Earned: **{total_amount:,}** 💵"

    if leveled_up:
        description += f"\n\n🎉 **LEVEL UP!** You're now level **{new_level}**!"

    embed = create_aesthetic_embed("💼 Work Complete", description, discord.Color.blue())
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/878328329692819466.gif")
    await ctx.send(embed=embed)

# Enhanced Social commands with anime GIFs and advanced aesthetics
@bot.command()
async def hug(ctx, member: discord.Member):
    """Hug another user with anime GIF"""
    gif_url = await get_anime_gif("hug")

    description = f"""
╔═══════════════════════════════════╗
║            💕 **WARM HUG** 💕            ║
╠═══════════════════════════════════╣
║ **{ctx.author.display_name}** wraps **{member.display_name}**
║ in a loving, warm embrace! 
║ 
║ 🌸 Comfort Level: Maximum
║ 💝 Love Points: +1000
║ 🤗 Hug Quality: Legendary
╚═══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Wholesome Interaction", description, discord.Color.from_rgb(255, 182, 193))
    embed.set_image(url=gif_url)
    embed.add_field(name="💫 Interaction Type", value="🤗 **AFFECTIONATE HUG**", inline=True)
    embed.add_field(name="🌟 Mood Boost", value="📈 **+50 Happiness**", inline=True)
    embed.add_field(name="🎭 Anime Style", value="✨ **Kawaii Level Max**", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def kiss(ctx, member: discord.Member):
    """Kiss another user with anime GIF"""
    gif_url = await get_anime_gif("kiss")

    description = f"""
╔═══════════════════════════════════╗
║          💋 **ROMANTIC KISS** 💋          ║
╠═══════════════════════════════════╣
║ **{ctx.author.display_name}** gives **{member.display_name}**
║ a tender, passionate kiss!
║ 
║ 💕 Romance Level: Supreme
║ 💖 Love Intensity: Maximum
║ 😘 Kiss Quality: Perfect
╚═══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Romantic Moment", description, discord.Color.from_rgb(255, 20, 147))
    embed.set_image(url=gif_url)
    embed.add_field(name="💫 Interaction Type", value="💋 **PASSIONATE KISS**", inline=True)
    embed.add_field(name="💘 Romance Points", value="📈 **+2000 Love**", inline=True)
    embed.add_field(name="🌹 Romantic Level", value="✨ **Ultimate Romance**", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def slap(ctx, member: discord.Member):
    """Slap another user with anime GIF"""
    gif_url = await get_anime_gif("slap")

    description = f"""
╔═══════════════════════════════════╗
║         👋 **DRAMATIC SLAP** 👋         ║
╠═══════════════════════════════════╣
║ **{ctx.author.display_name}** delivers a dramatic
║ anime-style slap to **{member.display_name}**!
║ 
║ 💥 Impact Force: Critical Hit
║ 😤 Drama Level: Maximum
║ 🎭 Anime Effect: Legendary
╚═══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Dramatic Action", description, discord.Color.from_rgb(255, 140, 0))
    embed.set_image(url=gif_url)
    embed.add_field(name="💫 Interaction Type", value="👋 **ANIME SLAP**", inline=True)
    embed.add_field(name="💥 Damage Dealt", value="📊 **999 Emotional DMG**", inline=True)
    embed.add_field(name="🎪 Drama Factor", value="🎭 **Soap Opera Level**", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def punch(ctx, member: discord.Member):
    """Punch another user with anime GIF"""
    gif_url = await get_anime_gif("punch")

    description = f"""
╔═══════════════════════════════════╗
║         👊 **POWER PUNCH** 👊         ║
╠═══════════════════════════════════╣
║ **{ctx.author.display_name}** unleashes an epic
║ anime punch on **{member.display_name}**!
║ 
║ ⚡ Power Level: Over 9000
║ 💥 Impact Rating: Devastating
║ 🥊 Fighting Style: Shonen Hero
╚═══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Battle Action", description, discord.Color.from_rgb(220, 20, 60))
    embed.set_image(url=gif_url)
    embed.add_field(name="💫 Interaction Type", value="👊 **SHONEN PUNCH**", inline=True)
    embed.add_field(name="⚡ Power Level", value="📊 **OVER 9000**", inline=True)
    embed.add_field(name="🔥 Fighting Spirit", value="🥊 **BURNING PASSION**", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def cuddle(ctx, member: discord.Member):
    """Cuddle with another user with anime GIF"""
    gif_url = await get_anime_gif("cuddle")

    description = f"""
╔═══════════════════════════════════╗
║         🥰 **SWEET CUDDLE** 🥰         ║
╠═══════════════════════════════════╣
║ **{ctx.author.display_name}** and **{member.display_name}**
║ share an adorable cuddling moment!
║ 
║ 💕 Cuteness Level: Maximum
║ 🌸 Comfort Rating: Perfect
║ 😌 Relaxation: Complete
╚═══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Cozy Moment", description, discord.Color.from_rgb(255, 192, 203))
    embed.set_image(url=gif_url)
    embed.add_field(name="💫 Interaction Type", value="🥰 **ADORABLE CUDDLE**", inline=True)
    embed.add_field(name="🌸 Comfort Level", value="📈 **+100 Coziness**", inline=True)
    embed.add_field(name="💤 Relaxation", value="😌 **Ultimate Peace**", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def pat(ctx, member: discord.Member):
    """Pat another user with anime GIF"""
    gif_url = await get_anime_gif("pat")

    description = f"""
╔═══════════════════════════════════╗
║          😊 **GENTLE PAT** 😊          ║
╠═══════════════════════════════════╣
║ **{ctx.author.display_name}** gives **{member.display_name}**
║ gentle, caring head pats!
║ 
║ 🌟 Kindness Level: Supreme
║ 💫 Pat Quality: Heavenly
║ 😇 Wholesome Factor: Maximum
╚═══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Caring Gesture", description, discord.Color.from_rgb(144, 238, 144))
    embed.set_image(url=gif_url)
    embed.add_field(name="💫 Interaction Type", value="😊 **HEADPAT SPECIAL**", inline=True)
    embed.add_field(name="🌟 Comfort Given", value="📈 **+75 Happiness**", inline=True)
    embed.add_field(name="👼 Wholesome Level", value="😇 **Angel Tier**", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def poke(ctx, member: discord.Member):
    """Poke another user with anime GIF"""
    gif_url = await get_anime_gif("poke")

    description = f"""
╔═══════════════════════════════════╗
║         👉 **PLAYFUL POKE** 👉         ║
╠═══════════════════════════════════╣
║ **{ctx.author.display_name}** playfully pokes
║ **{member.display_name}** to get attention!
║ 
║ 😆 Playfulness: Maximum
║ 🎮 Fun Factor: High
║ 😋 Mischief Level: Moderate
╚═══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Playful Action", description, discord.Color.from_rgb(135, 206, 250))
    embed.set_image(url=gif_url)
    embed.add_field(name="💫 Interaction Type", value="👉 **ATTENTION POKE**", inline=True)
    embed.add_field(name="😆 Fun Level", value="📈 **+25 Playfulness**", inline=True)
    embed.add_field(name="🎯 Poke Accuracy", value="🎪 **Bullseye Hit**", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def bite(ctx, member: discord.Member):
    """Bite another user with anime GIF"""
    gif_url = await get_anime_gif("bite")

    description = f"""
╔═══════════════════════════════════╗
║          🦷 **CUTE BITE** 🦷          ║
╠═══════════════════════════════════╣
║ **{ctx.author.display_name}** gives **{member.display_name}**
║ an adorable little anime bite!
║ 
║ 😸 Cuteness: Overwhelming
║ 🐱 Cat-like Behavior: Yes
║ 💕 Affection Level: High
╚═══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Adorable Action", description, discord.Color.from_rgb(138, 43, 226))
    embed.set_image(url=gif_url)
    embed.add_field(name="💫 Interaction Type", value="🦷 **KAWAII BITE**", inline=True)
    embed.add_field(name="😸 Cuteness Factor", value="📈 **+150 Adorable**", inline=True)
    embed.add_field(name="🐱 Animal Spirit", value="🦊 **Playful Fox**", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def tickle(ctx, member: discord.Member):
    """Tickle another user with anime GIF"""
    gif_url = await get_anime_gif("tickle")

    description = f"""
╔═══════════════════════════════════╗
║        😂 **TICKLE ATTACK** 😂        ║
╠═══════════════════════════════════╣
║ **{ctx.author.display_name}** launches a merciless
║ tickle attack on **{member.display_name}**!
║ 
║ 🤣 Laughter Induced: Maximum
║ 😆 Tickle Intensity: Extreme
║ 🎪 Fun Level: Through the roof
╚═══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Tickle War", description, discord.Color.from_rgb(255, 255, 0))
    embed.set_image(url=gif_url)
    embed.add_field(name="💫 Interaction Type", value="😂 **TICKLE ASSAULT**", inline=True)
    embed.add_field(name="🤣 Laughter Points", value="📈 **+200 Giggles**", inline=True)
    embed.add_field(name="🎭 Comedy Level", value="😆 **Stand-up Special**", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def fuck(ctx, member: discord.Member):
    """Adult action with another user with anime GIF"""
    gif_url = await get_anime_gif("anime nsfw")

    description = f"""
╔═══════════════════════════════════╗
║         🔞 **ADULT ACTION** 🔞         ║
╠═══════════════════════════════════╣
║ **{ctx.author.display_name}** and **{member.display_name}**
║ are having an intimate moment!
║ 
║ 💕 Passion Level: Intense
║ 🔥 Heat Rating: Maximum
║ 😳 Intensity: Extreme
╚═══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Adult Interaction", description, discord.Color.from_rgb(255, 69, 0))
    embed.set_image(url=gif_url)
    embed.add_field(name="💫 Interaction Type", value="🔞 **ADULT CONTENT**", inline=True)
    embed.add_field(name="🔥 Heat Level", value="📈 **+500 Passion**", inline=True)
    embed.add_field(name="💕 Romance Factor", value="😳 **Intimate Moment**", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def kick(ctx, member: discord.Member):
    """Kick another user with anime GIF"""
    gif_url = await get_anime_gif("anime kick")

    description = f"""
╔═══════════════════════════════════╗
║         🦵 **POWERFUL KICK** 🦵         ║
╠═══════════════════════════════════╣
║ **{ctx.author.display_name}** delivers a devastating
║ anime-style kick to **{member.display_name}**!
║ 
║ 💥 Impact Force: Devastating
║ ⚡ Kick Speed: Lightning Fast
║ 🥋 Fighting Style: Martial Arts Master
╚═══════════════════════════════════╝
"""

    embed = create_aesthetic_embed("Combat Action", description, discord.Color.from_rgb(255, 140, 0))
    embed.set_image(url=gif_url)
    embed.add_field(name="💫 Interaction Type", value="🦵 **MARTIAL ARTS KICK**", inline=True)
    embed.add_field(name="💥 Damage Dealt", value="📊 **1500 Physical DMG**", inline=True)
    embed.add_field(name="🥋 Technique", value="⚡ **LIGHTNING KICK**", inline=True)
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
║ **Your New Balance:** {max(0, user['balance'] - penalty):,} 💵
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
    {"q": "What is the largest mammal in the world?", "a": "blue whale", "reward": 200, "category": "N�ature"},
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
    {"q": "�I have a golden head and a golden tail, but no golden body. What am I?", "a": ["coin", "penny", "a coin"], "reward": 290, "difficulty": "Medium"},
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
            leveled_up, new_level = await �add_xp(ctx.author.id, xp_gained)
            
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
        return await ctx.send(embed=embed)
    
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
    embed = create_aesthetic_embed("📜 In�spirational Quote", f"║ {quote} ║", discord.Color.gold())
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
        embed.add_field(name="⚖️ Justice", �value="**SERVED**", inline=True)
        embed.add_field(name="🏥 Bail Cost", value=f"{penalty:,} 💵", inline=True)

    await ctx.send(embed=embed)

# Enhanced Help Command
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
        "💰 Economy": ["balance", "daily", "work", "crime", "hunt", "fish", "sell", "give", "top", "weekly", "monthly"],
        "🎮 Gambling": ["slots", "coinflip", "blackjack", "hit", "stand", "spin", "race", "duel"],
        "❤️ Social Actions": ["hug", "kiss", "slap", "cuddle", "pat", "poke", "punch", "bite", "tickle", "wave", "boop", "snuggle", "handhold", "greet", "bully", "protect", "feed", "fuck", "kick"],
        "💍 Marriage": ["marry", "propose", "acceptmarriage", "declinemarriage", "divorce"],
        "📊 Profile": ["profile", "setbio", "inventory", "level", "avatar", "ship", "leaderboard", "userinfo", "serverinfo"],
        "😊 Emotes": ["blush", "cry", "dance", "happy", "pout", "smile", "wag", "thinking", "grin"],
        "🎉 Fun & Games": ["meme", "cat", "dog", "eightball", "roll", "choose", "gif", "dinosaur", "flip", "unflip", "advice", "quote", "joke", "fact", "weather", "time", "truthordare", "roast", "compliment"],
        "🎯 Adventure": ["dig", "explore", "steal", "rob", "trivia", "riddle", "quest"],
        "🔧 Utility": ["ping", "invite", "stats", "math", "zoo", "dashboard", "help"]
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

    if user["last_hunt"] and (now - user["last_hunt"].replace(tzinfo=None))�.seconds < 300:
        remaining = 300 - (now - user["last_hunt"].replace(tzinfo=None)).seconds
        minutes = remaining // 60
        seconds = remaining % 60
        
        embed = create_aesthetic_embed("🏹 Bow Recharging", 
                                     f"║ Your hunting equipment needs maintenance! ║\n"
                                     f"║ Wait **{minutes}m {seconds}s** before hunting again ║",
                                     discord.Color.orange())
        embed.add_field(name="🎯 Hunter's Rest", value="⚡ Preparing for next expedition", inline=True)
        embed.add_field(name="⏰ Cooldown", value="5 minutes", inline=True)
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
    """View your animal collection"""
    member = member or ctx.author
    inventory = inventories.find_one({"_id": member.id})

    if not inventory or not inventory.get("items"):
        return await ctx.send(f"{member.display_name}'s zoo is empty!")

    animals = []
    for item_name, quantity in inventory["items"].items():
        if item_name in HUNT_ITEMS:
            animals.append(f"{HUNT_ITEMS[item_name]['emoji']} {item_name} x{quantity}")
        elif item_name in FISH_ITEMS:
            animals.append(f"{FISH_ITEMS[item_name]['emoji']} {item_name} x{quantity}")

    if not animals:
        return await ctx.send(f"{member.display_name} has no animals!")

    embed = discord.Embed(title=f"{member.display_name}'s Zoo", 
                         description="\n".join(animals), 
                         color=discord.Color.green())
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
    
�    await ctx.send(f"💸 {ctx.author.display_name} gave {amount} 💵 to {member.display_name}!")

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
        new_balance = user["balance"] + total_value
        await update_user_data(ctx.author.id, {"balance": new_balance})

        description = f"""
╔════════════════════════════════════╗
║        💰 **BULK SALE** 💰        ║
╠════════════════════════════════════╣
║ **Items Sold:** {len(sold_items)}
║ **Total Earned:** {total_value:,} 💵
║ **New Balance:** {new_balance:,} 💵
╠════════════════════════════════════╣
║ **SOLD ITEMS:**
║ {chr(10).join('║ ' + item for item in sold_items[:10])}
{f'║ ...and {len(sold_items) - 10} more items' if len(sold_items) > 10 else ''}
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Market Transaction", description, discord.Color.gold(), ctx.author.display_avatar.url)
        embed.add_field(name="💎 Transaction Type", value="**BULK SALE**", inline=True)
        embed.add_field(name="📊 Market Impact", value="**POSITIVE**", inline=True)
        embed.add_field(name="🎯 Efficiency", value="**MAXIMUM**", inline=True)
        return await ctx.send(embed=embed)

    else:
        # Sell specific item
        if len(parts) == 1:
            item = parts[0].lower()
            amount = 1
        elif len(parts) == 2:
            item = parts[0].lower()
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

        if not inventory or item not in inventory.get("items", {}):
            embed = create_aesthetic_embed("❌ Item Not Found", 
                                         f"║ You don't have any **{item}**! ║", 
                                         discord.Color.red())
            return await ctx.send(embed=embed)

        if inventory["items"][item] < amount:
            embed = create_aesthetic_embed("❌ Insufficient Quantity", 
                                         f"║ You only have **{inventory['items'][item]}** {item}(s)! ║", 
                                         �discord.Color.red())
            return await ctx.send(embed=embed)

        if item in HUNT_ITEMS:
            item_data = HUNT_ITEMS[item]
            value_per_item = item_data["value"]
            emoji = item_data["emoji"]
            rarity = item_data["type"]
        elif item in FISH_ITEMS:
            item_data = FISH_ITEMS[item]
            value_per_item = item_data["value"]
            emoji = item_data["emoji"]
            rarity = "aquatic"
        else:
            embed = create_aesthetic_embed("❌ Unsellable Item", 
                                         f"║ **{item}** cannot be sold! ║", 
                                         discord.Color.red())
            return await ctx.send(embed=embed)

        total_value = value_per_item * amount
        new_balance = user["balance"] + total_value

        await remove_item(ctx.author.id, item, amount)
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
║        🏪 **ITEM SOLD** 🏪        ║
╠════════════════════════════════════╣
║ **Item:** {emoji} **{item.title()}**
║ **Rarity:** {rarity_emoji} **{rarity.title()}**
║ **Quantity:** {amount}
║ **Price Each:** {value_per_item:,} 💵
║ **Total Earned:** {total_value:,} 💵
║ **New Balance:** {new_balance:,} 💵
╚════════════════════════════════════╝
"""

        embed = create_aesthetic_embed("Market Transaction", description, color, ctx.author.display_avatar.url)
        embed.add_field(name="💰 Transaction ID", value=f"#{random.randint(100000, 999999)}", inline=True)
        embed.add_field(name="📈 Market Value", value=f"{value_per_item:,} 💵", inline=True)
        embed.add_field(name="⏰ Timestamp", value=f"<t:{int(datetime.datetime.now().timestamp())}:R>", inline=True)
        
        return await ctx.send(embed=embed)

# Gambling commands
@bot.command()
async def slots(ctx, amount: int):
    """Play slots with your money"""
    user = await get_user_data(ctx.author.id)

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
    elif slots[0] == slots[1] or slots[1] == slots[2]:
        winnings = amount
        result = f"You won {winnings} 💵 (x1)"
    else:
        winnings = -amount
        result = f"You lost {amount} 💵"

    await update_user_data(ctx.author.id, {"balance": user["balance"] + winnings})
    await ctx.send(f"🎰 {' | '.join(slots)} 🎰\n{result}")

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
        return aw�ait ctx.send("You must bet a positive amount!")

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
    """View your or someone else's profile"""
    member = member or ctx.author
    user = awai�t get_user_data(member.id)

    embed = discord.Embed(title=f"{member.display_name}'s Profile", color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)

    embed.add_field(name="💰 Balance", value=f"{user['balance']} 💵", inline=True)
    embed.add_field(name="📊 Level", value=f"{user.get('level', 1)}", inline=True)
    embed.add_field(name="⭐ XP", value=f"{user.get('xp', 0)}", inline=True)
    embed.add_field(name="🏆 Rank", value=user.get('rank', 'Newbie'), inline=True)
    embed.add_field(name="📅 Daily Streak", value=user['daily_streak'], inline=True)

    # Calculate XP needed for next level
    current_level = user.get('level', 1)
    xp_needed = calculate_xp_for_level(current_level + 1) - user.get('xp', 0)
    embed.add_field(name="📈 XP to Next Level", value=f"{xp_needed}", inline=True)

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
                               �                   value=f"👍 {data.get('ups', 0):,} upvotes", 
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
            �    "limit": 20,  # Get multiple options
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
                                embed.add_field(name="🔗 View Original", 
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
async def stats(ctx):
    """Show bot statistics"""
    embed = discord.Embed(title="📊 Bot Statistics", color=discord.Color.blue())
    embed.add_field(name="Servers", value=len(bot.guilds), inline=True)
    embed.add_field(name="Users", value=len(bot.users), inline=True)
    embed.add_field(name="Commands", value=len(bot.commands), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def math(ctx, *, expression):
    """Calculate a math expression"""
    try:
        # Simple math evaluation (be careful with eval!)
        allowed_chars = "0123456789+-*/.() "
        if all(c in allowed_chars for c in expression):
            result = eval(expression)
            await ctx.send(f"🧮 {expression} = {result}")
        else:
            await ctx.send("❌ Invalid charac�ters in expression!")
    except:
        await ctx.send("❌ Invalid math expression!")



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

#Run the bot
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
            print(f"Star�ting bot (attempt {attempt + 1}/{max_retries})...")
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