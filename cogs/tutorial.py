import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime, timezone


USES_FILE = "/home/container/uses.json"

# Hilfsfunktionen zum Laden/Speichern von JSON-Dateien
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

def update_tutorial_uses():
    data = load_json(USES_FILE)
    if "tutorial_uses" not in data:
        data["tutorial_uses"] = 0
    data["tutorial_uses"] += 1
    save_json(USES_FILE, data)



class TutorialButton(discord.ui.Button):
    def __init__(self, label: str, custom_id: str):
        super().__init__(style=discord.ButtonStyle.primary, label=label, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        if self.custom_id == "tutorial_trading":
            new_embed = discord.Embed(
                title="Trading <a:trade:1337503184444330025>",
                description=(
                    "You selected the trade commands. To initiate a trade, you may use the `/trade start` command. "
                    "This will start your trade. After that you can use the `/offer item` or `/offer cash` commands. "
                    "These will add items with serial numbers to your trade. Please make sure to not add serials for event items. "
                    "When you added items to your side, you can use the `/counter item` and `/counter cash` commands to add cash to the other person's side.\n"
                    "When you are finished, make sure to use the `/trade end` command to get your result."
                ),
                color=discord.Color.blue()
            )
        elif self.custom_id == "tutorial_investments":
            new_embed = discord.Embed(
                title="Investments",
                description=(
                    "You selected the investments commands. With these commands you can keep an eye on what your TWW investments are doing. "
                    "You start by using `/investment add`. With this command you can add an item that you bought to your inventory. "
                    "You will be able to view the value development of this item and see when you can profit by selling it. "
                    "With `/investment view`, you can see your current investments. You see their current value and how much you would profit from selling them. "
                    "Then you can sell your items with `/investment sell`. This command simulates a sell from your inventory for a specific price. "
                    "When you don't enter a price, the system will assume that you sold for the current value."
                ),
                color=discord.Color.blue()
            )
        elif self.custom_id == "tutorial_values":
            new_embed = discord.Embed(
                title="Values",
                description=(
                    "You selected values. You can use the simple `/value` command to select any item that you want. "
                    "The bot will output the value. Please make sure to leave the serial option empty when you select a non-auction item. "
                    "When you select an auction item without specifying a serial, the bot will assume it's a high serial. "
                    "You have also two other options to get values:\n"
                    "Use the prefix command `!value {item name} + {serial if required}` to get a detailed overview of an item. "
                    "You can also just type the name of the item in the chat and wait for the bot to give its value. (Make sure to use the exact name of the item.)"
                ),
                color=discord.Color.blue()
            )
        elif self.custom_id == "tutorial_inventory":
            new_embed = discord.Embed(
                title="Inventory",
                description=(
                    "You selected inventory. These commands are still under development. You can expect a release soon..."
                ),
                color=discord.Color.blue()
            )
        else:
            new_embed = discord.Embed(title="Tutorial", description="Unknown selection.", color=discord.Color.blue())
        new_embed.set_footer(text="https://discord.gg/45J959xRzJ")
        # Aktualisiere das ursprüngliche Embed; die Buttons bleiben erhalten.
        await interaction.response.edit_message(embed=new_embed, view=self.view)

class TutorialView(discord.ui.View):
    """Diese View beschränkt die Button-Interaktion auf den ursprünglichen Command-Nutzer."""
    def __init__(self, author_id: int, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.add_item(TutorialButton(label="Trading", custom_id="tutorial_trading"))
        self.add_item(TutorialButton(label="Investments", custom_id="tutorial_investments"))
        self.add_item(TutorialButton(label="Values", custom_id="tutorial_values"))
        self.add_item(TutorialButton(label="Inventory", custom_id="tutorial_inventory"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You cannot use these buttons.", ephemeral=True)
            return False
        return True

class TutorialPublicView(discord.ui.View):
    """Diese View erlaubt allen Nutzern die Button-Interaktion und hat keinen Timeout."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TutorialButton(label="Trading", custom_id="tutorial_trading"))
        self.add_item(TutorialButton(label="Investments", custom_id="tutorial_investments"))
        self.add_item(TutorialButton(label="Values", custom_id="tutorial_values"))
        self.add_item(TutorialButton(label="Inventory", custom_id="tutorial_inventory"))


class Tutorial(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # /tutorial Slash-Command (nur der ausführende Nutzer kann die Buttons bedienen)
    @app_commands.command(name="tutorial", description="Start the bot tutorial")
    async def tutorial(self, interaction: discord.Interaction):
        update_tutorial_uses()
        embed = discord.Embed(
            title="Tutorial started",
            description="Hey, your tutorial has been started. Please click the buttons below to get information about a specific command or command group.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="https://discord.gg/45J959xRzJ")
        view = TutorialView(author_id=interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    # !panel Prefix-Command (jeder kann die Buttons bedienen; keine Button-Timeout)
    @commands.command(name="panel")
    async def panel(self, ctx: commands.Context):
        update_tutorial_uses()
        embed = discord.Embed(
            title="Tutorial started",
            description="Hey, your tutorial has been started. Please click the buttons below to get information about a specific command or command group.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="https://discord.gg/45J959xRzJ")
        view = TutorialPublicView()
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Tutorial(bot))
