import discord
from discord.ext import commands
from decouple import config

# Replace 'YOUR_BOT_TOKEN_HERE' with your actual bot token
TOKEN = config("DISCORD_TOKEN")

# Replace with the ID of the specific channel
SPECIFIC_CHANNEL_ID = config("DISCORD_CHANNEL_LOGS")  # Change this to your channel ID

intents = discord.Intents.default()
intents.members = True # Enable the member intent
intents.guilds = True # Enable the guild intent
intents.message_content = True  # Enable message content intent

bot = commands.Bot(command_prefix = '!', intents = intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

@bot.event
async def on_member_join(member):
    # Create a temporary text channel for the user
    guild = member.guild
    server_name = guild.name
    channel_name = f"{member.name}-temp-channel"

    # Define the overwrites for the channel
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),  # Deny @everyone
        member: discord.PermissionOverwrite(read_messages=True),  # Allow the user
        bot.user: discord.PermissionOverwrite(read_messages=True),  # Allow the bot
    }

    # Create the channel
    temp_channel = await guild.create_text_channel(channel_name, overwrites=overwrites)

    # Send a message to the member in their temporary channel
    await temp_channel.send(
        f'Welcome to {server_name}, {member.mention}! Please set your In-game Name using the command: `!setnick <new_nickname>`.\n'
        f'This channel will be deleted automatically after you set your nickname or after 5 minutes.'
    )
    
    # Wait for a nickname change or a timeout
    def check(m):
        return m.author == member and m.channel == temp_channel and m.content.startswith('!setnick')
    
    try:
        # Wait for the nickname command
        msg = await bot.wait_for('message', check=check, timeout=300)  # 5 minutes timeout
        new_nickname = msg.content[len('!setnick '):]

        # Change the nickname
        await member.edit(nick=new_nickname)
        # Send the new nickname to the specific channel
        try:
            specific_channel = await bot.fetch_channel(SPECIFIC_CHANNEL_ID)
            await specific_channel.send(f'{member.mention} has changed their nickname!')
        except discord.NotFound:
            print("The channel was not found.")
        except discord.Forbidden:
            print("The bot does not have permission to send messages in this channel.")
        except discord.HTTPException as e:
            print(f"Failed to send message: {e}")
    except Exception as e:
        await temp_channel.send(f"An error occurred: {e}")

    # Delete the temporary channel
    await temp_channel.delete()

@bot.command()
async def setnick(ctx, *, new_nickname: str):
    """Command to change the user's nickname."""
    if ctx.author.guild_permissions.change_nickname:
        try:
            await ctx.author.edit(nick=new_nickname)
            await ctx.send(f'Your nickname has been changed to **{new_nickname}**!')
        except discord.Forbidden:
            await ctx.send("I don't have permission to change your nickname.")
        except discord.HTTPException:
            await ctx.send("An error occurred while trying to change your nickname.")
    else:
        await ctx.send("You do not have permission to change your nickname.")

bot.run(TOKEN)