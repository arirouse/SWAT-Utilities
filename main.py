import discord
from discord.ext import commands
from discord import app_commands, ui
from discord.utils import get
from flask import Flask
import os
import asyncio

# -------------------------------
# ENVIRONMENT VARIABLES TO DEFINE
# -------------------------------
TOKEN = os.getenv("DISCORD_TOKEN")  # Bot token
GUILD_ID = int(os.getenv("GUILD_ID"))  # Server ID
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))  # Role allowed for mod commands
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))  # Role allowed for /say
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))  # Logs channel
TICKET_CATEGORY_IDS = {
    "desk": int(os.getenv("DESK_CAT_ID")),
    "ia": int(os.getenv("IA_CAT_ID")),
    "hr": int(os.getenv("HR_CAT_ID"))
}
EMOJI_1 = ":emoji_1:"  # Use your server emoji exactly like this

# -------------------------------
# BOT INITIALIZATION
# -------------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  # Needed for member actions

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# -------------------------------
# LOGGING FUNCTION
# -------------------------------
async def log_action(action: str, user: discord.Member, reason: str):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    embed = discord.Embed(
        title=f"{EMOJI_1} Mod Action",
        description=f"**Action:** {action}\n**User:** {user} (`{user.id}`)\n**Reason:** {reason}",
        color=0x313D61
    )
    await channel.send(embed=embed)

# -------------------------------
# MOD COMMANDS (Require reason)
# -------------------------------
@tree.command(guild=discord.Object(id=GUILD_ID), name="kick", description="Kick a user (requires mod role)")
@app_commands.describe(user="User to kick", reason="Reason for kick")
async def kick(interaction: discord.Interaction, user: discord.Member, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You lack permissions.", ephemeral=True)
        return
    await user.kick(reason=reason)
    await log_action("Kick", user, reason)
    await interaction.response.send_message(f"{user} was kicked.", ephemeral=True)

@tree.command(guild=discord.Object(id=GUILD_ID), name="ban", description="Ban a user (requires mod role)")
@app_commands.describe(user="User to ban", reason="Reason for ban")
async def ban(interaction: discord.Interaction, user: discord.Member, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You lack permissions.", ephemeral=True)
        return
    await user.ban(reason=reason)
    await log_action("Ban", user, reason)
    await interaction.response.send_message(f"{user} was banned.", ephemeral=True)

@tree.command(guild=discord.Object(id=GUILD_ID), name="mute", description="Timeout a user (requires mod role)")
@app_commands.describe(user="User to mute", reason="Reason for mute")
async def mute(interaction: discord.Interaction, user: discord.Member, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You lack permissions.", ephemeral=True)
        return
    await user.timeout(duration=3600, reason=reason)
    await log_action("Mute", user, reason)
    await interaction.response.send_message(f"{user} has been muted for 1 hour.", ephemeral=True)

@tree.command(guild=discord.Object(id=GUILD_ID), name="timeout", description="Timeout a user (requires mod role)")
@app_commands.describe(user="User to timeout", reason="Reason for timeout")
async def timeout(interaction: discord.Interaction, user: discord.Member, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You lack permissions.", ephemeral=True)
        return
    await user.timeout(duration=600, reason=reason)
    await log_action("Timeout", user, reason)
    await interaction.response.send_message(f"{user} has been timed out for 10 minutes.", ephemeral=True)

@tree.command(guild=discord.Object(id=GUILD_ID), name="lock", description="Lock the channel")
@app_commands.describe(reason="Reason for locking")
async def lock(interaction: discord.Interaction, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You lack permissions.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await log_action("Lock", interaction.user, reason)
    await interaction.response.send_message(f"Channel locked.", ephemeral=True)

@tree.command(guild=discord.Object(id=GUILD_ID), name="unlock", description="Unlock the channel")
@app_commands.describe(reason="Reason for unlocking")
async def unlock(interaction: discord.Interaction, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You lack permissions.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await log_action("Unlock", interaction.user, reason)
    await interaction.response.send_message(f"Channel unlocked.", ephemeral=True)

@tree.command(guild=discord.Object(id=GUILD_ID), name="purge", description="Delete messages and log as TXT")
@app_commands.describe(amount="Number of messages to delete", reason="Reason for purge")
async def purge(interaction: discord.Interaction, amount: int, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You lack permissions.", ephemeral=True)
        return
    msgs = await interaction.channel.history(limit=amount).flatten()
    deleted_txt = ""
    for m in msgs:
        deleted_txt += f"[{m.created_at}] {m.author}: {m.content}\n"
    file = discord.File(fp=discord.BytesIO(deleted_txt.encode()), filename="purged.txt")
    await interaction.channel.delete_messages(msgs)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    await log_channel.send(content=f"Purged {amount} messages in {interaction.channel}. Reason: {reason}", file=file)
    await log_action("Purge", interaction.user, reason)
    await interaction.response.send_message(f"Deleted {amount} messages.", ephemeral=True)

@tree.command(guild=discord.Object(id=GUILD_ID), name="say", description="Bot says a message")
@app_commands.describe(message="Message for the bot to send")
async def say(interaction: discord.Interaction, message: str):
    if SAY_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You lack permissions.", ephemeral=True)
        return
    await interaction.channel.send(message)
    await interaction.response.send_message("Message sent.", ephemeral=True)

@tree.command(guild=discord.Object(id=GUILD_ID), name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! {round(bot.latency*1000)}ms", ephemeral=True)

# -------------------------------
# TICKET PANEL
# -------------------------------
class TicketDropdown(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Desk Support", description="Open a ticket for Desk Support", value="desk"),
            discord.SelectOption(label="IA", description="Open a ticket for IA", value="ia"),
            discord.SelectOption(label="HR", description="Open a ticket for HR", value="hr"),
        ]
        super().__init__(placeholder="Choose ticket category...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        cat_id = TICKET_CATEGORY_IDS[self.values[0]]
        category = bot.get_channel(cat_id)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket = await category.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites)
        embed = discord.Embed(
            title=f"{EMOJI_1} Ticket",
            description="Use the buttons below to manage your ticket.",
            color=0x313D61
        )
        view = TicketView()
        await ticket.send(embed=embed, view=view)
        await interaction.response.send_message("Ticket created.", ephemeral=True)

class TicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketButton("Claim", True))
        self.add_item(TicketButton("Close", False))

class TicketButton(ui.Button):
    def __init__(self, label, is_claim: bool):
        super().__init__(label=label, style=discord.ButtonStyle.primary if is_claim else discord.ButtonStyle.danger)
        self.is_claim = is_claim

    async def callback(self, interaction: discord.Interaction):
        if self.is_claim:
            await interaction.response.send_message(f"{interaction.user} claimed the ticket.", ephemeral=True)
        else:
            await interaction.channel.delete()

@tree.command(guild=discord.Object(id=GUILD_ID), name="ticketpanel", description="Send ticket panel")
async def ticketpanel(interaction: discord.Interaction):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You lack permissions.", ephemeral=True)
        return
    embed = discord.Embed(
        title=f"{EMOJI_1} Open a Ticket",
        description="Select the ticket category from the dropdown below.",
        color=0x313D61
    )
    view = ui.View()
    view.add_item(TicketDropdown())
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# -------------------------------
# BOT EVENTS
# -------------------------------
@bot.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user}.")

# -------------------------------
# FLASK SERVER
# -------------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

async def start_bot():
    await bot.start(TOKEN)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
