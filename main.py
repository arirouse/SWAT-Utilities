import os
import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select
from discord import Interaction, Embed
import asyncio
from flask import Flask

# ----------------------
# Environment Variables
# ----------------------
TOKEN = os.getenv("TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))
DESK_CAT_ID = int(os.getenv("DESK_CAT_ID"))
IA_CAT_ID = int(os.getenv("IA_CAT_ID"))
HR_CAT_ID = int(os.getenv("HR_CAT_ID"))
TICKET_PANEL_CHANNEL_ID = int(os.getenv("TICKET_PANEL_CHANNEL_ID"))

# ----------------------
# Bot Setup
# ----------------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

# ----------------------
# Embed Color
# ----------------------
EMBED_COLOR = 0x313D61

# ----------------------
# Utility Functions
# ----------------------
def mod_check(interaction: Interaction):
    return interaction.user.get_role(MOD_ROLE_ID) is not None

def say_check(interaction: Interaction):
    return interaction.user.get_role(SAY_ROLE_ID) is not None

def format_mention(user):
    # Shows name and ID but does not ping
    return f"{user} (`{user.id}`)"

# ----------------------
# Logging
# ----------------------
async def log_action(action: str, user: discord.User, reason: str = None):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    embed = Embed(title=action, color=EMBED_COLOR)
    embed.add_field(name="User", value=format_mention(user))
    if reason:
        embed.add_field(name="Reason", value=reason)
    await log_channel.send(embed=embed)

# ----------------------
# Ticket Views
# ----------------------
class TicketView(View):
    def __init__(self, ticket_channel):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.add_item(Button(label="Claim", style=discord.ButtonStyle.green, custom_id="claim"))
        self.add_item(Button(label="Unclaim", style=discord.ButtonStyle.gray, custom_id="unclaim"))
        self.add_item(Button(label="Close", style=discord.ButtonStyle.red, custom_id="close"))

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="claim")
    async def claim_button(self, interaction: Interaction, button: Button):
        await interaction.response.send_message(f"{interaction.user} claimed this ticket.", ephemeral=True)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.gray, custom_id="unclaim")
    async def unclaim_button(self, interaction: Interaction, button: Button):
        await interaction.response.send_message(f"{interaction.user} unclaimed this ticket.", ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="close")
    async def close_button(self, interaction: Interaction, button: Button):
        await interaction.channel.delete()

# ----------------------
# Ticket Panel
# ----------------------
class TicketPanel(View):
    def __init__(self):
        super().__init__(timeout=None)
        options = [
            discord.SelectOption(label="Desk Support", description="Open a Desk ticket", value="desk"),
            discord.SelectOption(label="IA", description="Open an IA ticket", value="ia"),
            discord.SelectOption(label="HR", description="Open an HR ticket", value="hr"),
        ]
        self.add_item(Select(placeholder="Choose category...", options=options, custom_id="ticket_dropdown"))

    @discord.ui.select(custom_id="ticket_dropdown")
    async def select_callback(self, interaction: Interaction, select: Select):
        value = select.values[0]
        if value == "desk":
            category = bot.get_channel(DESK_CAT_ID)
        elif value == "ia":
            category = bot.get_channel(IA_CAT_ID)
        else:
            category = bot.get_channel(HR_CAT_ID)

        ticket = await category.create_text_channel(name=f"ticket-{interaction.user.name}", topic=f"Ticket for {interaction.user}")
        await ticket.send(embed=Embed(title="Ticket", description=f"Ticket opened by {interaction.user}", color=EMBED_COLOR), view=TicketView(ticket))
        await interaction.response.send_message("Ticket created!", ephemeral=True)

# ----------------------
# Slash Commands
# ----------------------
@bot.tree.command(name="panel", description="Send the ticket panel")
async def panel(interaction: Interaction):
    if not mod_check(interaction):
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    embed = Embed(title="Open a Ticket", description="Select the category below:", color=EMBED_COLOR)
    await interaction.response.send_message(embed=embed, view=TicketPanel(), ephemeral=True)

