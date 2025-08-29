import discord
from discord.ext import commands
import os
import json
import time
import asyncio

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

COG_DIR = "cogs"
OWNER_ID = 1263756486660587543
ALLOWED_SERVERS_FILE = "allowedservers.json"
ADMIN_FILE = "admin.json"
BLACKLIST_FILE = "blacklist.json"

last_command_time = 0

@bot.check
async def global_cooldown(ctx):
    global last_command_time
    now = time.time()
    if now - last_command_time < 10:
        try:
            await ctx.send(f"Please wait {round(10 - (now - last_command_time), 1)} seconds before using another command.", delete_after=1)
        except Exception:
            pass
        return False
    last_command_time = now
    return True

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await load_all_cogs()
    await bot.tree.sync()
    print("Slash-Commands synchronisiert.")

def load_json(filename):
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump([], f)
    with open(filename, "r") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_guild_join(guild):
    allowed_servers = load_json(ALLOWED_SERVERS_FILE)
    if guild.id not in allowed_servers:
        try:
            await guild.owner.send("This bot is restricted to specific servers. Leaving now.")
        except Exception as e:
            print("Failed to send DM to guild owner:", e)
        await guild.leave()

async def load_all_cogs():
    for filename in os.listdir(COG_DIR):
        if filename.endswith(".py") and filename != "__init__.py":
            cog_name = filename[:-3]
            await bot.load_extension(f"{COG_DIR}.{cog_name}")

@bot.command()
async def addadmin(ctx, user_id: int):
    if ctx.author.id != OWNER_ID:
        return
    admins = load_json(ADMIN_FILE)
    if user_id not in admins:
        admins.append(user_id)
        save_json(ADMIN_FILE, admins)
    await ctx.send("User added as admin.")

def is_admin():
    def predicate(ctx):
        admins = load_json(ADMIN_FILE)
        return ctx.author.id in admins
    return commands.check(predicate)

@bot.command()
@commands.check(is_admin())
async def addid(ctx, server_id: int):
    allowed_servers = load_json(ALLOWED_SERVERS_FILE)
    if server_id not in allowed_servers:
        allowed_servers.append(server_id)
        save_json(ALLOWED_SERVERS_FILE, allowed_servers)
    await ctx.send("Server ID added to allowed list.")

@bot.command()
@commands.check(is_admin())
async def remove(ctx):
    embed = discord.Embed(title="Removing..", description="<a:loading:1337122453024931910>", color=discord.Color.orange())
    message = await ctx.send(embed=embed)
    allowed_servers = load_json(ALLOWED_SERVERS_FILE)
    if ctx.guild.id in allowed_servers:
        allowed_servers.remove(ctx.guild.id)
        save_json(ALLOWED_SERVERS_FILE, allowed_servers)
    embed.title = "Success  <a:success:1337122638388269207>"
    embed.description = "Bot removed successfully."
    embed.color = discord.Color.green()
    await message.edit(embed=embed)
    await ctx.guild.leave()

@bot.command()
@commands.check(is_admin())
async def blacklist(ctx, user_id: int):
    blacklist = load_json(BLACKLIST_FILE)
    if user_id not in blacklist:
        blacklist.append(user_id)
        save_json(BLACKLIST_FILE, blacklist)
    await ctx.send("User added to blacklist.")

@bot.command()
@commands.check(is_admin())
async def unblacklist(ctx, user_id: int):
    blacklist = load_json(BLACKLIST_FILE)
    if user_id in blacklist:
        blacklist.remove(user_id)
        save_json(BLACKLIST_FILE, blacklist)
    await ctx.send("User removed from blacklist.")

@bot.command()
@commands.check(is_admin())
async def disable(ctx, cog_name: str):
    await bot.unload_extension(f"{COG_DIR}.{cog_name}")
    await bot.tree.sync()
    await ctx.send(f"Command {cog_name} disabled.")

@bot.command()
@commands.check(is_admin())
async def enable(ctx, cog_name: str):
    await bot.load_extension(f"{COG_DIR}.{cog_name}")
    await bot.tree.sync()
    await ctx.send(f"Command {cog_name} enabled.")

@bot.command(name="del")
@commands.check(lambda ctx: ctx.author.id == OWNER_ID)
async def delete_message(ctx, message_id: int):
    try:
        msg = await ctx.channel.fetch_message(message_id)
        if msg.author.id == bot.user.id:
            await msg.delete()
            await ctx.send("Message deleted.", delete_after=5)
        else:
            await ctx.send("I can only delete my own messages.", delete_after=5)
    except Exception as e:
        await ctx.send(f"Error: {e}", delete_after=5)
TOKEN = "PlaceHolder"
bot.run(TOKEN)

