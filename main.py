import discord
from discord.ext import commands, tasks
from discord import app_commands, Interaction, ui, Embed
import os
import asyncio
from flask import Flask

# ----------------------
# VARIABLES YOU DEFINED
# ----------------------
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))

LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

DESK_CATEGORY_ID = int(os.getenv("DESK_CATEGORY_ID"))
IA_CATEGORY_ID = int(os.getenv("IA_CATEGORY_ID"))
HR_CATEGORY_ID = int(os.getenv("HR_CATEGORY_ID"))

PORT = int(os.getenv("PORT", 10000))  # Flask port

# ----------------------
# BOT SETUP
# ----------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

# ----------------------
# HELPERS
# ----------------------
def get_category_id(ticket_type: str):
    if ticket_type == "Desk Support":
        return DESK_CATEGORY_ID
    elif ticket_type == "IA":
        return IA_CATEGORY_ID
    elif ticket_type == "HR":
        return HR_CATEGORY_ID

async def log_action(embed: Embed):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)

# ----------------------
# TICKET VIEW
# ----------------------
class TicketDropdown(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Desk Support", description="For desk-related issues"),
            discord.SelectOption(label="IA", description="For IA-related issues"),
            discord.SelectOption(label="HR", description="For HR-related issues")
        ]
        super().__init__(placeholder="Select a ticket type...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        ticket_type = self.values[0]
        category_id = get_category_id(ticket_type)
        category = interaction.guild.get_channel(category_id)
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True)
        }
        ticket_channel = await interaction.guild.create_text_channel(
            f"{ticket_type.lower().replace(' ', '-')}-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        # Ticket embed
        embed = Embed(
            title=f":emoji_1: {ticket_type} Ticket",
            description=f"Ticket opened by {interaction.user.mention}",
            color=0x313D61
        )
        await ticket_channel.send(embed=embed, view=TicketButtons())
        await interaction.response.send_message("Ticket created!", ephemeral=True)

        # Log ticket creation
        log_embed = Embed(
            title=f"Ticket Opened: {ticket_type}",
            description=f"{interaction.user.mention} opened a {ticket_type} ticket",
            color=0x313D61
        )
        await log_action(log_embed)

class TicketDropdownView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(TicketDropdown())

class TicketButtons(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ui.Button(label="Claim", style=discord.ButtonStyle.green, custom_id="claim"))
        self.add_item(ui.Button(label="Unclaim", style=discord.ButtonStyle.gray, custom_id="unclaim"))
        self.add_item(ui.Button(label="Close", style=discord.ButtonStyle.red, custom_id="close"))

    @ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="claim")
    async def claim(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message(f"{interaction.user.mention} claimed this ticket.", ephemeral=True)

    @ui.button(label="Unclaim", style=discord.ButtonStyle.gray, custom_id="unclaim")
    async def unclaim(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message(f"{interaction.user.mention} unclaimed this ticket.", ephemeral=True)

    @ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="close")
    async def close(self, interaction: Interaction, button: ui.Button):
        await interaction.channel.delete()

# ----------------------
# SLASH COMMANDS
# ----------------------
@tree.command(name="panel", description="Send the ticket panel")
async def panel(interaction: Interaction):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    embed = Embed(title=":emoji_1: Open a Ticket", description="Select a ticket type from the dropdown below.", color=0x313D61)
    await interaction.response.send_message(embed=embed, view=TicketDropdownView(), ephemeral=True)

@tree.command(name="say", description="Say something via bot")
async def say(interaction: Interaction, message: str):
    if SAY_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    await interaction.channel.send(message)

@tree.command(name="ping", description="Ping the bot")
async def ping(interaction: Interaction):
    await interaction.response.send_message("Pong!")

# MOD COMMANDS WITH REASON
@tree.command(name="lock", description="Lock this channel")
@app_commands.describe(reason="Reason for locking")
async def lock(interaction: Interaction, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    embed = Embed(title="Channel Locked", description=f"Reason: {reason}", color=0x313D61)
    await log_action(embed)
    await interaction.response.send_message("Channel locked.", ephemeral=True)

@tree.command(name="unlock", description="Unlock this channel")
@app_commands.describe(reason="Reason for unlocking")
async def unlock(interaction: Interaction, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
    embed = Embed(title="Channel Unlocked", description=f"Reason: {reason}", color=0x313D61)
    await log_action(embed)
    await interaction.response.send_message("Channel unlocked.", ephemeral=True)

# ----------------------
# PURGE COMMAND
# ----------------------
@tree.command(name="purge", description="Delete messages in a channel")
@app_commands.describe(amount="Number of messages to delete", reason="Reason for purge")
async def purge(interaction: Interaction, amount: int, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    deleted = await interaction.channel.purge(limit=amount)
    # Save to TXT
    txt_content = "\n".join(f"{m.author}: {m.content}" for m in deleted)
    with open("purged_messages.txt", "w", encoding="utf-8") as f:
        f.write(txt_content)
    embed = Embed(title="Messages Purged", description=f"{len(deleted)} messages purged by {interaction.user.mention}\nReason: {reason}", color=0x313D61)
    await log_action(embed)
    await interaction.response.send_message(f"Purged {len(deleted)} messages.", ephemeral=True)

# ----------------------
# EVENT: ON_READY
# ----------------------
@bot.event
async def on_ready():
    print(f"{bot.user} is online.")
    await tree.sync(guild=discord.Object(id=GUILD_ID))

# ----------------------
# BUTTON INTERACTION HANDLING
# ----------------------
@bot.event
async def on_interaction(interaction: discord.Interaction):
    # Required for button callbacks
    await bot.process_application_commands(interaction)

# ----------------------
# FLASK SERVER
# ----------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ----------------------
# RUN BOT
# ----------------------
async def main():
    loop.create_task(asyncio.to_thread(run_flask))
    await bot.start(TOKEN)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
