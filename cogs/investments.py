import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional, List

INVESTMENTS_FILE = "/home/container/investments.json"
USES_FILE = "/home/container/uses.json"
BLACKLIST_FILE = "/home/container/blacklist.json"
VALUES_FILE = "/home/container/cogs/values.json"

def load_json(filepath: str):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_json(filepath: str, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


class InvestmentSelectView(discord.ui.View):
    def __init__(self, investments: List[dict], callback):
        super().__init__(timeout=60)
        self.investments = investments
        self.callback = callback
        for idx, inv in enumerate(investments[:5], start=1):
            button = discord.ui.Button(label=str(idx), style=discord.ButtonStyle.primary)
            button.custom_id = str(idx)
            button.callback = self.generate_callback(idx - 1)
            self.add_item(button)
    def generate_callback(self, index: int):
        async def button_callback(interaction: discord.Interaction):
            await self.callback(interaction, self.investments[index])
            self.stop()
        return button_callback

class Investments(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if os.path.exists(VALUES_FILE):
            with open(VALUES_FILE, "r", encoding="utf-8") as f:
                self.values_data = json.load(f)
        else:
            self.values_data = {}
        self.all_items = []
        for group in ["items", "event_items", "miscellaneous_items", "kukri_items"]:
            if group in self.values_data:
                self.all_items.extend(list(self.values_data[group].keys()))
    def parse_cash(self, cash_str: str) -> int:
        cash_str = cash_str.strip().lower()
        match = re.match(r'^(\\d+(?:\.\d+)?)([km]?)$', cash_str)
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
    def get_item_value(self, item_name: str, serial: int) -> int:
        item_data = self.get_item_data(item_name)
        if not item_data:
            raise ValueError("Item not found.")
        if "prices" in item_data:
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
    def load_investments(self) -> dict:
        data = load_json(INVESTMENTS_FILE)
        return data
    def save_investments(self, data: dict):
        save_json(INVESTMENTS_FILE, data)
    def update_investment_uses(self, user_id: str):
        data = load_json(USES_FILE)
        if "investement_uses" not in data:
            data["investement_uses"] = 0
        data["investement_uses"] += 1
        if user_id in data:
            data[user_id] += 1
        else:
            data[user_id] = 1
        save_json(USES_FILE, data)
    async def invest_item_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        suggestions = [
            app_commands.Choice(name=item, value=item)
            for item in self.all_items if current in item.lower()
        ]
        return suggestions[:25]
    async def invest_sell_autocomplete(self, interaction: discord.Interaction, current: str):
        investments = self.load_investments().get(str(interaction.user.id), [])
        items = list({inv["item"] for inv in investments})
        suggestions = [
            app_commands.Choice(name=item, value=item)
            for item in items if current.lower() in item.lower()
        ]
        return suggestions[:25]
    investment = app_commands.Group(name="investement", description="Investment commands")
    @investment.command(name="add", description="Add a personal investment")
    @app_commands.describe(item="Select an item", price="Purchase price (e.g. 200k or 2M)", serial="Serial number")
    @app_commands.autocomplete(item=invest_item_autocomplete)
    async def invest_add(self, interaction: discord.Interaction, item: str, price: str, serial: int):
        blacklist = load_json(BLACKLIST_FILE)
        if str(interaction.user.id) in blacklist:
            embed = discord.Embed(
                title="Error",
                description="You are blacklisted.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        inv_data = self.load_investments()
        user_inv = inv_data.get(str(interaction.user.id), [])
        today = datetime.now(timezone.utc).date().isoformat()
        daily_count = sum(1 for inv in user_inv if inv["date"][:10] == today)
        if daily_count >= 3:
            await interaction.response.send_message(
                "To prevent spam we only allow a maximum amount of three daily investments.",
                ephemeral=True
            )
            return
        try:
            purchase_price = self.parse_cash(price)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        try:
            current_value = self.get_item_value(item, serial)
        except Exception as e:
            await interaction.response.send_message(f"Error retrieving item value: {e}", ephemeral=True)
            return
        diff = purchase_price - current_value
        percentage = (abs(diff) / current_value) * 100 if current_value != 0 else 0
        direction = "higher" if diff > 0 else "lower" if diff < 0 else "equal"
        now_iso = datetime.now(timezone.utc).isoformat()
        new_inv = {
            "item": item,
            "serial": serial,
            "date": now_iso,
            "price": purchase_price
        }
        user_inv.append(new_inv)
        inv_data[str(interaction.user.id)] = user_inv
        self.save_investments(inv_data)
        self.update_investment_uses(str(interaction.user.id))
        response_msg = (f"Added `{item}` for `{self.format_cash(purchase_price)}`. This is "
                        f"{'+' if diff > 0 else '-'}{round(percentage)}% "
                        f"{direction} than the current value of `{self.format_cash(current_value)}`.")
        await interaction.response.send_message(response_msg, ephemeral=True)
    @investment.command(name="sell", description="Sell one of your investments")
    @app_commands.describe(item="Select the item to sell", serial="Optional serial (if needed)", sell_price="Optional sell price (e.g. 200k or 2M)")
    @app_commands.autocomplete(item=invest_sell_autocomplete)
    async def invest_sell(self, interaction: discord.Interaction, item: str, serial: Optional[int] = None, sell_price: Optional[str] = None):
        user_id = str(interaction.user.id)
        inv_data = self.load_investments()
        user_inv = inv_data.get(user_id, [])
        matching = [inv for inv in user_inv if inv["item"].lower() == item.lower()]
        if serial is not None:
            matching = [inv for inv in matching if inv["serial"] == serial]
        if not matching:
            await interaction.response.send_message("No matching investment found.", ephemeral=True)
            return
        async def finalize_sale(inter: discord.Interaction, chosen_inv: dict):
            if sell_price is not None:
                try:
                    sell_value = self.parse_cash(sell_price)
                except ValueError as e:
                    await inter.response.send_message(f"Invalid sell price: {e}", ephemeral=True)
                    return
            else:
                try:
                    sell_value = self.get_item_value(chosen_inv["item"], chosen_inv["serial"])
                except Exception as e:
                    await inter.response.send_message(f"Error retrieving current value: {e}", ephemeral=True)
                    return
            buy_value = chosen_inv["price"]
            percent_change = ((sell_value - buy_value) / buy_value) * 100 if buy_value != 0 else 0
            percent_text = f"{'+' if percent_change > 0 else ''}{round(percent_change)}%"
            result_text = "Win" if percent_change > 0 else "Lose" if percent_change < 0 else "No change"
            try:
                purchase_date = datetime.fromisoformat(chosen_inv["date"])
            except Exception:
                purchase_date = datetime.now(timezone.utc)
            held_days = (datetime.now(timezone.utc) - purchase_date).days
            if held_days < 1:
                held_days = 1
            try:
                current_value = self.get_item_value(chosen_inv["item"], chosen_inv["serial"])
            except Exception:
                current_value = 0
            embed = discord.Embed(
                title="Investement Sold <a:success:1337122638388269207>",
                color=discord.Color.blue()
            )
            embed.add_field(name="Item", value=chosen_inv["item"], inline=False)
            embed.add_field(name="Bought for", value=self.format_cash(buy_value), inline=True)
            embed.add_field(name="Sold for", value=self.format_cash(sell_value), inline=True)
            embed.add_field(name="Result", value=f"{result_text} ({percent_text})", inline=False)
            embed.add_field(name="Held for", value=f"{held_days} day(s)", inline=True)
            embed.add_field(name="Current value", value=self.format_cash(current_value), inline=True)
            if not (interaction.guild and interaction.guild.id == 1310977344076251176):
                embed.set_footer(text="https://discord.gg/45J959xRzJ")
            user_inv.remove(chosen_inv)
            inv_data[user_id] = user_inv
            self.save_investments(inv_data)
            await inter.response.send_message(embed=embed, ephemeral=True)
        if len(matching) == 1:
            await finalize_sale(interaction, matching[0])
        else:
            desc = "Items:\n"
            for idx, inv in enumerate(matching[:5], start=1):
                desc += f"- {idx}. {inv['item']} serial {inv['serial']}\n"
            selection_embed = discord.Embed(
                title="Items:",
                description=desc,
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=selection_embed, ephemeral=True, view=InvestmentSelectView(matching, finalize_sale))
    @investment.command(name="view", description="View your current investments")
    async def invest_view(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        inv_data = self.load_investments()
        user_inv = inv_data.get(user_id, [])
        if not user_inv:
            await interaction.response.send_message("You have no active investments.", ephemeral=True)
            return
        desc = ""
        for inv in user_inv[:5]:
            item = inv["item"]
            serial = inv["serial"]
            buy_value = inv["price"]
            try:
                current_value = self.get_item_value(item, serial)
            except Exception:
                current_value = 0
            percent_change = ((current_value - buy_value) / buy_value) * 100 if buy_value != 0 else 0
            percent_text = f"{'+' if percent_change > 0 else ''}{round(percent_change)}%"
            category = self.get_item_category(item)
            serial_text = str(serial) if category in ["items", "kukri_items"] else "No serial"
            desc += (f"**Item:** {item}\n"
                     f"**Serial:** {serial_text}\n"
                     f"**Bought for:** {self.format_cash(buy_value)}\n"
                     f"**Current value:** {self.format_cash(current_value)}\n"
                     f"**{'Win' if percent_change>=0 else 'Lose'} (%):** {percent_text}\n\n")
        embed = discord.Embed(
            title="Your Investments",
            description=desc,
            color=discord.Color.green()
        )
        if not (interaction.guild and interaction.guild.id == 1310977344076251176):
            embed.set_footer(text="https://discord.gg/45J959xRzJ")
        await interaction.response.send_message(embed=embed, ephemeral=True)

def setup(bot: commands.Bot):
    await bot.add_cog(Investments(bot))
