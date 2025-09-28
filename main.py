import os
import discord
from discord.ext import commands
from discord import app_commands, Interaction, ui
import asyncio
from flask import Flask

# ---------- CONFIG ----------
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))

LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

TICKET_CATEGORIES = {
    "Desk Support": int(os.getenv("DESK_CAT_ID")),
    "IA": int(os.getenv("IA_CAT_ID")),
    "HR": int(os.getenv("HR_CAT_ID"))
}

TICKET_CHANNELS = {
    "Desk Support": int(os.getenv("DESK_LOG_ID")),
    "IA": int(os.getenv("IA_LOG_ID")),
    "HR": int(os.getenv("HR_LOG_ID"))
}

EMOJI_1 = ":emoji_1:"  # actual server emoji, type it exactly like Discord

# ---------- BOT SETUP ----------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# ---------- LOGGING FUNCTION ----------
async def log_action(action, member, reason=None, extra=None):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    msg = f"**{action}** - {member} ({member.id})"
    if reason:
        msg += f" | Reason: {reason}"
    if extra:
        msg += f" | {extra}"
    await log_channel.send(msg)

# ---------- TICKET PANEL ----------
class TicketDropdown(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=name, description=f"Open a ticket for {name}", value=name)
            for name in TICKET_CATEGORIES
        ]
        super().__init__(placeholder="Select Ticket Category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        category_name = self.values[0]
        cat_id = TICKET_CATEGORIES[category_name]
        ticket_channel = await interaction.guild.create_text_channel(
            f"{category_name.lower()}-{interaction.user.name}", category=interaction.guild.get_channel(cat_id)
        )
        await ticket_channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        await ticket_channel.set_permissions(interaction.guild.default_role, read_messages=False)
        # Ticket buttons
        await ticket_channel.send(
            embed=discord.Embed(title=f"{EMOJI_1} Ticket: {category_name}", description=f"Ticket opened by {interaction.user}"),
            view=TicketView()
        )
        await interaction.response.send_message("Ticket created!", ephemeral=True)

class TicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketButton("Claim"))
        self.add_item(TicketButton("Unclaim"))
        self.add_item(TicketButton("Close"))

class TicketButton(ui.Button):
    def __init__(self, label):
        super().__init__(label=label, style=discord.ButtonStyle.primary)

    async def callback(self, interaction: Interaction):
        if self.label == "Claim":
            await interaction.channel.set_permissions(interaction.user, manage_messages=True)
            await interaction.response.send_message(f"{interaction.user} claimed the ticket.", ephemeral=True)
        elif self.label == "Unclaim":
            await interaction.channel.set_permissions(interaction.user, manage_messages=False)
            await interaction.response.send_message(f"{interaction.user} unclaimed the ticket.", ephemeral=True)
        elif self.label == "Close":
            await interaction.channel.delete()

@bot.tree.command(name="ticket_panel", description="Send ticket panel")
async def ticket_panel(interaction: Interaction):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You do not have permission.", ephemeral=True)
        return
    embed = discord.Embed(title=f"{EMOJI_1} Open a Ticket", description="Select a category below")
    view = ui.View()
    view.add_item(TicketDropdown())
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ---------- MOD COMMANDS ----------
@bot.tree.command(name="kick", description="Kick a member")
@app_commands.describe(member="Member to kick", reason="Reason for kick")
async def kick(interaction: Interaction, member: discord.Member, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("No permission", ephemeral=True)
        return
    await member.kick(reason=reason)
    await log_action("Kick", member, reason)
    await interaction.response.send_message(f"{member} has been kicked.", ephemeral=True)

@bot.tree.command(name="ban", description="Ban a member")
@app_commands.describe(member="Member to ban", reason="Reason for ban")
async def ban(interaction: Interaction, member: discord.Member, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("No permission", ephemeral=True)
        return
    await member.ban(reason=reason)
    await log_action("Ban", member, reason)
    await interaction.response.send_message(f"{member} has been banned.", ephemeral=True)

@bot.tree.command(name="mute", description="Timeout a member")
@app_commands.describe(member="Member to timeout", reason="Reason")
async def mute(interaction: Interaction, member: discord.Member, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("No permission", ephemeral=True)
        return
    await member.timeout(duration=3600, reason=reason)
    await log_action("Timeout", member, reason)
    await interaction.response.send_message(f"{member} has been timed out.", ephemeral=True)

@bot.tree.command(name="purge", description="Delete messages")
@app_commands.describe(amount="Number of messages to delete", reason="Reason")
async def purge(interaction: Interaction, amount: int, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("No permission", ephemeral=True)
        return
    messages = await interaction.channel.purge(limit=amount)
    # Save messages to TXT in log channel
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    with open("purge_log.txt", "w") as f:
        for m in messages:
            f.write(f"{m.author}: {m.content}\n")
    await log_channel.send(file=discord.File("purge_log.txt"))
    await log_action("Purge", interaction.user, reason, f"Deleted {len(messages)} messages")
    await interaction.response.send_message(f"{len(messages)} messages deleted.", ephemeral=True)

@bot.tree.command(name="say", description="Say something")
@app_commands.describe(message="Message to say")
async def say(interaction: Interaction, message: str):
    if SAY_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    await interaction.channel.send(message)
    await interaction.response.send_message("Message sent.", ephemeral=True)

@bot.tree.command(name="ping", description="Ping the bot")
async def ping(interaction: Interaction):
    await interaction.response.send_message("Pong!")

# ---------- LOCK / UNLOCK ----------
@bot.tree.command(name="lock", description="Lock a channel")
@app_commands.describe(reason="Reason for locking")
async def lock(interaction: Interaction, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await log_action("Lock", interaction.user, reason)
    await interaction.response.send_message("Channel locked.", ephemeral=True)

@bot.tree.command(name="unlock", description="Unlock a channel")
@app_commands.describe(reason="Reason for unlocking")
async def unlock(interaction: Interaction, reason: str):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await log_action("Unlock", interaction.user, reason)
    await interaction.response.send_message("Channel unlocked.", ephemeral=True)

# ---------- RUN BOT ----------
async def main():
    async with bot:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        await bot.start(TOKEN)

if __name__ == "__main__":
    # Run Flask server in background
    app = Flask(__name__)

    @app.route("/")
    def home():
        return "Bot is running."

    # Run bot
    asyncio.run(main())
