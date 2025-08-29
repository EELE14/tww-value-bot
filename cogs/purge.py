import discord
from discord import app_commands
from discord.ext import commands
import asyncio

MAIN_SERVER_ID = 1310977344076251176  # Nur in diesem Server zulassen

class PurgeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="purge",
        description="Delete messages in the channel."
    )
    @app_commands.describe(
        count="Number of messages to delete (max 1000)",
        bot_filter="If true, only delete messages from bots; if false, only delete messages not from bots",
        user="If provided, only delete messages from this user"
    )
    async def purge(
        self,
        interaction: discord.Interaction,
        count: int,
        bot_filter: bool = None,
        user: discord.Member = None
    ):
        # Überprüfe, ob der Command im Main-Server ausgeführt wird.
        if not (interaction.guild and interaction.guild.id == MAIN_SERVER_ID):
            await interaction.response.send_message("This command can only be used in the main server.", ephemeral=True)
            return

        # 1k max
        if count > 1000:
            count = 1000

        # Initiales Loading-Embed
        initial_embed = discord.Embed(
            title="Deleting messages...",
            description="<a:loading:1337122453024931910>",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=initial_embed)
        original_msg = await interaction.original_response()

        try:
            # Hole bis zu 1k Nachrichten
            messages = [msg async for msg in interaction.channel.history(limit=1000)]
            
            # Filterfunktion
            def filter_message(m: discord.Message) -> bool:
                if m.id == original_msg.id:
                    return False
                if bot_filter is True and not m.author.bot:
                    return False
                if bot_filter is False and m.author.bot:
                    return False
                if user is not None and m.author.id != user.id:
                    return False
                return True

            filtered_messages = [m for m in messages if filter_message(m)]
            
            # Wenn nicht genügend Nachrichten vorhanden sind
            if len(filtered_messages) < count:
                error_embed = discord.Embed(
                    title="Error <:error:1337123835253751968>",
                    description=f"Less messages in channel than purge count!\nMessages in channel: {len(filtered_messages)}",
                    color=discord.Color.red()
                )
                try:
                    await original_msg.delete()  
                except discord.NotFound:
                    pass
                await interaction.followup.send(embed=error_embed, ephemeral=False)
                return

            deleted = await interaction.channel.delete_messages(filtered_messages[:count])
            num_deleted = len(deleted) if deleted is not None else 0

            success_embed = discord.Embed(
                title="Successful Purge <a:success:1337122638388269207>",
                description=f"Messages: {count}",
                color=discord.Color.green()
            )
            try:
                await original_msg.edit(embed=success_embed)
            except discord.NotFound:
                pass

            # Log in den Log-Channel
            log_channel = self.bot.get_channel(1310986228610502656)
            if log_channel:
                await log_channel.send(embed=success_embed)

        except Exception as e:
            error_embed = discord.Embed(
                title="Error <:error:1337123835253751968>",
                description=f"An error occurred: {e}",
                color=discord.Color.red()
            )
            try:
                await original_msg.delete()
            except discord.NotFound:
                pass
            await interaction.followup.send(embed=error_embed, ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(PurgeCog(bot))
