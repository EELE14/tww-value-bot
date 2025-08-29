import discord
from discord.ext import commands
import json
import os

USES_FILE = "/home/container/uses.json"

def load_json(filepath: str):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}

class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="stats")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def stats(self, ctx: commands.Context):
        
        uses = load_json(USES_FILE)
        trade_uses = uses.get("trade_uses", 0)
        total_uses = uses.get("total_uses", 0)
        investement_uses = uses.get("investement_uses", 0)
        tutorial_uses = uses.get("tutorial_uses", 0)
        your_uses = uses.get(str(ctx.author.id), 0)

        ping = round(self.bot.latency * 1000)
        
        server_count = len(self.bot.guilds)

        embed = discord.Embed(title="Statistics", color=discord.Color.green())
        embed.add_field(name="Ping", value=f"{ping}ms", inline=False)
        embed.add_field(name="Trade uses", value=str(trade_uses), inline=False)
        embed.add_field(name="Value uses", value=str(total_uses), inline=False)
        embed.add_field(name="Investment uses", value=str(investement_uses), inline=False)
        embed.add_field(name="Tutorial uses", value=str(tutorial_uses), inline=False)
        embed.add_field(name="Your uses", value=str(your_uses), inline=False)
        embed.add_field(
            name="**Servers:**", 
            value=f"Installed server count: {server_count}\nMain Server: Gold Rush Trading\nhttps://discord.gg/45J959xRzJ", 
            inline=False
        )
        await ctx.send(embed=embed)

    @stats.error
    async def stats_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Please wait {round(error.retry_after, 1)} seconds before using this command again.", delete_after=1)
        else:
            raise error

async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))

