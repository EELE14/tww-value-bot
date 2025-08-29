import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
import time
import asyncio
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict

VALUES_FILE = "/home/container/cogs/values.json"
USES_FILE = "/home/container/uses.json"
BLACKLIST_FILE = "/home/container/blacklist.json"
ADMIN_FILE = "/home/container/admin.json"
IGNORED_CHANNELS_FILE = "/home/container/ignoredchannel.json"

def load_json(filepath: str):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_json(filepath: str, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

class MessageDetection(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.values_data = load_json(VALUES_FILE)
        
        self.all_items = []
        for group in ["items", "event_items", "miscellaneous_items", "kukri_items"]:
            if group in self.values_data:
                self.all_items.extend(list(self.values_data[group].keys()))

        self.alias_mapping = {
            
            "lanc": "Lancaster Pistol",
            "lancaster": "Lancaster Pistol",
            "proto": "Prototype Pistol",
            "prototype": "Prototype Pistol",
            "schwarzlose": "Prototype Pistol",
            "spit": "Spitfire Revolving Sniper",
            "spitfire": "Spitfire Revolving Sniper",
            "pat": "Paterson Navy",
            "patterson navy": "Paterson Navy",
            "paterson": "Paterson Navy",
            "patterson": "Paterson Navy",
            "axegonne": "Admirals Axegonne",
            "axegun": "Admirals Axegonne",
            "admirals axe": "Admirals Axegonne",
            "guycot carbine": "Guycot Chain Carbine",
            "gcc": "Guycot Chain Carbine",
            "guycot pistol": "Guycot Chain Pistol",
            "gcp": "Guycot Chain Pistol",
            
            "frozen volc": "Frozen Volcanic Rifle",
            "frozen rifle": "Frozen Volcanic Rifle",
            "frozen volcanic": "Frozen Volcanic Rifle",
            "pile of bones": "Pile of Bones 1-30 (Per stack)",
            "pile of bones 1-30": "Pile of Bones 1-30 (Per stack)",
            "pile of bones 30-50": "Pile of Bones 31-50 (Per stack)",
            "cursed": "Cursed Volcanic Pistol",
            "cursed volc": "Cursed Volcanic Pistol",
            "cursed volcanic": "Cursed Volcanic Pistol",
            "cursed pistol": "Cursed Volcanic Pistol",
            "skull lantern": "Cursed Lantern",
            "cursed lamp": "Cursed Lantern",
            "occult lamp": "Occult Lantern",
            "purple lantern": "Occult Lantern",
            "purple lamp": "Occult Lantern",
            "occult sawed": "Occult Sawed Off",
            "occult pistol": "Occult Sawed Off",
            "occult saw": "Occult Sawed Off",
            "mule rifle": "Occult Mule",
            "dagger": "Ceremonial Dagger",
            "zombie pelt": "Zombie Bear Pelt",
            "vial": "Any Vials",
            "vials": "Any Vials",
            "frozen bow": "Frozen Horn Bow",
            "skeleton skull": "Skeleton Horse Parts (Per part)",
            "skeleton part": "Skeleton Horse Parts (Per part)",
            "skeleton parts": "Skeleton Horse Parts (Per part)",
            "skeleton horse": "Skeleton Horse Parts (Per part)",
            "santas presents": "Stolen Presents (each)",
            "presents": "Stolen Presents (each)",
            "christmas cookie": "Christmas Cookies (Per stack)",
            "cookie": "Christmas Cookies (Per stack)",
            "candy cane": "Candy Canes (each)",
            "candy canes": "Candy Canes (each)",
            "polar bear": "Polar Bear Pelt",
            "polar pelt": "Polar Bear Pelt",
            "relic": "Ancient Relic",
            "relict": "Ancient Relic",
            "ancient relict": "Ancient Relic",
            "frosty gun barrel": "Frosty Gun Parts (all of them)",
            "frosty gun body": "Frosty Gun Parts (all of them)",
            "frosty gun parts": "Frosty Gun Parts (all of them)",
            "frosty gun part": "Frosty Gun Parts (all of them)",
            "frozen gun part": "Frosty Gun Parts (all of them)",
            "frozen gun barrel": "Frosty Gun Parts (all of them)",
            "frozen gun": "Frosty Gun Parts (all of them)",
            "frozen gun body": "Frosty Gun Parts (all of them)",
            "santa lantern": "Santa's Lantern",
            "santas lantern": "Santa's Lantern",
            "christmas lantern": "Santa's Lantern",
            "volcanic rifle": "Frozen Volcanic Rifle",
            
            "gun barrel": "Damaged Gun Barrel",
            "damaged barrel": "Damaged Gun Barrel",
            "damaged parts": "Damaged Gun Parts",
            "gun parts": "Damaged Gun Parts",
            "damaged body": "Damaged Gun Body",
            "gun body": "Damaged Gun Body",
            "old boot": "An Old Boot",
            "boot": "An Old Boot",
            "tlog": "Thunderstruck Log",
            "tcactus": "Thunderstruck Cactus Juice",
            "tcacti": "Thunderstruck Cactus Juice",
            "martini": "Martini (full set)",
            "martini henry": "Martini (full set)",
            "gunbody": "Damaged Gun Body"
        }

        ignored = load_json(IGNORED_CHANNELS_FILE)
        self.ignored_channels = ignored if isinstance(ignored, list) else []

        self.pending_serial: Dict[Tuple[int, int], dict] = {}

        self.last_bot_message_time = 0
        self.cooldowns: Dict[Tuple[int, str], float] = {}

    async def safe_send(self, channel: discord.TextChannel, content=None, **kwargs):
        msg = await channel.send(content, **kwargs)
        self.last_bot_message_time = time.time()
        return msg

    def parse_cash(self, cash_str: str) -> int:
        cash_str = cash_str.strip().lower()
        match = re.match(r'^(\d+(?:\.\d+)?)([km]?)$', cash_str)
        if not match:
            raise ValueError("Invalid cash amount. Use e.g. 200k or 2M.")
        number = float(match.group(1))
        suffix = match.group(2)
        if suffix == "k":
            return int(number * 1000)
        elif suffix == "m":
            return int(number * 1000000)
        else:
            return int(number)

    def format_cash(self, amount: int) -> str:
        if amount >= 1000000:
            s = f"{amount/1000000:.1f}M"
            return s.rstrip("0").rstrip(".")
        elif amount >= 1000:
            return f"{amount/1000:.0f}k"
        else:
            return str(amount)

    def parse_price_string(self, price_str: str) -> int:
        if "-" in price_str:
            parts = price_str.split("-")
            if len(parts) != 2:
                raise ValueError("Invalid price range.")
            first, second = parts[0].strip(), parts[1].strip()
            if not re.search(r"[km]$", first) and re.search(r"[km]$", second):
                suffix = re.search(r"([km])$", second).group(1)
                first += suffix
            val1 = self.parse_cash(first)
            val2 = self.parse_cash(second)
            return (val1 + val2) // 2
        else:
            return self.parse_cash(price_str)

    def get_item_data(self, item_name: str):
        for group in ["items", "event_items", "miscellaneous_items", "kukri_items"]:
            if group in self.values_data and item_name in self.values_data[group]:
                return self.values_data[group][item_name]
        return None

    def get_item_category(self, item_name: str) -> Optional[str]:
        for group in ["items", "event_items", "miscellaneous_items", "kukri_items"]:
            if group in self.values_data and item_name in self.values_data[group]:
                return group
        return None

    def get_item_value(self, item_name: str, serial: Optional[int] = None) -> int:
        item_data = self.get_item_data(item_name)
        if not item_data:
            raise ValueError("Item not found.")
        if "prices" in item_data:
            if serial is None:
                raise ValueError("A serial number is required for this item.")
            for price_obj in item_data["prices"]:
                r = price_obj["range"]
                lower_bound, upper_bound = min(r[0], r[1]), max(r[0], r[1])
                if lower_bound <= serial <= upper_bound:
                    return self.parse_price_string(price_obj["price"])
            raise ValueError("Serial number out of range.")
        elif "price" in item_data:
            return self.parse_price_string(item_data["price"])
        else:
            raise ValueError("No price information available.")

    def update_total_uses(self):
        data = load_json(USES_FILE)
        data["total_uses"] = data.get("total_uses", 0) + 1
        save_json(USES_FILE, data)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        
        if message.author.bot:
            return
        if time.time() - self.last_bot_message_time < 5:
            return
        if message.channel.id in self.ignored_channels:
            return

        key = (message.author.id, message.channel.id)
        if key in self.pending_serial:
            serial_text = message.content.strip().lstrip("
            try:
                serial = int(serial_text)
            except ValueError:
                return
            pending = self.pending_serial.pop(key)
            try:
                value = self.get_item_value(pending["item"], serial)
            except Exception as e:
                await self.safe_send(message.channel, f"Error: {e} \n-
                return

            item_data = self.get_item_data(pending["item"])
            response = (
                f"__**{pending['item']}**__\n"
                f"- Value (Serial 
                f"- Demand: {item_data['demand']}\n"
                f"- Stability: {item_data['stability']}"
            )
            await self.safe_send(message.channel, response)
            self.update_total_uses()
            return

        content_lower = message.content.lower()
        found_item = None
        for item in self.all_items:
            if item.lower() in content_lower:
                found_item = item
                break
        if not found_item:
            for alias, canonical in self.alias_mapping.items():
                if alias in content_lower:
                    found_item = canonical
                    break

        if found_item:
            category = self.get_item_category(found_item)
            item_data = self.get_item_data(found_item)

            if category in ["items", "kukri_items"]:
                match = re.search(r"(?:
                if match:
                    serial = int(match.group(1))
                    try:
                        value = self.get_item_value(found_item, serial)
                    except Exception as e:
                        await self.safe_send(message.channel, f"Error: {e} \n-
                        return

                    response = (
                        f"__**{found_item}**__\n"
                        f"- Value (Serial 
                        f"- Demand: {item_data['demand']}\n"
                        f"- Stability: {item_data['stability']}"
                    )
                    await self.safe_send(message.channel, response)
                    self.update_total_uses()
                else:
                    await self.safe_send(message.channel, f"Please specify a serial for `{found_item}` **below**!\n-
                    self.pending_serial[key] = {"item": found_item, "category": category}

            elif category in ["event_items", "miscellaneous_items"]:
                try:
                    value = self.get_item_value(found_item, None)
                except Exception as e:
                    await self.safe_send(message.channel, f"Error: {e}")
                    return

                response = (
                    f"__**{found_item}**__\n"
                    f"- Value: {self.format_cash(value)}\n"
                    f"- Demand: {item_data['demand']}\n"
                    f"- Stability: {item_data['stability']}"
                )
                await self.safe_send(message.channel, response)
                self.update_total_uses()

        await self.bot.process_commands(message)

    async def handle_ignorechannel(self, message: discord.Message):
        parts = message.content.split()
        if len(parts) < 2:
            await self.safe_send(message.channel, "Usage: !ignorechannel {channel_id}")
            return
        try:
            channel_id = int(parts[1])
        except ValueError:
            await self.safe_send(message.channel, "Invalid channel ID.")
            return
        is_owner = message.guild and message.guild.owner_id == message.author.id
        admin_data = load_json(ADMIN_FILE)
        admin_ids = list(admin_data.keys()) if isinstance(admin_data, dict) else (admin_data if isinstance(admin_data, list) else [])
        if not (is_owner or str(message.author.id) in admin_ids):
            await self.safe_send(message.channel, "You do not have permission to use this command.")
            return
        if channel_id not in self.ignored_channels:
            self.ignored_channels.append(channel_id)
            save_json(IGNORED_CHANNELS_FILE, self.ignored_channels)
            await self.safe_send(message.channel, f"Channel {channel_id} is now ignored.")
        else:
            await self.safe_send(message.channel, f"Channel {channel_id} is already ignored.")

async def setup(bot: commands.Bot):
    await bot.add_cog(MessageDetection(bot))
