import discord
from discord.ext import commands
from discord import app_commands
import json
import re
import os
from typing import Optional

class Trading(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.trades = {}
        
        values_path = "/home/container/cogs/values.json"
        if os.path.exists(values_path):
            with open(values_path, "r", encoding="utf-8") as f:
                self.values_data = json.load(f)
        else:
            self.values_data = {}
        
        self.all_items = []
        for group in ["items", "event_items", "miscellaneous_items", "kukri_items"]:
            if group in self.values_data:
                self.all_items.extend(list(self.values_data[group].keys()))

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
            if group in self.values_data and item_name in self.values_data[group]:
                return self.values_data[group][item_name]
        return None

    def get_item_category(self, item_name: str) -> Optional[str]:
        for group in ["items", "event_items", "miscellaneous_items", "kukri_items"]:
            if group in self.values_data and item_name in self.values_data[group]:
                return group
        return None

    def get_item_value(self, item_name: str, serial: int = None) -> int:
        item_data = self.get_item_data(item_name)
        if not item_data:
            raise ValueError("Item not found.")
        if "prices" in item_data:
            if serial is None:
                raise ValueError("A serial number must be provided for this item.")
            for price_obj in item_data["prices"]:
                r = price_obj["range"]
                lower_bound = min(r[0], r[1])
                upper_bound = max(r[0], r[1])
                if lower_bound <= serial <= upper_bound:
                    return self.parse_price_string(price_obj["price"])
            return self.parse_price_string(item_data["prices"][-1]["price"])
        elif "price" in item_data:
            return self.parse_price_string(item_data["price"])
        else:
            raise ValueError("No price information available.")

    async def autocomplete_items(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        suggestions = [
            app_commands.Choice(name=item, value=item)
            for item in self.all_items if current in item.lower()
        ]
        return suggestions[:25]

    def update_uses(self, user_id: str):
        uses_path = "/home/container/uses.json"
        try:
            with open(uses_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        if "trade_uses" not in data:
            data["trade_uses"] = 0
        data["trade_uses"] += 1
        if user_id in data:
            data[user_id] += 1
        else:
            data[user_id] = 1
        with open(uses_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    trade = app_commands.Group(name="trade", description="Trade commands")
    offer = app_commands.Group(name="offer", description="Add items or cash to your offer")
    counter = app_commands.Group(name="counter", description="Add items or cash to the counter offer")

    @trade.command(name="start", description="Start a trade")
    async def trade_start(self, interaction: discord.Interaction):
        
        blacklist_path = "/home/container/blacklist.json"
        try:
            with open(blacklist_path, "r", encoding="utf-8") as f:
                blacklist = json.load(f)
        except Exception:
            blacklist = []
        if str(interaction.user.id) in blacklist:
            embed = discord.Embed(
                title="Blacklisted! <a:warning:1337122473879277580>",
                description="You have been blacklisted. Open a ticket in [Gold Rush Trading](https://discord.gg/45J959xRzJ) to appeal.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        self.trades[interaction.user.id] = {
            "offer_items": [],
            "offer_cash": 0,
            "counter_items": [],
            "counter_cash": 0
        }
        embed = discord.Embed(
            title="Trade Started",
            description=("Trade started. Use `/offer item` and `/offer cash` to add items or cash to your offer.\n"
                         "Use `/counter item` and `/counter cash` to add items or cash to the counter offer.\n"
                         "Use `/trade end` to finish the trade."),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @trade.command(name="end", description="End the trade and display the result")
    async def trade_end(self, interaction: discord.Interaction):
        if interaction.user.id not in self.trades:
            embed = discord.Embed(
                title="Error",
                description="No active trade session found.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        session = self.trades.pop(interaction.user.id)
        offer_items = session["offer_items"]
        counter_items = session["counter_items"]
        offer_cash = session["offer_cash"]
        counter_cash = session["counter_cash"]

        offer_details = ""
        counter_details = ""
        total_offer_value = offer_cash
        total_counter_value = counter_cash

        for item in offer_items:
            try:
                value = self.get_item_value(item["name"], item["serial"])
            except Exception:
                value = 0
            total_offer_value += value
            note = " (high serial)" if item.get("auto_serial", False) else ""
            offer_details += f"\n> - **{item['name']}{note}** (value: {self.format_cash(value)})"
        if offer_cash:
            offer_details += f"\n> - **Cash:** {self.format_cash(offer_cash)}"

        for item in counter_items:
            try:
                value = self.get_item_value(item["name"], item["serial"])
            except Exception:
                value = 0
            total_counter_value += value
            note = " (high serial)" if item.get("auto_serial", False) else ""
            counter_details += f"\n> - **{item['name']}{note}** (value: {self.format_cash(value)})"
        if counter_cash:
            counter_details += f"\n> - **Cash:** {self.format_cash(counter_cash)}"

        result_embed = discord.Embed(
            title="Trade Result <a:trade:1337503184444330025>",
            description=(f"**Your offer:**{offer_details}\n\n"
                         f"**Counter offer:**{counter_details}"),
            color=discord.Color.blue()
        )
        result_embed.set_footer(text="Powered by Gold Rush Trading", icon_url="https://discord.gg/45J959xRzJ")
        await interaction.response.send_message(embed=result_embed)

        if total_counter_value > total_offer_value:
            diff = total_counter_value - total_offer_value
            ansi_message = (
                "```ansi\n"
                "\u001b[1;2mResult:\n"
                "\u001b[0;2m\u001b[1;32mWin by " + self.format_cash(diff) +
                "\u001b[0m\n"
                "```"
            )
        elif total_counter_value < total_offer_value:
            diff = total_offer_value - total_counter_value
            ansi_message = (
                "```ansi\n"
                "\u001b[1;2mResult:\n"
                "\u001b[1;31mLose by " + self.format_cash(diff) +
                "\u001b[0m\n"
                "```"
            )
        else:
            ansi_message = (
                "```ansi\n"
                "\u001b[1;2mResult:\n"
                "\u001b[1;33mTie - Both offers are equal\u001b[0m\n"
                "```"
            )
        await interaction.followup.send(ansi_message)
        self.update_uses(str(interaction.user.id))

    @offer.command(name="item", description="Add an item to your offer")
    async def offer_item(self, interaction: discord.Interaction, item: str, serial: Optional[int] = None):
        if interaction.user.id not in self.trades:
            embed = discord.Embed(
                title="Error",
                description="No active trade session found. Start a trade using `/trade start`.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        category = self.get_item_category(item)
        if not category:
            embed = discord.Embed(
                title="Error",
                description="The specified item was not found.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if category in ["event_items", "miscellaneous_items"]:
            if serial is not None:
                embed = discord.Embed(
                    title="Error",
                    description="You cannot add a serial for an event/miscellaneous item.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            serial_value = None
            auto_serial = False
        elif category in ["items", "kukri_items"]:
            if serial is None:
                serial_value = 75000
                auto_serial = True
            else:
                serial_value = serial
                auto_serial = False
        else:
            embed = discord.Embed(
                title="Error",
                description="Unknown item category.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        self.trades[interaction.user.id]["offer_items"].append({
            "name": item,
            "serial": serial_value,
            "auto_serial": auto_serial
        })
        note_text = " (high serial)" if auto_serial else ""
        embed = discord.Embed(
            title="Item Added",
            description=f"{item}{note_text} with serial {serial_value if serial_value is not None else 'N/A'} has been added to your offer.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @offer_item.autocomplete("item")
    async def offer_item_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.autocomplete_items(interaction, current)

    @offer.command(name="cash", description="Add cash to your offer")
    async def offer_cash(self, interaction: discord.Interaction, amount: str):
        if interaction.user.id not in self.trades:
            embed = discord.Embed(
                title="Error",
                description="No active trade session found. Start a trade using `/trade start`.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        try:
            cash_value = self.parse_cash(amount)
        except ValueError as e:
            embed = discord.Embed(title="Error", description=str(e), color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        self.trades[interaction.user.id]["offer_cash"] += cash_value
        embed = discord.Embed(
            title="Cash Added",
            description=f"{self.format_cash(cash_value)} has been added to your offer.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @counter.command(name="item", description="Add an item to the counter offer")
    async def counter_item(self, interaction: discord.Interaction, item: str, serial: Optional[int] = None):
        if interaction.user.id not in self.trades:
            embed = discord.Embed(
                title="Error",
                description="No active trade session found. Start a trade using `/trade start`.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        category = self.get_item_category(item)
        if not category:
            embed = discord.Embed(
                title="Error",
                description="The specified item was not found.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if category in ["event_items", "miscellaneous_items"]:
            if serial is not None:
                embed = discord.Embed(
                    title="Error",
                    description="You cannot add a serial for an event/miscellaneous item.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            serial_value = None
            auto_serial = False
        elif category in ["items", "kukri_items"]:
            if serial is None:
                serial_value = 75000
                auto_serial = True
            else:
                serial_value = serial
                auto_serial = False
        else:
            embed = discord.Embed(
                title="Error",
                description="Unknown item category.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        self.trades[interaction.user.id]["counter_items"].append({
            "name": item,
            "serial": serial_value,
            "auto_serial": auto_serial
        })
        note_text = " (high serial)" if auto_serial else ""
        embed = discord.Embed(
            title="Item Added",
            description=f"{item}{note_text} with serial {serial_value if serial_value is not None else 'N/A'} has been added to the counter offer.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @counter_item.autocomplete("item")
    async def counter_item_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.autocomplete_items(interaction, current)

    @counter.command(name="cash", description="Add cash to the counter offer")
    async def counter_cash(self, interaction: discord.Interaction, amount: str):
        if interaction.user.id not in self.trades:
            embed = discord.Embed(
                title="Error",
                description="No active trade session found. Start a trade using `/trade start`.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        try:
            cash_value = self.parse_cash(amount)
        except ValueError as e:
            embed = discord.Embed(title="Error", description=str(e), color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        self.trades[interaction.user.id]["counter_cash"] += cash_value
        embed = discord.Embed(
            title="Cash Added",
            description=f"{self.format_cash(cash_value)} has been added to the counter offer.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Trading(bot))

