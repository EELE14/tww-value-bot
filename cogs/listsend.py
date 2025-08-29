import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import json
import os
import re
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

LISTS_FILE = "lists.json"
SETUP_FILE = "setup.json"
GUILDCHANNELS_FILE = "guildchannels.json"
LIST_BLACKLIST_FILE = "listblacklist.json"
LIST_ALLOWED_FILE = "listallowed.json"
LOGS_CHANNEL_ID = 1330577417496035409

def load_json(filename: str) -> Dict[str, Any]:
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4)
    with open(filename, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_json(filename: str, data: Dict[str, Any]) -> None:
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

async def log_event(bot: commands.Bot, title: str, action: str, user: discord.User):
    log_channel = bot.get_channel(LOGS_CHANNEL_ID)
    if log_channel:
        embed = discord.Embed(title=title, color=discord.Color.blurple())
        embed.description = (
            f"- User: {user.name} ({user.mention})\n"
            f"- User ID: {user.id}\n"
            f"- Action: {action}\n"
            f"- Timestamp: {datetime.now(timezone.utc).isoformat()}"
        )
        await log_channel.send(embed=embed)

def is_admin(user: discord.User) -> bool:
    return user.id == 1263756486660587543

class ListCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
       
        self.automations: Dict[int, asyncio.Task] = {}

    def load_lists(self) -> Dict[str, Any]:
        return load_json(LISTS_FILE)
    
    def save_lists(self, data: Dict[str, Any]) -> None:
        save_json(LISTS_FILE, data)
    
    def load_setup(self) -> Dict[str, Any]:
        return load_json(SETUP_FILE)
    
    def save_setup(self, data: Dict[str, Any]) -> None:
        save_json(SETUP_FILE, data)
    
    def load_allowed(self) -> Dict[str, Any]:
        return load_json(LIST_ALLOWED_FILE)
    
    def save_allowed(self, data: Dict[str, Any]) -> None:
        save_json(LIST_ALLOWED_FILE, data)

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

    def create_list_view(self, user: discord.User) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        button_owner = discord.ui.Button(label="List owner", style=discord.ButtonStyle.primary)
        button_how = discord.ui.Button(label="How to automate my list?", style=discord.ButtonStyle.secondary)
        
        async def owner_callback(inter: discord.Interaction):
            await inter.response.send_message(f"List sent by {user.mention}", ephemeral=True)
        
        async def how_callback(inter: discord.Interaction):
            text = (
                "
                "Join now Gold Rush Trading and use the `/list add` command to add your very own Trading list!\n"
                "https://discord.gg/45J959xRzJ"
            )
            await inter.response.send_message(text, ephemeral=True)
        
        button_owner.callback = owner_callback
        button_how.callback = how_callback
        view.add_item(button_owner)
        view.add_item(button_how)
        return view

    list_group = app_commands.Group(name="list", description="User list commands.")

    @staticmethod
    def interval_choices() -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name="2 hours", value="2"),
            app_commands.Choice(name="3 hours", value="3"),
            app_commands.Choice(name="4 hours", value="4"),
            app_commands.Choice(name="5 hours", value="5")
        ]
    
    @staticmethod
    def duration_choices() -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name="1 day", value="1"),
            app_commands.Choice(name="2 days", value="2")
        ]
    
    @list_group.command(name="add", description="Add your trading list.")
    async def list_add(self, interaction: discord.Interaction):
        blacklist = load_json(LIST_BLACKLIST_FILE)
        if str(interaction.user.id) in blacklist:
            await interaction.response.send_message("You are not allowed to use list commands.", ephemeral=True)
            return
        try:
            thread = await interaction.channel.create_thread(
                name="Trading list",
                type=discord.ChannelType.private_thread,
                invitable=False
            )
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to create threads here.", ephemeral=True)
            return
        try:
            await thread.add_user(interaction.user)
        except Exception:
            pass
        embed = discord.Embed(
            title="Add trading list <a:trade:1337122473879277580>",
            description="Send your trading list below. Note that your next message in this thread will be saved as your list.",
            color=discord.Color.blue()
        )
        await thread.send(embed=embed)
        await interaction.response.send_message("Please check the created thread and send your list there.", ephemeral=True)
        def check(m: discord.Message):
            return m.channel.id == thread.id and m.author.id == interaction.user.id
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=300)
        except asyncio.TimeoutError:
            await thread.send("Timeout reached. The thread will be archived now.")
            await thread.edit(archived=True)
            return
        if len(msg.content) > 2000:
            await thread.send("Error: Your list exceeds the maximum length of 2000 characters. This thread will be deleted in 5 seconds.", delete_after=5)
            await asyncio.sleep(5)
            try:
                await thread.delete()
            except Exception:
                pass
            return
        lists_data = self.load_lists()
        lists_data[str(interaction.user.id)] = {
            "username": interaction.user.name,
            "list": msg.content,
            "last_sent": datetime.now(timezone.utc).isoformat()
        }
        save_json(LISTS_FILE, lists_data)
        await thread.send("Your list has been saved. This thread will be archived now.")
        await thread.edit(archived=True)
        await log_event(self.bot, "List Add", "User added a trading list.", interaction.user)

    @list_group.command(name="delete", description="Delete your saved list.")
    async def list_delete(self, interaction: discord.Interaction):
        blacklist = load_json(LIST_BLACKLIST_FILE)
        if str(interaction.user.id) in blacklist:
            await interaction.response.send_message("You are not allowed to use list commands.", ephemeral=True)
            return
        lists_data = self.load_lists()
        if str(interaction.user.id) in lists_data:
            del lists_data[str(interaction.user.id)]
            save_json(LISTS_FILE, lists_data)
            await interaction.response.send_message("Your list has been deleted.", ephemeral=True)
            await log_event(self.bot, "List Delete", "User deleted their list.", interaction.user)
        else:
            await interaction.response.send_message("No list found to delete.", ephemeral=True)

    @list_group.command(name="edit", description="Edit your trading list.")
    async def list_edit(self, interaction: discord.Interaction):
        blacklist = load_json(LIST_BLACKLIST_FILE)
        if str(interaction.user.id) in blacklist:
            await interaction.response.send_message("You are not allowed to use list commands.", ephemeral=True)
            return
        lists_data = self.load_lists()
        if str(interaction.user.id) in lists_data:
            del lists_data[str(interaction.user.id)]
            save_json(LISTS_FILE, lists_data)
        try:
            thread = await interaction.channel.create_thread(
                name="Trading list",
                type=discord.ChannelType.private_thread,
                invitable=False
            )
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to create threads here.", ephemeral=True)
            return
        try:
            await thread.add_user(interaction.user)
        except Exception:
            pass
        embed = discord.Embed(
            title="Edit trading list <a:trade:1337122473879277580>",
            description="Send your new trading list below. Note that your next message in this thread will be saved as your list.",
            color=discord.Color.blue()
        )
        await thread.send(embed=embed)
        await interaction.response.send_message("Please check the created thread and send your new list there.", ephemeral=True)
        def check(m: discord.Message):
            return m.channel.id == thread.id and m.author.id == interaction.user.id
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=300)
        except asyncio.TimeoutError:
            await thread.send("Timeout reached. The thread will be archived now.")
            await thread.edit(archived=True)
            return
        if len(msg.content) > 2000:
            await thread.send("Error: Your list exceeds 2000 characters. This thread will be deleted in 5 seconds.", delete_after=5)
            await asyncio.sleep(5)
            try:
                await thread.delete()
            except Exception:
                pass
            return
        lists_data = self.load_lists()
        lists_data[str(interaction.user.id)] = {
            "username": interaction.user.name,
            "list": msg.content,
            "last_sent": datetime.now(timezone.utc).isoformat()
        }
        save_json(LISTS_FILE, lists_data)
        await thread.send("Your list has been updated. This thread will be archived now.")
        await thread.edit(archived=True)
        await log_event(self.bot, "List Edit", "User edited their list.", interaction.user)

    @list_group.command(name="send", description="Send your list to target channels.")
    async def list_send(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        
        await interaction.response.defer(ephemeral=True)
        blacklist = load_json(LIST_BLACKLIST_FILE)
        if str(interaction.user.id) in blacklist:
            await interaction.followup.send("You are not allowed to use list commands.", ephemeral=True)
            return
        lists_data = self.load_lists()
        user_list = lists_data.get(str(interaction.user.id))
        if not user_list:
            await interaction.followup.send("You have no saved list. Use /list add to create one.", ephemeral=True)
            return
        if "last_sent" in user_list:
            try:
                last_sent = datetime.fromisoformat(user_list["last_sent"])
                now = datetime.now(timezone.utc)
                if (now - last_sent).total_seconds() < 1800:
                    await interaction.followup.send("You are still on slowmode!", ephemeral=True)
                    return
            except Exception as e:
                print("Error parsing last_sent:", e)
        target_channels = []
        if channel:
            
            guild_channels = load_json(GUILDCHANNELS_FILE)
            allowed_channel_ids = [entry.get("channel_id") for entry in guild_channels if entry.get("channel_id")]
            if channel.id not in allowed_channel_ids:
                await interaction.followup.send("The selected channel is not configured as target channel.", ephemeral=True)
                return
            target_channels.append(channel)
        else:
            guild_channels = load_json(GUILDCHANNELS_FILE)
            if isinstance(guild_channels, list):
                for entry in guild_channels:
                    ch = self.bot.get_channel(entry.get("channel_id"))
                    if ch:
                        target_channels.append(ch)
        if not target_channels:
            await interaction.followup.send("No target channels configured.", ephemeral=True)
            return
       
        for ch in target_channels:
            try:
                user_obj = self.bot.get_user(interaction.user.id)
                view = self.create_list_view(user_obj) if user_obj else None
                await ch.send(user_list["list"], view=view)
            except Exception as e:
                print(f"Error sending list to channel {ch.id}: {e}")
            await asyncio.sleep(15)
        user_list["last_sent"] = datetime.now(timezone.utc).isoformat()
        lists_data[str(interaction.user.id)] = user_list
        save_json(LISTS_FILE, lists_data)
        
        await interaction.followup.send("Your list has been sent.", view=self.create_list_view(interaction.user), ephemeral=True)
        await log_event(self.bot, "List Send", "User sent their list.", interaction.user)

    @list_group.command(name="automate", description="Automate sending your list.")
    @app_commands.choices(interval=interval_choices(), duration=duration_choices())
    async def list_automate(self, interaction: discord.Interaction, interval: app_commands.Choice[str], duration: app_commands.Choice[str]):
        allowed = load_json(LIST_ALLOWED_FILE)
        if str(interaction.user.id) not in allowed:
            await interaction.response.send_message("You are not allowed to automate your list.", ephemeral=True)
            return
        blacklist = load_json(LIST_BLACKLIST_FILE)
        if str(interaction.user.id) in blacklist:
            await interaction.response.send_message("You are not allowed to use list commands.", ephemeral=True)
            return
        setup_data = load_json(SETUP_FILE)
        user_setup = setup_data.get(str(interaction.user.id))
        now = datetime.now(timezone.utc)
        if user_setup:
            end_time = datetime.fromisoformat(user_setup["end_time"])
            if now < end_time:
                await interaction.response.send_message("You already have an active automation.", ephemeral=True)
                return
            else:
                del setup_data[str(interaction.user.id)]
                save_json(SETUP_FILE, setup_data)
        try:
            interval_sec = int(interval.value) * 3600
        except ValueError:
            await interaction.response.send_message("Invalid interval format.", ephemeral=True)
            return
        try:
            duration_sec = int(duration.value) * 86400
        except ValueError:
            await interaction.response.send_message("Invalid duration format.", ephemeral=True)
            return
        setup_data[str(interaction.user.id)] = {
            "username": interaction.user.name,
            "list_interval": interval_sec,
            "end_time": (now + timedelta(seconds=duration_sec)).isoformat()
        }
        save_json(SETUP_FILE, setup_data)
        await interaction.response.send_message("Your list automation has been set up.", ephemeral=True)
        await log_event(self.bot, "List Automate", f"User set up automation with interval {interval_sec} sec and duration {duration_sec} sec.", interaction.user)
        self.bot.loop.create_task(self.run_automation(interaction.user.id, interval_sec, duration_sec))

    async def run_automation(self, user_id: int, interval: int, duration: int):
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(seconds=duration)
        lists_data = load_json(LISTS_FILE)
        if str(user_id) not in lists_data:
            return
        user_list = lists_data[str(user_id)]["list"]
        guild_channels = load_json(GUILDCHANNELS_FILE)
        target_channels = []
        if isinstance(guild_channels, list):
            for entry in guild_channels:
                ch = self.bot.get_channel(entry.get("channel_id"))
                if ch:
                    target_channels.append(ch)
        user_obj = self.bot.get_user(user_id)
        while datetime.now(timezone.utc) < end_time:
            for ch in target_channels:
                try:
                    view = self.create_list_view(user_obj) if user_obj else None
                    await ch.send(user_list, view=view)
                except Exception as e:
                    print(f"Error sending automation list to channel {ch.id}: {e}")
                await asyncio.sleep(15)
            lists_data[str(user_id)]["last_sent"] = datetime.now(timezone.utc).isoformat()
            save_json(LISTS_FILE, lists_data)
            await asyncio.sleep(interval)
        setup_data = load_json(SETUP_FILE)
        if str(user_id) in setup_data:
            del setup_data[str(user_id)]
            save_json(SETUP_FILE, setup_data)
        if user_obj:
            await log_event(self.bot, "List Automate End", "User automation ended.", user_obj)

    @list_group.command(name="see", description="See a user's saved list.")
    async def list_see(self, interaction: discord.Interaction, user: discord.User):
        lists_data = load_json(LISTS_FILE)
        user_list = lists_data.get(str(user.id))
        if not user_list:
            await interaction.response.send_message("No list found for that user.", ephemeral=True)
            return
        await interaction.response.send_message(user_list["list"], ephemeral=True)
        await log_event(self.bot, "List View", f"User viewed list of {user.name}", interaction.user)

    @commands.command(name="admin_list_view")
    async def admin_list_view(self, ctx, user: Optional[discord.User] = None):
        if ctx.author.id != 1263756486660587543:
            return
        lists_data = load_json(LISTS_FILE)
        if user:
            data = lists_data.get(str(user.id))
            if not data:
                await ctx.send("No list found for that user.")
                return
            await ctx.send(f"List for {user.mention}: {data['list']}")
        else:
            await ctx.send(f"All lists: {json.dumps(lists_data, indent=2)}")
        await log_event(self.bot, "Admin List View", f"Admin viewed list for {user.name if user else 'all users'}", ctx.author)

    @commands.command(name="admin_list_delete")
    async def admin_list_delete(self, ctx, user: Optional[discord.User] = None):
        if ctx.author.id != 1263756486660587543:
            return
        lists_data = load_json(LISTS_FILE)
        if user:
            if str(user.id) in lists_data:
                del lists_data[str(user.id)]
                save_json(LISTS_FILE, lists_data)
                await ctx.send(f"List for {user.mention} deleted.")
            else:
                await ctx.send("No list found for that user.")
        else:
            lists_data = {}
            save_json(LISTS_FILE, lists_data)
            await ctx.send("All lists deleted.")
        await log_event(self.bot, "Admin List Delete", f"Admin deleted list for {user.name if user else 'all users'}", ctx.author)

    @commands.command(name="admin_automate_view")
    async def admin_automate_view(self, ctx, user: Optional[discord.User] = None):
        if ctx.author.id != 1263756486660587543:
            return
        setup_data = load_json(SETUP_FILE)
        if user:
            data = setup_data.get(str(user.id))
            if not data:
                await ctx.send("No automation found for that user.")
                return
            await ctx.send(f"Automation for {user.mention}: {json.dumps(data, indent=2)}")
        else:
            await ctx.send(f"All automations: {json.dumps(setup_data, indent=2)}")
        await log_event(self.bot, "Admin Automate View", f"Admin viewed automation for {user.name if user else 'all users'}", ctx.author)

    @commands.command(name="admin_automate_stop")
    async def admin_automate_stop(self, ctx, user: discord.User):
        if ctx.author.id != 1263756486660587543:
            return
        setup_data = load_json(SETUP_FILE)
        if str(user.id) in setup_data:
            del setup_data[str(user.id)]
            save_json(SETUP_FILE, setup_data)
            await ctx.send(f"Automation for {user.mention} has been stopped.")
        else:
            await ctx.send("No active automation found for that user.")
        await log_event(self.bot, "Admin Automate Stop", f"Admin stopped automation for {user.name}", ctx.author)

    @commands.command(name="admin_channel_add")
    async def admin_channel_add(self, ctx, channel: discord.TextChannel):
        if ctx.author.id != 1263756486660587543:
            return
        guild_channels = load_json(GUILDCHANNELS_FILE)
        if not isinstance(guild_channels, list):
            guild_channels = []
        for entry in guild_channels:
            if entry.get("channel_id") == channel.id:
                await ctx.send("Channel already exists.")
                return
        new_entry = {
            "guild_id": channel.guild.id,
            "guild_name": channel.guild.name,
            "channel_id": channel.id
        }
        guild_channels.append(new_entry)
        save_json(GUILDCHANNELS_FILE, guild_channels)
        await ctx.send(f"Channel {channel.mention} added for list sending.")
        await log_event(self.bot, "Admin Channel Add", f"Admin added channel {channel.mention}", ctx.author)

    @commands.command(name="admin_channel_remove")
    async def admin_channel_remove(self, ctx, channel: discord.TextChannel):
        if ctx.author.id != 1263756486660587543:
            return
        guild_channels = load_json(GUILDCHANNELS_FILE)
        if not isinstance(guild_channels, list):
            guild_channels = []
        new_channels = [entry for entry in guild_channels if entry.get("channel_id") != channel.id]
        if len(new_channels) == len(guild_channels):
            await ctx.send("Channel not found in the list.")
            return
        save_json(GUILDCHANNELS_FILE, new_channels)
        await ctx.send(f"Channel {channel.mention} removed from list sending.")
        await log_event(self.bot, "Admin Channel Remove", f"Admin removed channel {channel.mention}", ctx.author)

    @commands.command(name="admin_log_view")
    async def admin_log_view(self, ctx, count: int):
        if ctx.author.id != 1263756486660587543:
            return
        await ctx.send("Log view functionality is not implemented separately; logs are sent to the log channel.", delete_after=5)
        await log_event(self.bot, "Admin Log View", f"Admin requested last {count} log entries.", ctx.author)

    @commands.command(name="admin_role_set")
    async def admin_role_set(self, ctx, role: discord.Role):
        if ctx.author.id != 1263756486660587543:
            return
        setup_data = load_json(SETUP_FILE)
        setup_data["special_member_role"] = role.id
        save_json(SETUP_FILE, setup_data)
        await ctx.send(f"Special Member role set to {role.mention}.")
        await log_event(self.bot, "Admin Role Set", f"Admin set special member role to {role.mention}.", ctx.author)

    @commands.command(name="admin_blacklist_user")
    async def admin_blacklist_user(self, ctx, user: discord.User):
        if ctx.author.id != 1263756486660587543:
            return
        blacklist = load_json(LIST_BLACKLIST_FILE)
        if not isinstance(blacklist, list):
            blacklist = []
        if str(user.id) not in blacklist:
            blacklist.append(str(user.id))
            save_json(LIST_BLACKLIST_FILE, blacklist)
            await ctx.send(f"{user.mention} has been blacklisted from list commands.")
        else:
            await ctx.send(f"{user.mention} is already blacklisted.")
        await log_event(self.bot, "Admin Blacklist", f"Admin blacklisted user {user.mention}.", ctx.author)

    @commands.command(name="admin_blacklist_remove")
    async def admin_blacklist_remove(self, ctx, user: discord.User):
        if ctx.author.id != 1263756486660587543:
            return
        blacklist = load_json(LIST_BLACKLIST_FILE)
        if not isinstance(blacklist, list):
            blacklist = []
        if str(user.id) in blacklist:
            blacklist.remove(str(user.id))
            save_json(LIST_BLACKLIST_FILE, blacklist)
            await ctx.send(f"{user.mention} has been removed from the blacklist.")
        else:
            await ctx.send(f"{user.mention} is not blacklisted.")
        await log_event(self.bot, "Admin Blacklist Remove", f"Admin removed {user.mention} from blacklist.", ctx.author)

    @commands.command(name="admin_allow_automate")
    async def admin_allow_automate(self, ctx, user_id: int):
        if ctx.author.id != 1263756486660587543:
            return
        allowed = load_json(LIST_ALLOWED_FILE)
        if str(user_id) not in allowed:
            allowed[str(user_id)] = True
            save_json(LIST_ALLOWED_FILE, allowed)
            await ctx.send(f"User with ID {user_id} is now allowed to automate their list.")
        else:
            await ctx.send("User is already allowed to automate their list.")
        await log_event(self.bot, "Admin Allow Automate", f"Admin allowed automation for user {user_id}.", ctx.author)

async def setup(bot: commands.Bot):
    await bot.add_cog(ListCog(bot))