# /say
@bot.tree.command(name="say", description="Bot says something")
@app_commands.check(say_check)
@app_commands.describe(message="The message the bot will say")
async def say(interaction: Interaction, message: str):
    await interaction.response.send_message(message)

# /ping
@bot.tree.command(name="ping", description="Bot ping")
async def ping(interaction: Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms")

# /kick
@bot.tree.command(name="kick", description="Kick a user")
@app_commands.check(mod_check)
@app_commands.describe(user="User to kick", reason="Reason for kick")
async def kick(interaction: Interaction, user: discord.Member, reason: str):
    await user.kick(reason=reason)
    await log_action("Kick", user, reason)
    await interaction.response.send_message(f"Kicked {format_mention(user)}")

# /ban
@bot.tree.command(name="ban", description="Ban a user")
@app_commands.check(mod_check)
@app_commands.describe(user="User to ban", reason="Reason for ban")
async def ban(interaction: Interaction, user: discord.Member, reason: str):
    await user.ban(reason=reason)
    await log_action("Ban", user, reason)
    await interaction.response.send_message(f"Banned {format_mention(user)}")

# /timeout
@bot.tree.command(name="timeout", description="Timeout a user")
@app_commands.check(mod_check)
@app_commands.describe(user="User to timeout", reason="Reason for timeout", duration="Duration in seconds")
async def timeout(interaction: Interaction, user: discord.Member, duration: int, reason: str):
    await user.timeout(discord.Duration(seconds=duration), reason=reason)
    await log_action("Timeout", user, reason)
    await interaction.response.send_message(f"Timed out {format_mention(user)}")

# /purge
@bot.tree.command(name="purge", description="Delete messages")
@app_commands.check(mod_check)
@app_commands.describe(amount="Number of messages to delete", reason="Reason for purge")
async def purge(interaction: Interaction, amount: int, reason: str):
    deleted = await interaction.channel.purge(limit=amount)
    await log_action("Purge", interaction.user, reason)
    await interaction.response.send_message(f"Deleted {len(deleted)} messages")

# /lock
@bot.tree.command(name="lock", description="Lock the channel")
@app_commands.check(mod_check)
@app_commands.describe(reason="Reason for lock")
async def lock(interaction: Interaction, reason: str):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await log_action("Channel Locked", interaction.user, reason)
    await interaction.response.send_message("Channel locked.")

# /unlock
@bot.tree.command(name="unlock", description="Unlock the channel")
@app_commands.check(mod_check)
@app_commands.describe(reason="Reason for unlock")
async def unlock(interaction: Interaction, reason: str):
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await log_action("Channel Unlocked", interaction.user, reason)
    await interaction.response.send_message("Channel unlocked.")

# ----------------------
# Add/Remove from ticket
# ----------------------
@bot.tree.command(name="add", description="Add a user to a ticket")
@app_commands.check(mod_check)
@app_commands.describe(user="User to add")
async def add(interaction: Interaction, user: discord.Member):
    await interaction.channel.set_permissions(user, read_messages=True, send_messages=True)
    await interaction.response.send_message(embed=Embed(title="Added", description=f"{format_mention(user)} added to ticket", color=EMBED_COLOR))

@bot.tree.command(name="remove", description="Remove a user from a ticket")
@app_commands.check(mod_check)
@app_commands.describe(user="User to remove")
async def remove(interaction: Interaction, user: discord.Member):
    await interaction.channel.set_permissions(user, overwrite=None)
    await interaction.response.send_message(embed=Embed(title="Removed", description=f"{format_mention(user)} removed from ticket", color=EMBED_COLOR))

# ----------------------
# Events
# ----------------------
@bot.event
async def on_ready():
    print(f"Bot ready! Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

# ----------------------
# Flask App (Keep alive)
# ----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

async def run_bot():
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(run_bot())
