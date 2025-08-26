import discord
from discord import app_commands
import asyncio
import random
import os

# --------------------------- 設定 ---------------------------
TOKEN = os.environ.get('DISCORD_TOKEN')
GUILD_ID = 1227929105018912839
ADMIN_ROLE_ID = 1227938559130861578

# --------------------------- Bot 設定 ---------------------------
class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.user_permissions = {}
        self.warnings = {}

    async def setup_hook(self):
        # 全域同步 Slash Commands
        await self.tree.sync()
        print("✅ 全域 Slash commands 已同步!")

bot = MyBot()

# --------------------------- Bot 狀態 ---------------------------
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game('HFG 機器人 ・ 照亮你的生活'))
    print(f'Logged in as {bot.user}')

# --------------------------- 權限檢查 ---------------------------
def is_admin():
    def predicate(interaction: discord.Interaction) -> bool:
        return any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles)
    return app_commands.check(predicate)

# --------------------------- 測試指令 ---------------------------
@bot.tree.command(name='ping', description='測試指令')
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('Pong! ✅')

@bot.tree.command(name='help', description='顯示可用指令列表')
async def help_cmd(interaction: discord.Interaction):
    cmds = [c.name for c in bot.tree.get_commands()]
    await interaction.response.send_message('📜 可用指令:\n' + '\n'.join([f'/{c}' for c in cmds]), ephemeral=True)

# --------------------------- 管理功能 ---------------------------
@bot.tree.command(name='clear', description='清除訊息')
@is_admin()
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f'🧹 已清除 {amount} 則訊息', ephemeral=True)

@bot.tree.command(name='lock_channel', description='鎖定頻道')
@is_admin()
async def lock_channel(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message('🔒 頻道已鎖定')

@bot.tree.command(name='unlock_channel', description='解鎖頻道')
@is_admin()
async def unlock_channel(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = True
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message('🔓 頻道已解鎖')

@bot.tree.command(name='kick', description='踢出成員')
@is_admin()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "無理由"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f'👢 {member} 已被踢出，理由: {reason}')

@bot.tree.command(name='ban', description='封鎖成員')
@is_admin()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "無理由"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f'⛔ {member} 已被封鎖，理由: {reason}')

@bot.tree.command(name='unban', description='解除封鎖成員')
@is_admin()
async def unban(interaction: discord.Interaction, user_id: int):
    user = await bot.fetch_user(user_id)
    await interaction.guild.unban(user)
    await interaction.response.send_message(f'✅ {user} 已解除封鎖')

# --------------------------- 公告功能 ---------------------------
@bot.tree.command(name='announce', description='管理員發布公告')
@is_admin()
async def announce(interaction: discord.Interaction, message: str):
    for channel in interaction.guild.text_channels:
        try:
            await channel.send(f'📢 公告: {message}')
        except:
            continue
    await interaction.response.send_message('公告已發佈。', ephemeral=True)

# --------------------------- 私訊功能 ---------------------------
@bot.tree.command(name='dm_user', description='私訊特定用戶')
@is_admin()
async def dm_user(interaction: discord.Interaction, member: discord.Member, message: str):
    try:
        await member.send(f'📩 管理員訊息: {message}')
        await interaction.response.send_message(f'訊息已發送給 {member}.', ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message('無法私訊此用戶。', ephemeral=True)

# --------------------------- 娛樂功能 ---------------------------
@bot.tree.command(name='coinflip', description='擲硬幣')
async def coinflip(interaction: discord.Interaction):
    await interaction.response.send_message(f'🪙 硬幣結果: {random.choice(["正面","反面"])}')

@bot.tree.command(name='roll_dice', description='擲骰子')
async def roll_dice(interaction: discord.Interaction, sides: int):
    await interaction.response.send_message(f'🎲 骰子結果: {random.randint(1,sides)}')

@bot.tree.command(name='truth_or_dare', description='真心話大冒險')
async def truth_or_dare(interaction: discord.Interaction):
    choice = random.choice(['真心話','大冒險'])
    prompt = random.choice(['問題1','問題2','問題3']) if choice=='真心話' else random.choice(['挑戰1','挑戰2','挑戰3'])
    await interaction.response.send_message(f'🎲 {choice}: {prompt}')

@bot.tree.command(name='create_ticket', description='開客服單')
async def create_ticket(interaction: discord.Interaction, reason: str):
    category = discord.utils.get(interaction.guild.categories, name='客服單')
    if not category:
        category = await interaction.guild.create_category('客服單')
    overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                  interaction.user: discord.PermissionOverwrite(view_channel=True)}
    ticket = await interaction.guild.create_text_channel(f'ticket-{interaction.user.name}', category=category, overwrites=overwrites)
    await ticket.send(f'{interaction.user.mention} 已開啟客服單，原因: {reason}')
    await interaction.response.send_message(f'✅ 已建立客服單: {ticket.mention}', ephemeral=True)

# --------------------------- 額外娛樂 ---------------------------
@bot.tree.command(name='hug', description='給予擁抱')
async def hug(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f'🤗 {interaction.user.mention} 擁抱了 {member.mention}!')

@bot.tree.command(name='poll', description='建立投票')
async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str):
    embed = discord.Embed(title=f'📊 {question}', description=f'1️⃣ {option1}\n2️⃣ {option2}', color=0x00ff00)
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction('1️⃣')
    await message.add_reaction('2️⃣')
    await interaction.response.send_message('投票已建立!', ephemeral=True)

@bot.tree.command(name='remind', description='提醒功能 (秒)')
async def remind(interaction: discord.Interaction, time: int, reminder: str):
    await interaction.response.send_message(f'⏰ 好的，我會在 {time} 秒後提醒你: {reminder}', ephemeral=True)
    await asyncio.sleep(time)
    await interaction.followup.send(f'⏰ 提醒: {reminder}')

@bot.tree.command(name='say', description='讓機器人說話')
async def say(interaction: discord.Interaction, message: str):
    await interaction.channel.send(f'{message}')
    await interaction.response.send_message('✅ 已代發訊息', ephemeral=True)

@bot.tree.command(name='server_info', description='查看伺服器資訊')
async def server_info(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f'{guild.name} 資訊', color=0x3498db)
    embed.add_field(name='👑 擁有者', value=guild.owner, inline=False)
    embed.add_field(name='👥 成員數', value=guild.member_count, inline=False)
    embed.add_field(name='📅 建立時間', value=guild.created_at.strftime('%Y-%m-%d'), inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='userinfo', description='查看用戶資訊')
async def userinfo(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(title=f'{member} 的資訊', color=0x95a5a6)
    embed.add_field(name='🆔 ID', value=member.id, inline=False)
    embed.add_field(name='📅 加入伺服器', value=member.joined_at.strftime('%Y-%m-%d'), inline=False)
    embed.add_field(name='📝 建立帳號', value=member.created_at.strftime('%Y-%m-%d'), inline=False)
    await interaction.response.send_message(embed=embed)

# --------------------------- 啟動 Bot ---------------------------
bot.run(TOKEN)
