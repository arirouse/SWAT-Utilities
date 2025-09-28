import os
import discord
from discord.ext import commands
from discord import app_commands, Interaction, ButtonStyle
from discord.ui import View, Button
from flask import Flask
import threading

# Flask app for uptime
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# Discord bot setup
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ENV variables
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
DESK_CATEGORY = int(os.getenv("DESK_CATEGORY"))
HR_CATEGORY = int(os.getenv("HR_CATEGORY"))
IA_CATEGORY = int(os.getenv("IA_CATEGORY"))
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL"))

# ---------------- Ticket Panel ----------------
class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Desk", style=ButtonStyle.green, custom_id="desk"))
        self.add_item(Button(label="HR", style=ButtonStyle.blurple, custom_id="hr"))
        self.add_item(Button(label="IA", style=ButtonStyle.gray, custom_id="ia"))

    @discord.ui.button(label="Desk", style=ButtonStyle.green, custom_id="desk")
    async def desk(self, interaction: Interaction, button: Button):
        await self.create_ticket(interaction, "desk", DESK_CATEGORY)

    @discord.ui.button(label="HR", style=ButtonStyle.blurple, custom_id="hr")
    async def hr(self, interaction: Interaction, button: Button):
        await self.create_ticket(interaction, "hr", HR_CATEGORY)

    @discord.ui.button(label="IA", style=ButtonStyle.gray, custom_id="ia")
    async def ia(self, interaction: Interaction, button: Button):
        await self.create_ticket(interaction, "ia", IA_CATEGORY)

    async def create_ticket(self, interaction, ticket_type, category_id):
        guild = interaction.guild
        category = guild.get_channel(category_id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        ticket_channel = await guild.create_text_channel(
            f"{ticket_type}-ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        log_channel = guild.get_channel(LOG_CHANNEL)
        if log_channel:
            await log_channel.send(f"📥 Ticket created by {interaction.user.mention}: {ticket_channel.mention}")

        await interaction.response.send_message(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

# ---------------- Slash Commands ----------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))

# Panel command
@bot.tree.command(name="panel", description="Send the ticket panel embed", guild=discord.Object(id=GUILD_ID))
async def panel(interaction: Interaction):
    embed = discord.Embed(title="Support Tickets", description="Click a button below to open a ticket.", color=0x00ff00)
    await interaction.channel.send(embed=embed, view=TicketView())
    await interaction.response.send_message("✅ Panel created", ephemeral=True)

# Close ticket
@bot.tree.command(name="close", description="Close the current ticket", guild=discord.Object(id=GUILD_ID))
async def close(interaction: Interaction):
    if isinstance(interaction.channel, discord.TextChannel):
        log_channel = interaction.guild.get_channel(LOG_CHANNEL)
        if log_channel:
            await log_channel.send(f"📤 Ticket closed by {interaction.user.mention}: {interaction.channel.name}")
        await interaction.channel.delete()
    else:
        await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)

# ---------------- Moderation Commands ----------------
@bot.tree.command(name="kick", description="Kick a user", guild=discord.Object(id=GUILD_ID))
async def kick(interaction: Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"✅ {member.mention} has been kicked. Reason: {reason}")
    log_channel = interaction.guild.get_channel(LOG_CHANNEL)
    if log_channel:
        await log_channel.send(f"👢 {member} was kicked by {interaction.user.mention}. Reason: {reason}")

@bot.tree.command(name="ban", description="Ban a user", guild=discord.Object(id=GUILD_ID))
async def ban(interaction: Interaction, member: discord.Member, reason: str = "No reason provided"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"✅ {member.mention} has been banned. Reason: {reason}")
    log_channel = interaction.guild.get_channel(LOG_CHANNEL)
    if log_channel:
        await log_channel.send(f"🔨 {member} was banned by {interaction.user.mention}. Reason: {reason}")

@bot.tree.command(name="timeout", description="Timeout a user (in minutes)", guild=discord.Object(id=GUILD_ID))
async def timeout(interaction: Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    until = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
    await member.timeout(until, reason=reason)
    await interaction.response.send_message(f"✅ {member.mention} has been timed out for {minutes} minutes. Reason: {reason}")
    log_channel = interaction.guild.get_channel(LOG_CHANNEL)
    if log_channel:
        await log_channel.send(f"⏰ {member} was timed out by {interaction.user.mention} for {minutes} minutes. Reason: {reason}")

# ---------------- Run Bot + Flask ----------------
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.run(TOKEN)
