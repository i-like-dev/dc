import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import os

# --------------------------- 設定 ---------------------------
TOKEN = os.environ.get('DISCORD_TOKEN')
GUILD_ID = 1227929105018912839
ADMIN_ROLE_ID = 1227938559130861578

# --------------------------- Bot 設定 ---------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents, help_command=None)

# --------------------------- Bot 狀態設定 ---------------------------
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game('暑假作業'))
    print(f'Logged in as {bot.user}')

# --------------------------- 權限檢查 ---------------------------
def is_admin():
    def predicate(interaction: discord.Interaction) -> bool:
        return any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles)
    return app_commands.check(predicate)

# --------------------------- 使用者權限控制 ---------------------------
user_permissions = {}

async def check_permission(interaction: discord.Interaction):
    if any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles) or user_permissions.get(interaction.user.id, False):
        return True
    else:
        await interaction.response.send_message('你沒有權限使用此功能。', ephemeral=True)
        return False

# --------------------------- 警告系統 ---------------------------
warnings = {}
warning_limit = 5
mute_duration = 600

async def warn_member(interaction, member: discord.Member, reason:str):
    if not await check_permission(interaction):
        return
    warnings[member.id] = warnings.get(member.id,0)+1
    await interaction.response.send_message(f'{member} 被警告 ({warnings[member.id]}/{warning_limit}) 原因: {reason}')
    if warnings[member.id]>=warning_limit:
        await mute_member(interaction, member, mute_duration)
        warnings[member.id]=0

async def mute_member(interaction, member: discord.Member, duration:int = 600):
    mute_role = discord.utils.get(interaction.guild.roles, name='Muted')
    if not mute_role:
        mute_role = await interaction.guild.create_role(name='Muted')
        for ch in interaction.guild.channels:
            await ch.set_permissions(mute_role, send_messages=False, speak=False)
    await member.add_roles(mute_role)
    await interaction.response.send_message(f'{member} 已被禁言 {duration//60} 分鐘')
    await asyncio.sleep(duration)
    await member.remove_roles(mute_role)
    await interaction.followup.send(f'{member} 的禁言已解除')

# --------------------------- 管理、公告、私訊功能 ---------------------------
@bot.tree.command(name='grant_admin_access', description='管理員開通特定使用者管理權限')
@is_admin()
async def grant_admin_access(interaction: discord.Interaction, member: discord.Member):
    user_permissions[member.id] = True
    await interaction.response.send_message(f'{member} 已被授予管理功能使用權限')

@bot.tree.command(name='revoke_admin_access', description='管理員解除特定使用者管理權限')
@is_admin()
async def revoke_admin_access(interaction: discord.Interaction, member: discord.Member):
    user_permissions[member.id] = False
    await interaction.response.send_message(f'{member} 的管理功能使用權限已被撤銷')

@bot.tree.command(name='announce', description='管理員發布公告')
@is_admin()
async def announce(interaction: discord.Interaction, message: str):
    for channel in interaction.guild.text_channels:
        try:
            await channel.send(f'📢 公告: {message}')
        except:
            continue
    await interaction.response.send_message('公告已發佈。', ephemeral=True)

@bot.tree.command(name='dm_user', description='私訊特定用戶')
@is_admin()
async def dm_user(interaction: discord.Interaction, member: discord.Member, message: str):
    try:
        await member.send(f'📩 管理員訊息: {message}')
        await interaction.response.send_message(f'訊息已發送給 {member}.', ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message('無法私訊此用戶。', ephemeral=True)

# --------------------------- 娛樂/工具/互動功能（手動添加不重複） ---------------------------
@bot.tree.command(name='coinflip', description='擲硬幣')
async def coinflip(interaction: discord.Interaction):
    result = random.choice(['正面','反面'])
    await interaction.response.send_message(f'🪙 硬幣結果: {result}')

@bot.tree.command(name='roll_dice', description='擲骰子')
async def roll_dice(interaction: discord.Interaction, sides: int = 6):
    result = random.randint(1, sides)
    await interaction.response.send_message(f'🎲 骰子結果: {result}')

@bot.tree.command(name='random_joke', description='隨機笑話')
async def random_joke(interaction: discord.Interaction):
    jokes = ['為什麼電腦冷？因為它有風扇','為什麼程式員喜歡戶外？因為他們討厭Bug']
    await interaction.response.send_message(random.choice(jokes))

@bot.tree.command(name='math_quiz', description='數學測驗')
async def math_quiz(interaction: discord.Interaction):
    a, b = random.randint(1,50), random.randint(1,50)
    await interaction.response.send_message(f'計算: {a} + {b} = ?')

@bot.tree.command(name='reverse_text', description='反轉文字')
async def reverse_text(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text[::-1])

@bot.tree.command(name='random_color', description='隨機顏色')
async def random_color(interaction: discord.Interaction):
    color = f'#{random.randint(0,0xFFFFFF):06X}'
    await interaction.response.send_message(f'🎨 隨機顏色: {color}')

@bot.tree.command(name='fortune', description='運勢')
async def fortune(interaction: discord.Interaction):
    fortunes = ['大吉','中吉','小吉','凶']
    await interaction.response.send_message(f'🔮 今日運勢: {random.choice(fortunes)}')

@bot.tree.command(name='generate_password', description='生成隨機密碼')
async def generate_password(interaction: discord.Interaction, length: int = 12):
    chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()'
    password = ''.join(random.choice(chars) for _ in range(length))
    await interaction.response.send_message(f'🔑 隨機密碼: {password}')

# --------------------------- /help 指令 ---------------------------
@bot.tree.command(name='help', description='顯示可用指令列表')
async def help_cmd(interaction: discord.Interaction):
    all_commands = [
        'grant_admin_access','revoke_admin_access','announce','dm_user',
        'coinflip','roll_dice','random_joke','math_quiz','reverse_text','random_color','fortune','generate_password'
    ]
    help_text='\n'.join([f'/{cmd}' for cmd in all_commands])
    await interaction.response.send_message(f'📜 可用指令:\n{help_text}', ephemeral=True)

# --------------------------- 啟動 Bot ---------------------------
bot.run(TOKEN)

# 注意: Flask 不再使用，Render 上直接運行 Bot 即可，不需額外依賴
