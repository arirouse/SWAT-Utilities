import discord
from discord import ui
from discord.ext import commands
import os
import asyncio
from io import StringIO

# --- Environment Variables (Render) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
SAY_ROLE_ID = int(os.getenv("SAY_ROLE_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
DESK_CATEGORY_ID = int(os.getenv("DESK_CATEGORY_ID"))
IA_CATEGORY_ID = int(os.getenv("IA_CATEGORY_ID"))
HR_CATEGORY_ID = int(os.getenv("HR_CATEGORY_ID"))

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Logging Helper ---
async def log_action(action, user, channel, details=None):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    embed = discord.Embed(
        title="<:emoji_1:1401614346316021813> " + action,
        description=f"User: {user.mention}\nChannel: {channel.mention}"
    )
    if details:
        embed.add_field(name="Details", value=details, inline=False)
    await log_channel.send(embed=embed)

# --- /ping command ---
@bot.tree.command(name="ping", description="Check if bot is online")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! {latency}ms", ephemeral=True)

# --- Ticket Dropdown ---
class TicketDropdown(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Desk Support", description="For general issues/questions"),
            discord.SelectOption(label="IA", description="For IA-related issues"),
            discord.SelectOption(label="HR", description="For HR-related issues")
        ]
        super().__init__(placeholder="Select ticket type...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        category_id = DESK_CATEGORY_ID if self.values[0] == "Desk Support" else IA_CATEGORY_ID if self.values[0] == "IA" else HR_CATEGORY_ID
        category = interaction.guild.get_channel(category_id)
        ticket_channel = await interaction.guild.create_text_channel(
            name=f"{self.values[0]}-{user.name}",
            category=category,
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                discord.Object(id=MOD_ROLE_ID): discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
        )
        await interaction.response.send_message(
            f"{user.mention}, your ticket has been created: {ticket_channel.mention}",
            ephemeral=True
        )
        embed = discord.Embed(
            title=f"<:emoji_1:1401614346316021813> {self.values[0]} Ticket",
            description=f"Ticket opened by {user.mention}\nClaimed by: None"
        )
        view = ui.View()
        view.add_item(ClaimButton())
        view.add_item(CloseButton())
        ticket_msg = await ticket_channel.send(embed=embed, view=view)
        await log_action("Ticket Created", user, ticket_channel, f"Type: {self.values[0]}")

# --- Claim / Unclaim Buttons ---
class ClaimButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.green, label="Claim")

    async def callback(self, interaction: discord.Interaction):
        ticket_channel = interaction.channel
        ticket_msg = interaction.message
        if getattr(ticket_channel, "claimed_by", None):
            await interaction.response.send_message(
                f"This ticket is already claimed by {ticket_channel.claimed_by.mention}.",
                ephemeral=True
            )
            return
        ticket_channel.claimed_by = interaction.user
        embed = ticket_msg.embeds[0]
        embed.set_field_at(0, name="Claimed by", value=interaction.user.mention, inline=False)
        view = ui.View()
        view.add_item(UnclaimButton())
        view.add_item(CloseButton())
        await ticket_msg.edit(embed=embed, view=view)
        confirm_embed = discord.Embed(
            title="<:emoji_1:1401614346316021813> Ticket Claimed",
            description=f"{interaction.user.mention} has claimed this ticket."
        )
        await ticket_channel.send(embed=confirm_embed)
        await log_action("Ticket Claimed", interaction.user, ticket_channel)

class UnclaimButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.grey, label="Unclaim")

    async def callback(self, interaction: discord.Interaction):
        ticket_channel = interaction.channel
        ticket_msg = interaction.message
        if getattr(ticket_channel, "claimed_by", None) != interaction.user:
            await interaction.response.send_message(
                "You cannot unclaim this ticket (not the claimer).",
                ephemeral=True
            )
            return
        ticket_channel.claimed_by = None
        embed = ticket_msg.embeds[0]
        embed.set_field_at(0, name="Claimed by", value="None", inline=False)
        view = ui.View()
        view.add_item(ClaimButton())
        view.add_item(CloseButton())
        await ticket_msg.edit(embed=embed, view=view)
        await log_action("Ticket Unclaimed", interaction.user, ticket_channel)

class CloseButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.red, label="Close")

    async def callback(self, interaction: discord.Interaction):
        ticket_channel = interaction.channel
        messages = await ticket_channel.history(limit=None, oldest_first=True).flatten()
        transcript_buffer = StringIO()
        for msg in messages:
            transcript_buffer.write(f"{msg.author}: {msg.content}\n")
        transcript_buffer.seek(0)
        file_name = f"purged_messages_{ticket_channel.id}.txt"
        file = discord.File(fp=transcript_buffer, filename=file_name)
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        embed = discord.Embed(
            title="<:emoji_1:1401614346316021813> Ticket Closed",
            description=f"Ticket {ticket_channel.name} closed by {interaction.user.mention}.\nTranscript attached."
        )
        await log_channel.send(embed=embed, file=file)
        await ticket_channel.delete()

# --- /panel command ---
@bot.tree.command(name="panel", description="Posts the ticket panel (MOD only, visible to everyone)")
async def panel(interaction: discord.Interaction):
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot use this.", ephemeral=True)
        return
    embed = discord.Embed(
        title="<:emoji_1:1401614346316021813> Open a Ticket",
        description="""\
<:icon3:1420478187917283410> Guidelines
<:icon9:1420479660222841063> Tickets are designed for serious support matters only. Always select the correct category and clearly explain your issue so staff can assist quickly. Misuse of the ticket system, such as trolling or opening tickets without reason, may lead to warnings, ticket closures, or disciplinary action.

<:icon5:1420478145307476038> Desk Support
<:icon9:1420479660222841063> Inquiries, questions. Typically faster responses and age verification.

<:icon4:1420478165754712148> Internal Affairs
<:icon9:1420479660222841063> Handling Officer reports, cases. This requires department lawyers.

<:icon6:1420478130157785271> HR+ Support
<:icon9:1420479660222841063> Speaking to Director/SHR+, told by HR to open and etc."""
    )
    view = ui.View()
    view.add_item(TicketDropdown())
    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

# --- /add command ---
@bot.tree.command(name="add", description="Add a user to a ticket")
async def add_user(interaction: discord.Interaction, member: discord.Member):
    ticket_channel = interaction.channel
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot do this.", ephemeral=True)
        return
    await ticket_channel.set_permissions(member, view_channel=True, send_messages=True)
    await interaction.response.send_message(f"{member.mention} has been added to the ticket.", ephemeral=True)
    await log_action("User Added to Ticket", interaction.user, ticket_channel, f"Added {member.mention}")

# --- /remove command ---
@bot.tree.command(name="remove", description="Remove a user from a ticket")
async def remove_user(interaction: discord.Interaction, member: discord.Member):
    ticket_channel = interaction.channel
    if MOD_ROLE_ID not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You cannot do this.", ephemeral=True)
        return
    await ticket_channel.set_permissions(member, overwrite=None)
    await interaction.response.send_message(f"{member.mention} has been removed from the ticket.", ephemeral=True)
    await log_action("User Removed from Ticket", interaction.user, ticket_channel, f"Removed {member.mention}")

# --- Bot Activity ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Created by RE3"))

# --- Start bot ---
bot.run(BOT_TOKEN)
