import discord
from discord.ext import commands
from discord import app_commands, ButtonStyle
from discord.ui import Button, View
import os

# -------------------- ENV VARIABLES --------------------
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
DESK_CATEGORY_ID = int(os.getenv("DESK_CATEGORY_ID"))
IA_CATEGORY_ID = int(os.getenv("IA_CATEGORY_ID"))
HR_CATEGORY_ID = int(os.getenv("HR_CATEGORY_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)

# -------------------- HELPER FUNCTIONS --------------------
async def log_action(message: str):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(message)

async def create_ticket_channel(interaction: discord.Interaction, category_id: int, reason: str):
    guild = bot.get_guild(GUILD_ID)
    category = discord.utils.get(guild.categories, id=category_id)
    if not category:
        await interaction.response.send_message("Category not found.", ephemeral=True)
        return
    channel = await guild.create_text_channel(
        name=f"{interaction.user.name}-ticket",
        category=category,
        topic=f"Ticket opened by {interaction.user} ({interaction.user.id}) | Reason: {reason}"
    )
    await channel.set_permissions(interaction.user, send_messages=True, read_messages=True)
    await channel.set_permissions(guild.default_role, send_messages=False, read_messages=False)
    await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)
    await log_action(f"{interaction.user} ({interaction.user.id}) opened a ticket in {category.name}: {reason}")

# -------------------- TICKET PANEL --------------------
@bot.tree.command(name="ticketpanel", description="Send the ticket panel")
@app_commands.checks.has_role(MOD_ROLE_ID)
async def ticketpanel(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"{interaction.guild.icon} Ticket Panel",
        description="Select your ticket type from below",
        color=0x313D61
    )
    view = View()
    # Ticket buttons
    view.add_item(Button(label="Desk Support", style=ButtonStyle.green, custom_id="desk_support"))
    view.add_item(Button(label="Internal Affairs", style=ButtonStyle.blurple, custom_id="internal_affairs"))
    view.add_item(Button(label="HR+ Support", style=ButtonStyle.blurple, custom_id="hr_support"))
    # Action buttons
    view.add_item(Button(label="Claim", style=ButtonStyle.green, custom_id="claim_ticket"))
    view.add_item(Button(label="Add User", style=ButtonStyle.blurple, custom_id="add_user"))
    view.add_item(Button(label="Remove User", style=ButtonStyle.blurple, custom_id="remove_user"))
    view.add_item(Button(label="Close", style=ButtonStyle.red, custom_id="close_ticket"))
    await interaction.response.send_message(embed=embed, view=view)

# -------------------- BUTTON HANDLERS --------------------
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.type == discord.InteractionType.component:
        return
    custom_id = interaction.data.get("custom_id")
    if custom_id in ["desk_support", "internal_affairs", "hr_support"]:
        category_id = {"desk_support": DESK_CATEGORY_ID,
                       "internal_affairs": IA_CATEGORY_ID,
                       "hr_support": HR_CATEGORY_ID}[custom_id]
        await create_ticket_channel(interaction, category_id, f"{custom_id.replace('_', ' ').title()}")
    elif custom_id == "claim_ticket":
        await interaction.response.send_message(f"{interaction.user} ({interaction.user.id}) claimed the ticket.", ephemeral=True)
        await log_action(f"{interaction.user} ({interaction.user.id}) claimed a ticket in {interaction.channel.name}")
    elif custom_id == "add_user":
        await interaction.response.send_message("Use /add command to add users.", ephemeral=True)
    elif custom_id == "remove_user":
        await interaction.response.send_message("Use /remove command to remove users.", ephemeral=True)
    elif custom_id == "close_ticket":
        await interaction.channel.delete()
        await log_action(f"{interaction.user} ({interaction.user.id}) closed the ticket.")

# -------------------- MOD COMMANDS --------------------
@bot.tree.command(name="purge", description="Delete messages in channel")
@app_commands.checks.has_role(MOD_ROLE_ID)
@app_commands.describe(amount="Number of messages to delete")
async def purge(interaction: discord.Interaction, amount: int):
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"Deleted {len(deleted)} messages.", ephemeral=True)
    await log_action(f"{interaction.user} ({interaction.user.id}) purged {len(deleted)} messages in {interaction.channel.name}")

@bot.tree.command(name="kick", description="Kick a member")
@app_commands.checks.has_role(MOD_ROLE_ID)
@app_commands.describe(member="Member to kick", reason="Reason")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"{member} was kicked.", ephemeral=True)
    await log_action(f"{interaction.user} ({interaction.user.id}) kicked {member} ({member.id}) | Reason: {reason}")

@bot.tree.command(name="ban", description="Ban a member")
@app_commands.checks.has_role(MOD_ROLE_ID)
@app_commands.describe(member="Member to ban", reason="Reason")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"{member} was banned.", ephemeral=True)
    await log_action(f"{interaction.user} ({interaction.user.id}) banned {member} ({member.id}) | Reason: {reason}")

@bot.tree.command(name="timeout", description="Timeout a member")
@app_commands.checks.has_role(MOD_ROLE_ID)
@app_commands.describe(member="Member to timeout", duration="Duration in seconds")
async def timeout(interaction: discord.Interaction, member: discord.Member, duration: int):
    await member.timeout(discord.utils.utcnow() + discord.timedelta(seconds=duration))
    await interaction.response.send_message(f"{member} was timed out for {duration} seconds.", ephemeral=True)
    await log_action(f"{interaction.user} ({interaction.user.id}) timed out {member} ({member.id}) for {duration}s")

@bot.tree.command(name="lock", description="Lock the current channel")
@app_commands.checks.has_role(MOD_ROLE_ID)
async def lock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("Channel locked.", ephemeral=True)
    await log_action(f"{interaction.user} ({interaction.user.id}) locked {interaction.channel.name}")

# /say command
@bot.tree.command(name="say", description="Send a message as the bot")
@app_commands.checks.has_role(SAY_ROLE_ID)
@app_commands.describe(message="Message to send")
async def say(interaction: discord.Interaction, message: str):
    await interaction.channel.send(message)
    await interaction.response.send_message("Message sent.", ephemeral=True)
    await log_action(f"{interaction.user} ({interaction.user.id}) used /say in {interaction.channel.name}: {message}")

# /ping command
@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms")

# -------------------- ADD/REMOVE USER COMMANDS --------------------
@bot.tree.command(name="add", description="Add a user to the ticket")
@app_commands.checks.has_role(MOD_ROLE_ID)
@app_commands.describe(member="Member to add")
async def add(interaction: discord.Interaction, member: discord.Member):
    await interaction.channel.set_permissions(member, send_messages=True, read_messages=True)
    await interaction.response.send_message(f"{member} added to the ticket.", ephemeral=True)
    await log_action(f"{interaction.user} ({interaction.user.id}) added {member} ({member.id}) to {interaction.channel.name}")

@bot.tree.command(name="remove", description="Remove a user from the ticket")
@app_commands.checks.has_role(MOD_ROLE_ID)
@app_commands.describe(member="Member to remove")
async def remove(interaction: discord.Interaction, member: discord.Member):
    await interaction.channel.set_permissions(member, overwrite=None)
    await interaction.response.send_message(f"{member} removed from the ticket.", ephemeral=True)
    await log_action(f"{interaction.user} ({interaction.user.id}) removed {member} ({member.id}) from {interaction.channel.name}")

# -------------------- ON READY --------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

bot.run(TOKEN)
