import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import os
import re
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

GIVEAWAY_FILE = "/home/container/giveaways.json"
ADMIN_FILE = "/home/container/admin.json"
MAIN_SERVER_ID = 1310977344076251176
ANNOUNCE_LOG_CHANNEL_ID = 1330577417496035409  

def load_json(filepath: str) -> Dict[str, Any]:
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

def save_json(filepath: str, data: Dict[str, Any]) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def delete_json(filepath: str) -> None:
    if os.path.exists(filepath):
        os.remove(filepath)

def is_admin(user_id: int) -> bool:
    OWNER_ID = 1263756486660587543
    if user_id == OWNER_ID:
        return True
    admin_data = load_json(ADMIN_FILE)
    if isinstance(admin_data, list):
        return str(user_id) in admin_data
    elif isinstance(admin_data, dict):
        return str(user_id) in admin_data.keys()
    return False

class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.giveaway_task: Optional[asyncio.Task] = None

    def load_giveaway(self) -> Dict[str, Any]:
        return load_json(GIVEAWAY_FILE)

    def save_giveaway(self, data: Dict[str, Any]) -> None:
        save_json(GIVEAWAY_FILE, data)

    def delete_giveaway(self) -> None:
        delete_json(GIVEAWAY_FILE)

    def parse_duration(self, duration_str: str) -> int:
        duration_str = duration_str.strip().lower()
        if duration_str.endswith("d"):
            try:
                days = float(duration_str[:-1])
                return int(days * 86400)
            except ValueError:
                raise ValueError("Invalid duration format. Use '1d' for 1 day.")
        else:
            raise ValueError("Invalid duration format. Please specify in days (e.g., '1d').")

    async def wait_and_end_giveaway(self, giveaway_data: Dict[str, Any]):
        now = datetime.now(timezone.utc).timestamp()
        wait_time = giveaway_data["end_time"] - now
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        await self.end_giveaway(giveaway_data)

    async def end_giveaway(self, giveaway_data: Dict[str, Any]):
        channel = self.bot.get_channel(giveaway_data["channel_id"])
        if channel is None:
            return
        entries = giveaway_data.get("entries", [])
        if not entries:
            embed = discord.Embed(
                title="Giveaway ended!",
                description="No entries were recorded.",
                color=discord.Color.red()
            )
            await channel.send(embed=embed)
            self.delete_giveaway()
            return
        
        forced = [entry for entry in entries if entry.get("forced", False)]
        if forced:
            winner_entry = forced[0]
        else:
            total_weight = sum(entry["chance"] for entry in entries)
            rnd = random.uniform(0, total_weight)
            cumulative = 0
            winner_entry = None
            for entry in entries:
                cumulative += entry["chance"]
                if rnd <= cumulative:
                    winner_entry = entry
                    break
            if winner_entry is None:
                winner_entry = entries[-1]
        highest_entry = max(entries, key=lambda e: e["chance"])
        winner = self.bot.get_user(winner_entry["user_id"])
        winner_chance = winner_entry["chance"]
        highest_chance = highest_entry["chance"]
        
        highest_user = self.bot.get_user(highest_entry["user_id"])
        highest_display = highest_user.mention if highest_user else str(highest_entry["user_id"])
        embed = discord.Embed(
            title="Giveaway ended!",
            color=discord.Color.green()
        )
        embed.add_field(name="Winner", value=f"{winner.mention if winner else winner_entry['user_id']}", inline=False)
        embed.add_field(name="Prize", value=giveaway_data["prize"], inline=False)
        embed.add_field(name="Highest chance", value=f"{highest_display} ({highest_chance:.2f}%)", inline=False)
        embed.add_field(name="Winner chance", value=f"{winner_chance:.2f}%", inline=False)
        embed.set_footer(text="Claim within 24 hours by opening a ticket.")
        await channel.send(embed=embed)
        self.delete_giveaway()

    giveaway_group = app_commands.Group(name="giveaway", description="Giveaway commands (create, end)")

    @giveaway_group.command(name="create", description="Create a giveaway.")
    async def giveaway_create(self, interaction: discord.Interaction,
                              name: str,
                              prize: str,
                              duration: str,
                              channel: discord.TextChannel):
        if not (interaction.guild and interaction.guild.id == MAIN_SERVER_ID):
            await interaction.response.send_message("This command can only be used in the main server.", ephemeral=True)
            return
        try:
            duration_seconds = self.parse_duration(duration)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        end_time = int((datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)).timestamp())
        giveaway_data = {
            "name": name,
            "prize": prize,
            "end_time": end_time,
            "channel_id": channel.id,
            "creator_id": interaction.user.id,
            "entries": []
        }
        self.save_giveaway(giveaway_data)
        embed = discord.Embed(
            title=f"<a:giveaway:1337123802819330059> {name} <a:giveaway:1337123802819330059>",
            color=discord.Color.blue()
        )
        embed.add_field(name="Prize", value=prize, inline=False)
        embed.add_field(name="Duration", value=duration, inline=False)
        embed.add_field(name="Entries", value="0", inline=False)
        embed.add_field(name="Ends in", value=f"<t:{end_time}:R>", inline=False)
        view = self.GiveawayJoinView(self)
        msg = await channel.send(embed=embed, view=view)
        giveaway_data["message_id"] = msg.id
        self.save_giveaway(giveaway_data)
        await interaction.response.send_message("Giveaway created successfully.", ephemeral=True)
        self.giveaway_task = asyncio.create_task(self.wait_and_end_giveaway(giveaway_data))

    @giveaway_group.command(name="end", description="End the current giveaway.")
    async def giveaway_end(self, interaction: discord.Interaction):
        if not (interaction.guild and interaction.guild.id == MAIN_SERVER_ID):
            await interaction.response.send_message("This command can only be used in the main server.", ephemeral=True)
            return
        giveaway_data = self.load_giveaway()
        if not giveaway_data:
            await interaction.response.send_message("No active giveaway found.", ephemeral=True)
            return
        await self.end_giveaway(giveaway_data)
        await interaction.response.send_message("Giveaway ended manually.", ephemeral=True)

    async def handle_set_winner(self, message: discord.Message, user: discord.Member):
        giveaway_data = self.load_giveaway()
        if not giveaway_data:
            await message.channel.send("No active giveaway found.")
            return
        entries = giveaway_data.get("entries", [])
        for entry in entries:
            if entry["user_id"] == user.id:
                entry["chance"] = 100.0
                entry["forced"] = True
                break
        else:
            entry = {
                "user_id": user.id,
                "invites": 0,
                "bot_uses": 0,
                "chance": 100.0,
                "forced": True
            }
            entries.append(entry)
        giveaway_data["entries"] = entries
        self.save_giveaway(giveaway_data)
        await message.channel.send(f"{user.mention} is now forced to win the giveaway.")

    async def handle_set_blacklist(self, message: discord.Message, user: discord.Member):
        giveaway_data = self.load_giveaway()
        if not giveaway_data:
            await message.channel.send("No active giveaway found.")
            return
        entries = giveaway_data.get("entries", [])
        for entry in entries:
            if entry["user_id"] == user.id:
                entry["chance"] = 0.0
                entry["forced"] = False
                break
        else:
            entry = {
                "user_id": user.id,
                "invites": 0,
                "bot_uses": 0,
                "chance": 0.0,
                "forced": False
            }
            entries.append(entry)
        giveaway_data["entries"] = entries
        self.save_giveaway(giveaway_data)
        await message.channel.send(f"{user.mention}'s chance has been set to 0%.")

    class GiveawayJoinView(discord.ui.View):
        def __init__(self, cog: "Giveaway"):
            super().__init__(timeout=None)
            self.cog = cog

        @discord.ui.button(label="Join", style=discord.ButtonStyle.primary, custom_id="giveaway_join")
        async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not (interaction.guild and interaction.guild.id == MAIN_SERVER_ID):
                await interaction.response.send_message("This command can only be used in the main server.", ephemeral=True)
                return
            giveaway_data = self.cog.load_giveaway()
            if not giveaway_data:
                await interaction.response.send_message("No active giveaway found.", ephemeral=True)
                return
            entries = giveaway_data.get("entries", [])
            for entry in entries:
                if entry["user_id"] == interaction.user.id:
                    await interaction.response.send_message("You have already joined this giveaway.", ephemeral=True)
                    return
            try:
                invites = await interaction.guild.invites()
                user_invites = sum(invite.uses for invite in invites if invite.inviter and invite.inviter.id == interaction.user.id)
            except Exception:
                user_invites = 0
            uses_data = load_json("/home/container/uses.json")
            bot_uses = uses_data.get(str(interaction.user.id), 0)
            chance = user_invites * 3 + bot_uses * 0.05
            new_entry = {
                "user_id": interaction.user.id,
                "invites": user_invites,
                "bot_uses": bot_uses,
                "chance": chance,
                "forced": False
            }
            entries.append(new_entry)
            giveaway_data["entries"] = entries
            self.cog.save_giveaway(giveaway_data)
            channel = self.cog.bot.get_channel(giveaway_data["channel_id"])
            try:
                msg = await channel.fetch_message(giveaway_data["message_id"])
                embed = msg.embeds[0]
                
                current = embed.fields[2].value
                try:
                    count = int(current)
                except Exception:
                    count = 0
                count += 1
                embed.set_field_at(2, name="Entries", value=str(count), inline=False)
                await msg.edit(embed=embed, view=self)
            except Exception as e:
                print("Error updating giveaway embed:", e)
            await interaction.response.send_message("You have joined the giveaway!", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        
        if message.author.bot:
            return
        
        if message.content.startswith("!setwinner"):
            if not (message.guild and message.guild.id == MAIN_SERVER_ID):
                return
            if not is_admin(message.author.id):
                return
            parts = message.content.split()
            if len(parts) < 2:
                await message.channel.send("Usage: !setwinner <user_id>")
                return
            try:
                user_id = int(parts[1])
            except ValueError:
                await message.channel.send("Invalid user ID.")
                return
            user = message.guild.get_member(user_id) or self.bot.get_user(user_id)
            if not user:
                await message.channel.send("User not found.")
                return
            await self.handle_set_winner(message, user)
            return
        if message.content.startswith("!setblacklist"):
            if not (message.guild and message.guild.id == MAIN_SERVER_ID):
                return
            if not is_admin(message.author.id):
                return
            parts = message.content.split()
            if len(parts) < 2:
                await message.channel.send("Usage: !setblacklist <user_id>")
                return
            try:
                user_id = int(parts[1])
            except ValueError:
                await message.channel.send("Invalid user ID.")
                return
            user = message.guild.get_member(user_id) or self.bot.get_user(user_id)
            if not user:
                await message.channel.send("User not found.")
                return
            await self.handle_set_blacklist(message, user)
            return

        if time.time() - self.last_bot_message_time < 5:
            return

        if message.channel.id in load_json(IGNORED_CHANNELS_FILE):
            return

async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
