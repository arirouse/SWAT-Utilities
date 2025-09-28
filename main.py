import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from flask import Flask

# ====== ENV VARIABLES ======
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))  # For guild-specific commands
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

# Ticket category channel IDs
DESK_CAT_ID = int(os.getenv("DESK_CAT_ID"))
IA_CAT_ID = int(os.getenv("IA_CAT_ID"))
HR_CAT_ID = int(os.getenv("HR_CAT_ID"))

# Roles
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))

# ====== BOT SETUP ======
intents = discord.Intents.default()
intents.members = True  # Needed for moderation commands

bot = commands.Bot(command_prefix="!", intents=intents)

# Sync commands to a specific guild
GUILD = discord.Object(id=GUILD_ID)

# ====== HELPER FUNCTIONS ======
async def log_action(action: str, user: discord.Member, reason: str = None):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    embed = discord.Embed(title=f"{action} Executed", color=0x313D61)
    embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    await log_channel.send(embed=embed)

# ====== TICKET PANEL COMMAND ======
@bot.tree.command(name="ticket_panel", description="Send the ticket panel")
@app_commands.checks.has_role(MOD_ROLE_ID)
async def ticket_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title=":emoji_1: Open a Ticket",
        description="Select a category to open a ticket.",
        color=0x313D61
    )
    embed.add_field(name="Desk Support", value="Technical support issues", inline=False)
    embed.add_field(name="IA", value="Internal affairs", inline=False)
    embed.add_field(name="HR", value="Human resources", inline=False)

    view = discord.ui.View(timeout=None)
    dropdown = discord.ui.Select(
        placeholder="Select a ticket category...",
        options=[
            discord.SelectOption(label="Desk Support", value="desk"),
            discord.SelectOption(label="IA", value="ia"),
            discord.SelectOption(label="HR", value="hr")
        ]
    )

    async def dropdown_callback(interaction: discord.Interaction):
        cat_map = {
            "desk": DESK_CAT_ID,
            "ia": IA_CAT_ID,
            "hr": HR_CAT_ID
        }
        cat_id = cat_map[dropdown.values[0]]
        category = bot.get_channel(cat_id)
        ticket_channel = await category.send(
            f"Ticket opened by {interaction.user.mention}"
        )

        # Add ticket buttons
        ticket_view = discord.ui.View(timeout=None)
        claim_button = discord.ui.Button(label="Claim", style=discord.ButtonStyle.green)
        unclaim_button = discord.ui.Button(label="Unclaim", style=discord.ButtonStyle.gray)
        close_button = discord.ui.Button(label="Close", style=discord.ButtonStyle.red)

        async def claim_callback(btn_inter):
            await btn_inter.response.send_message(f"{btn_inter.user} claimed the ticket.", ephemeral=True)

        async def unclaim_callback(btn_inter):
            await btn_inter.response.send_message(f"{btn_inter.user} unclaimed the ticket.", ephemeral=True)

        async def close_callback(btn_inter):
            await ticket_channel.send(f"Ticket closed by {btn_inter.user}.")
            await ticket_channel.delete()

        claim_button.callback = claim_callback
        unclaim_button.callback = unclaim_callback
        close_button.callback = close_callback
        ticket_view.add_item(claim_button)
        ticket_view.add_item(unclaim_button)
        ticket_view.add_item(close_button)

        await ticket_channel.send("Use the buttons below:", view=ticket_view)
        await interaction.response.send_message("Ticket created!", ephemeral=True)

    dropdown.callback = dropdown_callback
    view.add_item(dropdown)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ====== MODERATION COMMANDS ======
mod_commands = ["kick", "ban", "mute", "timeout", "lock", "unlock", "purge"]

for cmd in mod_commands:
    @bot.tree.command(name=cmd)
    @app_commands.describe(user="Target user", reason="Reason for the action")
    @app_commands.checks.has_role(MOD_ROLE_ID)
    async def mod_action(interaction: discord.Interaction, user: discord.Member, reason: str):
        if cmd == "kick":
            await user.kick(reason=reason)
        elif cmd == "ban":
            await user.ban(reason=reason)
        elif cmd == "mute":
            await user.edit(mute=True)
        elif cmd == "timeout":
            await user.timeout(duration=3600, reason=reason)
        elif cmd == "lock":
            await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
        elif cmd == "unlock":
            await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
        elif cmd == "purge":
            messages = await interaction.channel.history(limit=100).flatten()
            txt_content = "\n".join(f"{m.author}: {m.content}" for m in messages)
            log_channel = bot.get_channel(LOG_CHANNEL_ID)
            await log_channel.send(file=discord.File(fp=txt_content.encode(), filename="purged.txt"))
            await interaction.channel.purge(limit=100)
        await log_action(cmd.capitalize(), user, reason)
        await interaction.response.send_message(f"{cmd.capitalize()} executed on {user}", ephemeral=True)

# ====== SAY COMMAND ======
@bot.tree.command(name="say")
@app_commands.checks.has_role(SAY_ROLE_ID)
async def say(interaction: discord.Interaction, message: str):
    await interaction.channel.send(message)
    await interaction.response.send_message("Message sent.", ephemeral=True)

# ====== PING COMMAND ======
@bot.tree.command(name="ping")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!", ephemeral=True)

# ====== START BOT WITH SYNC ======
async def main():
    async with bot:
        await bot.start(TOKEN)

# ====== RUN FLASK SERVER FOR RENDER ======
app = Flask("main")

@app.route("/")
def home():
    return "Bot is running"

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
