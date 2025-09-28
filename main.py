import os
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Select, View, Button

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
DESK_CATEGORY = int(os.getenv("DESK_CATEGORY_ID"))
IA_CATEGORY = int(os.getenv("IA_CATEGORY_ID"))
HR_CATEGORY = int(os.getenv("HR_CATEGORY_ID"))
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL_ID"))
EMOJI_1 = os.getenv("EMOJI_1")  # custom server emoji pasted
MOD_ROLE = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE = int(os.getenv("SAY_ROLE_ID"))

bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# ---------- Helper Functions ----------

def format_user(user: discord.Member):
    return f"{user} (ID: {user.id})"  # no ping

async def log_action(message: str):
    channel = bot.get_channel(LOG_CHANNEL)
    if channel:
        await channel.send(embed=discord.Embed(
            description=message,
            color=0x313D61
        ))

def get_category(category_name: str):
    if category_name.lower() == "desk":
        return DESK_CATEGORY
    elif category_name.lower() == "ia":
        return IA_CATEGORY
    elif category_name.lower() == "hr":
        return HR_CATEGORY
    else:
        return None

# ---------- Ticket Panel ----------

class TicketDropdown(Select):
    def __init__(self):
        options=[
            discord.SelectOption(label="Desk Support", description="Desk inquiries", emoji="💼"),
            discord.SelectOption(label="Internal Affairs", description="Reports/cases", emoji="⚖️"),
            discord.SelectOption(label="HR+ Support", description="Speak to Director/HR", emoji="📝")
        ]
        super().__init__(placeholder="Select ticket type", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        category_id = get_category(self.values[0])
        if not category_id:
            await interaction.response.send_message("Category not found.", ephemeral=True)
            return
        category = bot.get_channel(category_id)
        channel = await category.create_text_channel(
            name=f"{self.values[0]}-{interaction.user.name}",
            topic=f"Ticket for {interaction.user}",
        )
        embed = discord.Embed(
            title=f"Ticket Created",
            description=f"{EMOJI_1} Ticket for {interaction.user} in {self.values[0]} category",
            color=0x313D61
        )
        await channel.send(embed=embed)
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)
        await log_action(f"Ticket opened by {format_user(interaction.user)} in {self.values[0]}")

class TicketView(View):
    def __init__(self):
        super().__init__()
        self.add_item(TicketDropdown())

@tree.command(name="panel", description="Send ticket panel")
async def panel(interaction: discord.Interaction):
    if not any(role.id == MOD_ROLE for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permission to send the ticket panel.", ephemeral=True)
        return
    embed = discord.Embed(
        title="Ticket Panel",
        description=f"{EMOJI_1} Select your ticket type below",
        color=0x313D61
    )
    await interaction.response.send_message(embed=embed, view=TicketView())

# ---------- Add/Remove Commands ----------

@tree.command(name="add", description="Add a user to a ticket")
@app_commands.describe(user="User to add")
async def add(interaction: discord.Interaction, user: discord.Member):
    channel = interaction.channel
    await channel.set_permissions(user, read_messages=True, send_messages=True)
    embed = discord.Embed(
        description=f"✅ {format_user(user)} added to this ticket.",
        color=0x00FF00
    )
    await interaction.response.send_message(embed=embed)
    await log_action(f"{format_user(user)} added to ticket {channel.name} by {format_user(interaction.user)}")

@tree.command(name="remove", description="Remove a user from a ticket")
@app_commands.describe(user="User to remove")
async def remove(interaction: discord.Interaction, user: discord.Member):
    channel = interaction.channel
    await channel.set_permissions(user, overwrite=None)
    embed = discord.Embed(
        description=f"❌ {format_user(user)} removed from this ticket.",
        color=0xFF0000
    )
    await interaction.response.send_message(embed=embed)
    await log_action(f"{format_user(user)} removed from ticket {channel.name} by {format_user(interaction.user)}")

# ---------- Moderation Commands ----------

@tree.command(name="kick", description="Kick a member")
@app_commands.describe(user="User to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str="No reason provided"):
    if not any(role.id == MOD_ROLE for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    await user.kick(reason=reason)
    await interaction.response.send_message(f"{user} kicked.")
    await log_action(f"{format_user(user)} was kicked by {format_user(interaction.user)}. Reason: {reason}")

@tree.command(name="ban", description="Ban a member")
@app_commands.describe(user="User to ban", reason="Reason for ban")
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str="No reason provided"):
    if not any(role.id == MOD_ROLE for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    await user.ban(reason=reason)
    await interaction.response.send_message(f"{user} banned.")
    await log_action(f"{format_user(user)} was banned by {format_user(interaction.user)}. Reason: {reason}")

@tree.command(name="purge", description="Delete messages")
@app_commands.describe(amount="Number of messages")
async def purge(interaction: discord.Interaction, amount: int):
    if not any(role.id == MOD_ROLE for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    embed = discord.Embed(
        description=f"🧹 Purged {len(deleted)} messages by {format_user(interaction.user)}",
        color=0x313D61
    )
    await interaction.response.send_message(embed=embed)
    await log_action(f"{len(deleted)} messages purged in {interaction.channel.name} by {format_user(interaction.user)}")

@tree.command(name="say", description="Bot says something")
@app_commands.describe(message="Message to send")
async def say(interaction: discord.Interaction, message: str):
    if not any(role.id == SAY_ROLE for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    await interaction.channel.send(message)

@tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms")

# ---------- Bot Startup ----------

@bot.event
async def on_ready():
    guild = bot.get_guild(GUILD_ID)
    await tree.sync(guild=guild)
    print(f"Logged in as {bot.user} ({bot.user.id})")

bot.run(TOKEN)
