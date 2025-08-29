import json
import os
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import re
from typing import Optional, Dict, Any

VALUES_FILE = "/home/container/cogs/values.json"
USES_FILE = "/home/container/uses.json"
PRIVATE_FILE = "/home/container/private.json"
BLACKLIST_FILE = "/home/container/blacklist.json"

class Values(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.item_data = self.load_json(VALUES_FILE)
        self.special_serials = {69420, 420, 42069, 69, 6969, 696969, 420420}
        self.low_serial_threshold = 100

    def load_json(self, path: str) -> Dict[str, Any]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def save_json(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def update_total_uses(self, user_id: int):
        data = self.load_json(USES_FILE)
        if "total_uses" not in data:
            data["total_uses"] = 0
        data["total_uses"] += 1
        
        if str(user_id) in data:
            data[str(user_id)] += 1
        else:
            data[str(user_id)] = 1
        self.save_json(USES_FILE, data)

    def check_blacklist(self, user_id):
        data = self.load_json(BLACKLIST_FILE)
        return str(user_id) in data and data[str(user_id)]

    def check_private(self, user_id):
        data = self.load_json(PRIVATE_FILE)
        return data.get(str(user_id), {}).get("private", False)

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

    def parse_price_string(self, price_str: str) -> int:
        
        if "-" in price_str:
            parts = price_str.split("-")
            if len(parts) != 2:
                raise ValueError("Invalid price range.")
            first = parts[0].strip()
            second = parts[1].strip()
            if not re.search(r"[km]$", first) and re.search(r"[km]$", second):
                suffix = re.search(r"([km])$", second).group(1)
                first += suffix
            val1 = self.parse_cash(first)
            val2 = self.parse_cash(second)
            return (val1 + val2) // 2
        else:
            return self.parse_cash(price_str)

    def format_cash(self, amount: int) -> str:
        
        if amount >= 1000000:
            s = f"{amount/1000000:.1f}M"
            return s.rstrip("0").rstrip(".")
        elif amount >= 1000:
            return f"{amount/1000:.0f}k"
        else:
            return str(amount)

    def get_item_data(self, item_name: str):
        
        for group in ["items", "event_items", "miscellaneous_items", "kukri_items"]:
            if group in self.item_data and item_name in self.item_data[group]:
                return self.item_data[group][item_name]
        return None

    def get_item_category(self, item_name: str) -> Optional[str]:
        
        for group in ["items", "event_items", "miscellaneous_items", "kukri_items"]:
            if group in self.item_data and item_name in self.item_data[group]:
                return group
        return None

    def get_item_value(self, item_name, serial=None):

        item_data = self.get_item_data(item_name)
        if not item_data:
            raise ValueError("Item not found.")
        if "prices" in item_data:
            if serial is None:
                return (self.parse_price_string(item_data["prices"][0]["price"]),
                        item_data["demand"],
                        item_data["stability"],
                        True)
            for price_obj in item_data["prices"]:
                r = price_obj["range"]
                lower_bound = min(r[0], r[1])
                upper_bound = max(r[0], r[1])
                if lower_bound <= serial <= upper_bound:
                    return (self.parse_price_string(price_obj["price"]),
                            item_data["demand"],
                            item_data["stability"],
                            False)
            raise ValueError("Serial number out of range.")
        elif "price" in item_data:
            return (self.parse_price_string(item_data["price"]),
                    item_data.get("demand", "Unknown"),
                    item_data.get("stability", "Unknown"),
                    False)
        else:
            raise ValueError("No price information available.")

    async def autocomplete_items(self, interaction: discord.Interaction, current: str):
        all_items = [item for category in self.item_data.values() for item in category.keys()]
        filtered_items = [app_commands.Choice(name=item, value=item) for item in all_items if current.lower() in item.lower()]
        return filtered_items[:25]

    def check_special_serial(self, serial):
        serial_str = str(serial)
        if serial in self.special_serials or (len(serial_str) > 1 and serial_str[1:] == "0" * (len(serial_str) - 1)) or all(digit == serial_str[0] for digit in serial_str):
            return "This is a special serial and may receive overpays!"
        if serial < self.low_serial_threshold:
            return "This is a low serial and may receive overpays!"
        return None

    @commands.command(name="value")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def value_command(self, ctx, *args):
        if len(args) < 1:
            await ctx.send("Usage: !value <item name> [serial number]")
            return
        
        item = " ".join(args[:-1]) if len(args) > 1 and args[-1].isdigit() else " ".join(args)
        serial = int(args[-1]) if len(args) > 1 and args[-1].isdigit() else None
        if self.check_blacklist(ctx.author.id):
            embed = discord.Embed(title="Blacklisted! <a:warning:1337122473879277580>",
                                  description="You are blacklisted from this command and are not able to use it!",
                                  color=discord.Color.red())
            embed.set_footer(text="Appeal at [Gold Rush Trading](https://discord.gg/45J959xRzJ) [tickets](https://discord.com/channels/1310977344076251176/1311033788473671690)")
            try:
                await ctx.send(embed=embed, ephemeral=self.check_private(ctx.author.id))
            except TypeError:
                await ctx.send(embed=embed)
            return
        ephemeral = self.check_private(ctx.author.id)
        try:
            result = self.get_item_value(item, serial)
        except ValueError as e:
            await ctx.send(str(e))
            return
        if result == "No serial supported":
            try:
                await ctx.send(f"<:error:1337123835253751968> {item} does not support serial numbers.", ephemeral=ephemeral)
            except TypeError:
                await ctx.send(f"<:error:1337123835253751968> {item} does not support serial numbers.")
            return
        if isinstance(result, tuple) and len(result) == 4:
            value, demand, stability, high_serial = result
        else:
            value, demand, stability = result
            high_serial = False
        title = f"{item} - {serial if serial is not None else 'High serial'}"
        embed = discord.Embed(title=title, color=discord.Color.green())
        embed.add_field(name="<a:value:1337535946580562014> Value", value=self.format_cash(value), inline=False)
        embed.add_field(name="<a:demand:1337535929790894120> Demand", value=demand, inline=False)
        embed.add_field(name="<:moneymoneymoney:1342639154307137617> Stability", value=stability, inline=False)
        if high_serial:
            embed.set_footer(text="High serial")
        else:
            special_warning = self.check_special_serial(serial) if serial is not None else None
            if special_warning:
                embed.set_footer(text=special_warning)
        self.update_total_uses(ctx.author.id)
        try:
            await ctx.send(embed=embed, ephemeral=ephemeral)
        except TypeError:
            await ctx.send(embed=embed)
    
    @value_command.error
    async def value_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            msg = await ctx.send(f"Please wait {round(error.retry_after, 1)} seconds before using this command again.", delete_after=1)
        else:
            raise error

    @app_commands.command(name="value", description="Get the value of an item (serial optional)")
    @app_commands.autocomplete(item=autocomplete_items)
    async def value_slash_command(self, interaction: discord.Interaction, item: str, serial: int = None):

        category = self.get_item_category(item)
        if category in ["event_items", "miscellaneous_items"]:
            if serial is not None:
                await interaction.response.send_message("No serials applicable for that item.", ephemeral=True)
                return
            
            serial = None

        if self.check_blacklist(interaction.user.id):
            embed = discord.Embed(title="Blacklisted! <a:warning:1337122473879277580>",
                                  description="You are blacklisted from this command and are not able to use it!",
                                  color=discord.Color.red())
            embed.set_footer(text="Appeal at [Gold Rush Trading](https://discord.gg/45J959xRzJ)[tickets](https://discord.com/channels/1310977344076251176/1311033788473671690)")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        ephemeral = self.check_private(interaction.user.id)
        try:
            result = self.get_item_value(item, serial)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        if result == "No serial supported":
            await interaction.response.send_message(f"<:error:1337123835253751968> {item} does not support serial numbers.", ephemeral=ephemeral)
            return
        if isinstance(result, tuple) and len(result) == 4:
            value, demand, stability, high_serial = result
        else:
            value, demand, stability = result
            high_serial = False

        if category in ["event_items", "miscellaneous_items"]:
            title = f"{item}"
        else:
            title = f"{item} - {serial if serial is not None else 'High serial'}"
        embed = discord.Embed(title=title, color=discord.Color.green())
        embed.add_field(name="<a:value:1337535946580562014> Value", value=self.format_cash(value), inline=False)
        embed.add_field(name="<a:demand:1337535929790894120> Demand", value=demand, inline=False)
        embed.add_field(name="<:moneymoneymoney:1342639154307137617> Stability", value=stability, inline=False)
        if category not in ["event_items", "miscellaneous_items"]:
            if high_serial:
                embed.set_footer(text="High serial")
            else:
                special_warning = self.check_special_serial(serial) if serial is not None else None
                if special_warning:
                    embed.set_footer(text=special_warning)
        self.update_total_uses(interaction.user.id)
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

        if interaction.guild is not None and interaction.guild.id != 1310977344076251176:
            if interaction.user.id != interaction.guild.owner_id:
                followup_text = (
                    "
                    "Interested in an **auction tracker**?"
                    "Make sure to join the main server then! https://discord.gg/45J959xRzJ"
                )
                await interaction.followup.send(followup_text, ephemeral=True)

    @commands.command(name="myuses")
    async def myuses_command(self, ctx):
        data = self.load_json(USES_FILE)
        user_uses = data.get(str(ctx.author.id), 0)
        await ctx.send(f"You have used the bot {user_uses} times.")
    
    @commands.command(name="uses")
    async def uses_command(self, ctx):
        data = self.load_json(USES_FILE)
        total_uses = data.get("total_uses", 0)
        await ctx.send(f"The value command has been used {total_uses} times in total.")              

async def setup(bot: commands.Bot):
    await bot.add_cog(Values(bot))

    