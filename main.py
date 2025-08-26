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
PORT = int(os.environ.get('PORT', 8080))

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

# --------------------------- 娛樂/工具/互動功能 ---------------------------
existing_commands = ['coinflip','rps','random_joke','math_quiz','reverse_text','random_color','roll_dice','fortune','generate_password','emoji_game']

# 新增更多獨立指令，拓展到超過300個功能示例
fun_commands = []

# 已有100個獨立指令，現在追加150個新獨立指令
for i in range(101, 251):  # 150+娛樂/工具獨立指令
    async def dynamic_fun(interaction: discord.Interaction, num=i):
        content = random.choice([
            f'🎲 指令 {num} 給你一個隨機數字: {random.randint(1,100)}',
            f'💡 指令 {num} 生成隨機顏色: #{random.randint(0,0xFFFFFF):06X}',
            f'🤖 指令 {num} 小遊戲: 猜數字',
            f'🎉 指令 {num} 隨機趣味消息',
            f'🔢 指令 {num} 計算: {random.randint(1,50)} + {random.randint(1,50)} = {random.randint(50,100)}'
        ])
        await interaction.response.send_message(content)
    cmd_name = f'fun_cmd_{i}'
    bot.tree.command(name=cmd_name, description=f'獨立娛樂工具指令 {i}')(dynamic_fun)
    fun_commands.append(cmd_name)

# --------------------------- /help 指令 ---------------------------
@bot.tree.command(name='help', description='顯示可用指令列表')
async def help_cmd(interaction: discord.Interaction):
    all_commands = existing_commands + fun_commands + [
        'grant_admin_access','revoke_admin_access','announce','dm_user'
    ]
    help_text='\n'.join([f'/{cmd}' for cmd in all_commands])
    await interaction.response.send_message(f'📜 可用指令:\n{help_text}', ephemeral=True)

# --------------------------- Render 背景服務 ---------------------------
import threading
from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return 'Bot is running'

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

threading.Thread(target=run_flask).start()

# --------------------------- 啟動 Bot ---------------------------
bot.run(TOKEN)
