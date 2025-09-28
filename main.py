import os
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
import threading

# ----------------- ENV VARIABLES -----------------
TOKEN = os.getenv("TOKEN")
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
TICKET_CHANNEL_ID = int(os.getenv("TICKET_CHANNEL_ID"))
DESK_CAT_ID = int(os.getenv("DESK_CAT_ID"))
GUILD_ID = int(os.getenv("GUILD_ID"))  # server ID

# ----------------- INTENTS -----------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)
tree = bot.tree

# ----------------- LOGGING FUNCTION -----------------
async def log_action(action: str, user: discord.Member, moderator: discord.Member, reason: str):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title=f"{action}",
            description=f"**User:** {user} (`{user.id}`)\n**Moderator:** {moderator} (`{moderator.id}`)\n**Reason:** {reason}",
            color=0x313D61
        )
        await channel.send(embed=embed)

# ----------------- CHECKS -----------------
def is_mod():
    async def predicate(interaction: discord.Interaction):
        return MOD_ROLE_ID in [role.id for role in interaction.user.roles]
    return app_commands.check(predicate)

def can_say():
    async def predicate(interaction: discord.Interaction):
        return SAY_ROLE_ID in [role.id for role in interaction.user.roles]
    return app_commands.check(predicate)

# ----------------- MOD COMMANDS -----------------
@tree.command(name="kick", description="Kick a member", guild=discord.Object(id=GUILD_ID))
@is_mod()
@app_commands.describe(member="Member to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str):
    await member.kick(reason=reason)
    await log_action("Kick", member, interaction.user, reason)
    await interaction.response.send_message(f"{member} was kicked.", ephemeral=True)

@tree.command(name="ban", description="Ban a member", guild=discord.Object(id=GUILD_ID))
@is_mod()
@app_commands.describe(member="Member to ban", reason="Reason for ban")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str):
    await member.ban(reason=reason)
    await log_action("Ban", member, interaction.user, reason)
    await interaction.response.send_message(f"{member} was banned.", ephemeral=True)

@tree.command(name="timeout", description="Timeout a member", guild=discord.Object(id=GUILD_ID))
@is_mod()
@app_commands.describe(member="Member to timeout", duration="Minutes of timeout", reason="Reason for timeout")
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: int, reason: str):
    await member.timeout(duration * 60, reason=reason)
    await log_action("Timeout", member, interaction.user, reason)
    await interaction.response.send_message(f"{member} was timed out for {duration} minutes.", ephemeral=True)

@tree.command(name="purge", description="Purge messages", guild=discord.Object(id=GUILD_ID))
@is_mod()
@app_commands.describe(amount="Number of messages", reason="Reason for purge")
async def purge(interaction: discord.Interaction, amount: int, reason: str):
    deleted = await interaction.channel.purge(limit=amount)
    await log_action("Purge", interaction.user, interaction.user, reason)
    await interaction.response.send_message(f"Deleted {len(deleted)} messages.", ephemeral=True)

@tree.command(name="lock", description="Lock channel", guild=discord.Object(id=GUILD_ID))
@is_mod()
@app_commands.describe(reason="Reason for locking")
async def lock(interaction: discord.Interaction, reason: str):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await log_action("Lock", interaction.user, interaction.user, reason)
    await interaction.response.send_message("Channel locked.", ephemeral=True)

@tree.command(name="unlock", description="Unlock channel", guild=discord.Object(id=GUILD_ID))
@is_mod()
@app_commands.describe(reason="Reason for unlocking")
async def unlock(interaction: discord.Interaction, reason: str):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = True
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await log_action("Unlock", interaction.user, interaction.user, reason)
    await interaction.response.send_message("Channel unlocked.", ephemeral=True)

# ----------------- SAY COMMAND -----------------
@tree.command(name="say", description="Make the bot say something", guild=discord.Object(id=GUILD_ID))
@can_say()
@app_commands.describe(text="Text to send")
async def say(interaction: discord.Interaction, text: str):
    await interaction.channel.send(text)
    await interaction.response.send_message("Message sent.", ephemeral=True)

# ----------------- TICKET PANEL -----------------
@tree.command(name="ticketpanel", description="Send ticket panel", guild=discord.Object(id=GUILD_ID))
@is_mod()
async def ticketpanel(interaction: discord.Interaction):
    channel = bot.get_channel(TICKET_CHANNEL_ID)
    embed = discord.Embed(
        title=":ticket: Support Tickets",
        description="Click the button to open a ticket.",
        color=0x313D61
    )
    button = discord.ui.Button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    view = discord.ui.View()
    view.add_item(button)
    await channel.send(embed=embed, view=view)
    await interaction.response.send_message("Ticket panel sent.", ephemeral=True)

# ----------------- BOT EVENTS -----------------
@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"{bot.user} is online!")

# ----------------- FLASK SERVER FOR RENDER -----------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running."

def run_flask():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

threading.Thread(target=run_flask).start()

# ----------------- RUN BOT -----------------
bot.run(TOKEN)
