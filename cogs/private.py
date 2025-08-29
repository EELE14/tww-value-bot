import discord
from discord.ext import commands
import json
import os
from datetime import datetime

PRIVATE_FILE = "private.json"

class PrivateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="private")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def private_command(self, ctx):
        user_id = str(ctx.author.id)
        data = {}
        
        if os.path.exists(PRIVATE_FILE):
            with open(PRIVATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        
        if user_id in data and data[user_id].get("private", False):
            data[user_id]["private"] = False
            response = "Private deactivated <a:success:1337122638388269207>"
        else:
            data[user_id] = {"private": True, "timestamp": datetime.utcnow().isoformat()}
            response = "Private activated <a:success:1337122638388269207>"
        
        with open(PRIVATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        
        await ctx.send(response)

    @private_command.error
    async def private_command_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Please wait {round(error.retry_after, 1)} seconds before using this command again.", delete_after=1)
        else:
            raise error

async def setup(bot):
    await bot.add_cog(PrivateCog(bot))

