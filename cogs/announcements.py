import discord
from discord.ext import commands
import json
import os
import asyncio
import time


ADMIN_FILE = "/home/container/admin.json"
ANNOUNCEMENTS_FILE = "/home/container/announcements.json"

MAIN_ALLOWED_ID = 1263756486660587543

# Kanal, in den das Announcements-Embed gesendet wird:
ANNOUNCE_LOG_CHANNEL_ID = 1330577417496035409

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

def is_admin(user_id: int) -> bool:
    # Prüft, ob der user_id gleich MAIN_ALLOWED_ID ist oder in admin.json gelistet ist.
    admin_data = load_json(ADMIN_FILE)
    if str(user_id) == str(MAIN_ALLOWED_ID):
        return True
    if isinstance(admin_data, list):
        return str(user_id) in admin_data
    elif isinstance(admin_data, dict):
        return str(user_id) in admin_data.keys()
    return False

class OwnerNotifier(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot


    @commands.command(name="ownersend")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ownersend(self, ctx: commands.Context, *, message: str):
        if not is_admin(ctx.author.id):
            await ctx.send("You do not have permission to use this command.")
            return

        # Sammle alle eindeutigen Serverbesitzer (als User-Objekte) aus allen Guilds, in denen der Bot aktiv ist
        owners = {}
        for guild in self.bot.guilds:
            if guild.owner is not None:
                owners[guild.owner.id] = guild.owner  # Überschreibt doppelte Einträge

        # Sende an jeden Besitzer per DM (mit 10 Sekunden Pause zwischen den DMs)
        sent_count = 0
        for owner in owners.values():
            try:
                await owner.send(f"Message from bot admin:\n\n{message}")
                sent_count += 1
            except Exception as e:
                print(f"Could not send DM to {owner}: {e}")
            await asyncio.sleep(10)
        await ctx.send(f"Sent message to {sent_count} server owner(s).")


    @commands.command(name="ownerask")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ownerask(self, ctx: commands.Context):
        if not is_admin(ctx.author.id):
            await ctx.send("You do not have permission to use this command.")
            return

        # Sammle alle eindeutigen Serverbesitzer
        owners = {}
        for guild in self.bot.guilds:
            if guild.owner is not None:
                owners[guild.owner.id] = (guild.owner, guild)
        if not owners:
            await ctx.send("No server owners found.")
            return

        # Erstelle die View mit Buttons (für DM)
        for owner, guild in owners.values():
            try:
                view = OwnerAskView(owner, guild, self.bot)
                await owner.send("Hello, it seems like you own a server where the value bot is being used. Would you like to add a channel where the bot informs your members about updates?", view=view)
                # 2 Sekunden Pause zwischen den DMs
                await asyncio.sleep(2)
            except Exception as e:
                print(f"Error sending ownerask DM to {owner}: {e}")
        await ctx.send("Owner ask message sent to all server owners.")


    @commands.command(name="announce")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def announce(self, ctx: commands.Context, *, message: str):
        if not is_admin(ctx.author.id):
            await ctx.send("You do not have permission to use this command.")
            return

        announcements = load_json(ANNOUNCEMENTS_FILE)
        if not announcements:
            await ctx.send("No announcement channels have been set up.")
            return


        count = 0
        for entry in announcements.get("channels", []):
            channel_id = entry.get("channel_id")
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        await channel.send(message)
                        count += 1
                        await asyncio.sleep(10)  # 10 Sekunden Pause zwischen Nachrichten
                    except Exception as e:
                        print(f"Failed to send message to channel {channel_id}: {e}")
        await ctx.send(f"Announcement sent to {count} channel(s).")



class OwnerAskView(discord.ui.View):
    def __init__(self, owner: discord.User, guild: discord.Guild, bot: commands.Bot, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.owner = owner
        self.guild = guild
        self.bot = bot

    @discord.ui.button(label="Add Updates", style=discord.ButtonStyle.primary, custom_id="add_updates")
    async def add_updates(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Prüfe, ob der Interactor auch der Owner ist
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("This is not your prompt.", ephemeral=True)
            return

        await interaction.response.send_message("Please send a channel ID for updates below:", ephemeral=True)
        try:
            def check(m: discord.Message):
                return m.author.id == self.owner.id and m.channel.type == discord.ChannelType.private
            reply = await self.bot.wait_for("message", check=check, timeout=300)
            # Versuche, den Inhalt als integer zu interpretieren
            try:
                channel_id = int(reply.content.strip())
            except ValueError:
                await interaction.followup.send("Invalid channel ID.", ephemeral=True)
                return

            # Aktualisiere announcements.json
            announcements = load_json(ANNOUNCEMENTS_FILE)
            if "channels" not in announcements:
                announcements["channels"] = []
            # Füge einen neuen Eintrag hinzu. Wenn der Owner bereits einen Eintrag hat, ersetze ihn.
            new_entry = {
                "server_id": self.guild.id,
                "server_name": self.guild.name,
                "channel_id": channel_id,
                "owner_id": self.owner.id
            }
            # Entferne vorhandene Einträge dieses Owners (optional)
            announcements["channels"] = [e for e in announcements["channels"] if e.get("owner_id") != self.owner.id]
            announcements["channels"].append(new_entry)
            save_json(ANNOUNCEMENTS_FILE, announcements)

            # Hole den Channel-Objekt
            update_channel = self.bot.get_channel(channel_id)
            channel_name = update_channel.name if update_channel else "Unknown"
            embed = discord.Embed(
                title="Announcements Channel added",
                description=f"Server: {self.guild.name}\nChannel: {channel_name}\nOwner: {self.owner}",
                color=discord.Color.green()
            )
            log_channel = self.bot.get_channel(ANNOUNCE_LOG_CHANNEL_ID)
            if log_channel:
                await log_channel.send(embed=embed)
            await interaction.followup.send("Updates channel added successfully.", ephemeral=True)
        except asyncio.TimeoutError:
            await interaction.followup.send("Timed out waiting for channel ID.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="cancel_update")
    async def cancel_update(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("This is not your prompt.", ephemeral=True)
            return
        await interaction.response.send_message("Operation cancelled.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(OwnerNotifier(bot))
