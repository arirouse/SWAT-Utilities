import discord
from discord.ext import commands
from discord import app_commands, ui, Interaction
from discord.ui import View, Button, Select, Modal, TextInput
import os
import asyncio

from flask import Flask
from threading import Thread

app = Flask("")

@app.route("/")
def home():
    return "Bot is alive!"

def run():
    app.run(host="0.0.0.0", port=8080)

# Run Flask in a separate thread
Thread(target=run).start()

TOKEN = os.getenv("DISCORD_TOKEN")  # Set this in Render environment variables
GUILD_ID = int(os.getenv("GUILD_ID"))  # Your server ID
TICKET_CATEGORY_NAMES = {
    "desk": "Desk Support",
    "internal": "Internal Affairs",
    "hr": "HR+ Support"
}
EMOJI_SERVER = ":emoji_1:"  # Replace with actual emoji or unicode
EMBED_COLOR = 0x313D61

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

class TicketReasonModal(Modal, title="Ticket Reason"):
    reason_input = TextInput(label="Issue / Reason", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, category_key, author):
        super().__init__()
        self.category_key = category_key
        self.author = author

    async def on_submit(self, interaction: Interaction):
        guild = interaction.guild
        category_name = TICKET_CATEGORY_NAMES[self.category_key]

        # Find or create the Discord category
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            category = await guild.create_category(category_name)

        # Create the ticket channel
        channel_name = f"ticket-{self.author.name}".lower()
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.author: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        # Allow staff roles (assumes role names include 'Staff'; adjust as needed)
        for role in guild.roles:
            if "Staff" in role.name:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        ticket_channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites
        )

        # Send ticket embed
        embed = discord.Embed(
            title=f"{EMOJI_SERVER} Ticket Created",
            description=f"Hello {self.author.mention}! A staff member will be with you shortly.",
            color=EMBED_COLOR
        )
        embed.add_field(name="Category", value=category_name, inline=False)
        embed.add_field(name="User", value=self.author.mention, inline=False)
        embed.add_field(name="Issue", value=self.reason_input.value, inline=False)
        embed.set_footer(text="Staff will respond here shortly.")

        # Send buttons view
        view = TicketButtonsView(ticket_channel, self.author)
        await ticket_channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

class TicketButtonsView(View):
    def __init__(self, ticket_channel, author):
        super().__init__(timeout=None)
        self.ticket_channel = ticket_channel
        self.author = author

        # Buttons
        self.add_item(Button(label="Claim", style=discord.ButtonStyle.success, custom_id="claim"))
        self.add_item(Button(label="Add User", style=discord.ButtonStyle.primary, custom_id="add"))
        self.add_item(Button(label="Remove User", style=discord.ButtonStyle.primary, custom_id="remove"))
        self.add_item(Button(label="Close", style=discord.ButtonStyle.danger, custom_id="close"))

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, custom_id="claim")
    async def claim(self, interaction: Interaction, button: Button):
        embed = discord.Embed(
            title=f"{EMOJI_SERVER} Ticket Claimed",
            description=f"{interaction.user.mention} has claimed this ticket.",
            color=EMBED_COLOR
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @discord.ui.button(label="Add User", style=discord.ButtonStyle.primary, custom_id="add")
    async def add_user(self, interaction: Interaction, button: Button):
        modal = AddRemoveUserModal(action="add", ticket_channel=self.ticket_channel)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Remove User", style=discord.ButtonStyle.primary, custom_id="remove")
    async def remove_user(self, interaction: Interaction, button: Button):
        modal = AddRemoveUserModal(action="remove", ticket_channel=self.ticket_channel)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="close")
    async def close_ticket(self, interaction: Interaction, button: Button):
        embed = discord.Embed(
            title=f"{EMOJI_SERVER} Ticket Closed",
            description="This ticket has been closed.",
            color=EMBED_COLOR
        )
        await self.ticket_channel.send(embed=embed)
        await asyncio.sleep(2)
        await self.ticket_channel.delete()

class AddRemoveUserModal(Modal, title="Modify Ticket Users"):
    user_input = TextInput(label="@mention the user", style=discord.TextStyle.short, required=True)

    def __init__(self, action, ticket_channel):
        super().__init__()
        self.action = action
        self.ticket_channel = ticket_channel

    async def on_submit(self, interaction: Interaction):
        guild = interaction.guild
        user_mention = self.user_input.value
        try:
            user_id = int(user_mention.strip("<@!>"))
            user = guild.get_member(user_id)
        except:
            await interaction.response.send_message("Invalid user mention.", ephemeral=True)
            return

        if self.action == "add":
            await self.ticket_channel.set_permissions(user, read_messages=True, send_messages=True)
            embed = discord.Embed(
                title=f"{EMOJI_SERVER} User Added",
                description=f"{user.mention} has been added to this ticket.",
                color=EMBED_COLOR
            )
        else:
            await self.ticket_channel.set_permissions(user, overwrite=None)
            embed = discord.Embed(
                title=f"{EMOJI_SERVER} User Removed",
                description=f"{user.mention} has been removed from this ticket.",
                color=EMBED_COLOR
            )
        await self.ticket_channel.send(embed=embed)
        await interaction.response.send_message(f"{self.action.capitalize()}ed {user.mention}.", ephemeral=True)

class TicketCategoryDropdown(View):
    def __init__(self):
        super().__init__(timeout=None)
        options = [
            discord.SelectOption(label="Desk Support", value="desk", description="Inquiries, questions. Typically faster responses and age verification.", emoji=":icon5:"),
            discord.SelectOption(label="Internal Affairs", value="internal", description="Handling Officer reports, cases. This requires department lawyers.", emoji=":icon4:"),
            discord.SelectOption(label="HR+ Support", value="hr", description="Speaking to Director/SHR+, told by HR to open and etc.", emoji=":icon6:")
        ]
        self.add_item(Select(placeholder="Select a ticket category...", options=options, custom_id="ticket_dropdown"))

    @discord.ui.select(custom_id="ticket_dropdown", placeholder="Select a ticket category...")
    async def select_callback(self, interaction: Interaction, select: Select):
        modal = TicketReasonModal(category_key=select.values[0], author=interaction.user)
        await interaction.response.send_modal(modal)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    guild = discord.Object(id=GUILD_ID)
    try:
        # Send the ticket panel to a specific channel, adjust CHANNEL_ID
        channel = bot.get_channel(int(os.getenv("TICKET_PANEL_CHANNEL")))
        embed = discord.Embed(
            title=f"{EMOJI_SERVER} Guidelines",
            description="Tickets are designed for serious support matters only. Always select the correct category and clearly explain your issue so staff can assist quickly. Misuse of the ticket system may lead to warnings, closures, or disciplinary action.",
            color=EMBED_COLOR
        )
        view = TicketCategoryDropdown()
        await channel.send(embed=embed, view=view)
    except Exception as e:
        print("Could not send ticket panel:", e)

# Keep-alive for Render
from flask import Flask
from threading import Thread

app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()
bot.run(TOKEN)
