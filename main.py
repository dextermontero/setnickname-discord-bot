import discord, json, asyncio
# import logging
from discord.ext import commands
from decouple import config
from discord import HTTPException

TOKEN = config("DISCORD_TOKEN")
SERVER_DATA = "settings.json"

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix = '!', intents = intents)

def load_settings():
    try:
        with open(SERVER_DATA, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_settings(settings):
    with open(SERVER_DATA, 'w') as f:
        json.dump(settings, f, indent=4)

SETTINGS = load_settings()
bot.help_command = None

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        error_message = "Oops! That command doesn't exist. Type `!helps` for available commands."
    elif isinstance(error, commands.MissingRole):
        error_message = "You don't have the required role to use this command."
    elif isinstance(error, commands.MissingPermissions):
        error_message = "You need the manage channels permission to use this command."
    elif isinstance(error, HTTPException) and error.status == 429:
        error_message = "Rate limit hit. Please try again later."
    else:
        error_message = "An unexpected error occurred."

    embed = discord.Embed(title="Error", description=error_message, color=discord.Color.red())
    await ctx.send(embed=embed)

@bot.command(name='helps')
async def help_command(ctx):
    commands_list = [
        '!setlogs - Setup your audit logs for admin using: `!setlogs channel_id`.',
        '!setnick - Setup your In-Game Name using: `!setnick your_nickname`',
        '!delnick - Remove nickname of member using: `!delnick member_id`',
        '!setchannel - Set up your channel to change the nicknames of existing members.'
    ]

    embed = discord.Embed(title="Available Commands", description="\n".join(commands_list), color=discord.Color.blue())
    await ctx.send(embed=embed)

@bot.command(name='setnick')
@commands.cooldown(1, 5, commands.BucketType.user)  # 1 use every 5 seconds
async def setnick(ctx, *, new_nickname: str):
    guild_id = str(ctx.guild.id)
    user_id = str(ctx.author.id)

    load_nickname = load_settings()

    user_nicknames = load_nickname.setdefault(guild_id, {}).setdefault("nicknames", {})
    temp_channel_prefix = f"{ctx.author.name}-temp-channel-bot"

    if user_id in user_nicknames:
        await ctx.send("```fix\nYou have already set your nickname. Contact the server administrator for changes.```")
        await asyncio.sleep(5)
        for channel in ctx.guild.channels:
            if isinstance(channel, discord.TextChannel) and temp_channel_prefix in channel.name:
                await channel.delete()
                print(f'Deleted temporary channel: {channel.name}')
        return
    
    audit_logs_id = load_nickname[guild_id].get('channel_logs_id')
    
    if not ctx.channel.name.startswith(temp_channel_prefix) and ctx.channel.id != audit_logs_id:
            return await ctx.send("```fix\nYou can't use !setnick in this channel!```")

    if ctx.guild.me.guild_permissions.manage_nicknames:
        try:
            await ctx.author.edit(nick=new_nickname)
            user_nicknames[user_id] = new_nickname
            save_settings(load_nickname)
            await ctx.send(f'Your nickname has been changed to **{new_nickname}**!')
        except discord.Forbidden:
            await ctx.send("I don't have permission to change your nickname.")
        except discord.HTTPException:
            await ctx.send("An error occurred while trying to change your nickname.")
    else:
        await ctx.send("I don't have permission to manage nicknames in this server.")

@bot.command(name='delnick')
@commands.cooldown(1, 5, commands.BucketType.user)  # 1 use every 5 seconds
@commands.has_permissions(manage_nicknames=True)
async def delnick(ctx, nickname_id: str):
    load_nickname = load_settings()
    try:
        guild_data = load_nickname[str(ctx.guild.id)]

        if nickname_id in guild_data['nicknames']:
            del guild_data['nicknames'][nickname_id]
            save_settings(load_nickname)
            await ctx.send(f"```fix\nNickname with ID {nickname_id} has been removed.```")
        else:
            await ctx.send('```fix\nNickname ID not found!```')

        # logging.info(f"Nickname ID {nickname_id} removed by {ctx.author} from guild {ctx.guild.id}.")
    except KeyError:
        await ctx.send("Error: This guild does not have any associated data.")
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")

@bot.command(name='setlogs')
@commands.has_permissions(manage_channels=True)
async def setlogs(ctx, *, sid: str):
    await set_channel_id(ctx, "Audit Logs", sid, "audit_logs_id")

@bot.command(name='setchannel')
@commands.has_permissions(manage_channels=True)
async def setchannel(ctx, *, sid: str):
    await set_channel_id(ctx, "Channel ID", sid, "channel_logs_id")

async def set_channel_id(ctx, channel_type: str, channel_id: str, key: str):
    settings = load_settings()
    guild_id = str(ctx.guild.id)

    settings.setdefault(guild_id, {})[key] = int(channel_id)

    save_settings(settings)
    embed = discord.Embed(title="Channel ID Updated", description=f"{channel_type} set successfully.", color=discord.Color.blue())
    await ctx.send(embed=embed)

@bot.event
async def on_guild_join(guild):
    settings = load_settings()
    settings[str(guild.id)] = {"discord_name": str(guild.name)}
    save_settings(settings)

    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send("Hello! Thank you for inviting me! Please configure me using the setup commands. !helps")
            break

@bot.event
async def on_member_join(member):
    load_server = load_settings()
    guild_id = str(member.guild.id)
    member_id = str(member.id)

    user_nicknames = load_server.setdefault(guild_id, {}).setdefault("nicknames", {})

    if member_id in user_nicknames:
        nickname = user_nicknames[member_id]
        await member.edit(nick=nickname)

        channel_id = load_server[guild_id].get('audit_logs_id')
        if channel_id:
            audit_logs = bot.get_channel(int(channel_id))
            await audit_logs.send(f'{member.name} has rejoined the discord server and automatically changed their nickname to **{nickname}**!')
        return

    temp_channel = await create_temp_channel(member)
    await handle_temp_channel(member, temp_channel)

async def create_temp_channel(member):
    guild = member.guild


    async def delete_temp_channels(guild):
        temp_channel_prefix = "temp-channel-bot"
        for channel in guild.channels:
            if isinstance(channel, discord.TextChannel) and temp_channel_prefix in channel.name:
                await channel.delete()
                print(f'Deleted temporary channel: {channel.name}')

    await delete_temp_channels(member.guild)

    channel_name = f"{member.name}-temp-channel-bot"
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(read_messages=True),
        bot.user: discord.PermissionOverwrite(read_messages=True),
    }
    return await guild.create_text_channel(channel_name, overwrites=overwrites)

async def handle_temp_channel(member, temp_channel):
    await temp_channel.send(
        f'Welcome {member.mention}! Please set your In-game Name using: `!setnick your_ign`.\n'
        f'This channel will be deleted automatically after 5 minutes or once you set your nickname.'
    )

    def check(m):
        return m.author == member and m.channel == temp_channel and m.content.startswith('!setnick ')

    try:
        msg = await bot.wait_for('message', check=check, timeout=300)
        new_nickname = msg.content[len('!setnick '):]
        await member.edit(nick=new_nickname)
        channel_id = load_settings()[str(member.guild.id)].get('audit_logs_id')
        if channel_id:
            audit_logs = bot.get_channel(int(channel_id))
            await audit_logs.send(f'{member.name} has set their nickname to **{new_nickname}**!')
        await asyncio.sleep(5)
        await temp_channel.delete()
    except asyncio.TimeoutError:
        await temp_channel.send(f'{member.mention}, you took too long to set your nickname!')   

bot.run(TOKEN)