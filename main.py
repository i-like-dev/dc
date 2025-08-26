import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import asyncio

# --------------------------- Bot 設定 ---------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents, help_command=None)

# --------------------------- Bot 狀態設定 ---------------------------
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game('暑假作業'))
    print(f'Logged in as {bot.user}')

# --------------------------- 用戶警告系統 ---------------------------
warnings = {}
warning_limit = 5
mute_duration = 600  # 10 分鐘

# --------------------------- 管理功能 ---------------------------
async def kick_member(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.guild_permissions.kick_members:
        await member.kick(reason=f'Kicked by {interaction.user}')
        await interaction.response.send_message(f'{member} 已被踢出')

async def ban_member(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.guild_permissions.ban_members:
        await member.ban(reason=f'Banned by {interaction.user}')
        await interaction.response.send_message(f'{member} 已被封鎖')

async def warn_member(interaction: discord.Interaction, member: discord.Member, reason: str):
    if interaction.user.guild_permissions.administrator:
        warnings[member.id] = warnings.get(member.id, 0) + 1
        await interaction.response.send_message(f'{member} 被警告 ({warnings[member.id]}/{warning_limit}) 原因: {reason}')
        if warnings[member.id] >= warning_limit:
            mute_role = discord.utils.get(interaction.guild.roles, name='Muted')
            if not mute_role:
                mute_role = await interaction.guild.create_role(name='Muted')
                for ch in interaction.guild.channels:
                    await ch.set_permissions(mute_role, send_messages=False, speak=False)
            await member.add_roles(mute_role)
            await interaction.channel.send(f'{member} 超過警告次數已被禁言 10 分鐘')
            await asyncio.sleep(mute_duration)
            await member.remove_roles(mute_role)
            warnings[member.id] = 0

async def unwarn_member(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.guild_permissions.administrator:
        warnings[member.id] = 0
        await interaction.response.send_message(f'{member} 的警告已重置')

# 更多管理功能
async def purge_messages(interaction: discord.Interaction, limit: int):
    if interaction.user.guild_permissions.manage_messages:
        deleted = await interaction.channel.purge(limit=limit)
        await interaction.response.send_message(f'已刪除 {len(deleted)} 則訊息', ephemeral=True)

async def add_role(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if interaction.user.guild_permissions.manage_roles:
        await member.add_roles(role)
        await interaction.response.send_message(f'{role} 已新增給 {member}')

async def remove_role(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if interaction.user.guild_permissions.manage_roles:
        await member.remove_roles(role)
        await interaction.response.send_message(f'{role} 已移除 {member}')

# --------------------------- 公告系統 ---------------------------
announcements = {}
async def announce(interaction: discord.Interaction, title: str, content: str):
    if interaction.user.guild_permissions.administrator:
        announcements[title] = content
        await interaction.response.send_message(f'公告 {title} 已發布')

async def edit_announcement(interaction: discord.Interaction, title: str, content: str):
    if title in announcements:
        announcements[title] = content
        await interaction.response.send_message(f'公告 {title} 已更新')

async def delete_announcement(interaction: discord.Interaction, title: str):
    if title in announcements:
        del announcements[title]
        await interaction.response.send_message(f'公告 {title} 已刪除')

async def list_announcements(interaction: discord.Interaction):
    if announcements:
        msg = '\n'.join([f'{t}: {c}' for t,c in announcements.items()])
        await interaction.response.send_message(msg)
    else:
        await interaction.response.send_message('目前沒有公告')

# --------------------------- 私訊系統 ---------------------------
async def dm_user(interaction: discord.Interaction, member: discord.Member, content: str):
    await member.send(content)
    await interaction.response.send_message(f'訊息已發送給 {member}', ephemeral=True)

async def dm_all(interaction: discord.Interaction, content: str):
    for m in interaction.guild.members:
        if not m.bot:
            await m.send(content)
    await interaction.response.send_message('訊息已發送給所有成員', ephemeral=True)

async def dm_role(interaction: discord.Interaction, role: discord.Role, content: str):
    for m in role.members:
        await m.send(content)
    await interaction.response.send_message(f'訊息已發送給 {role} 的所有成員', ephemeral=True)

# --------------------------- 娛樂功能 ---------------------------
async def dice(interaction: discord.Interaction):
    roll = random.randint(1,6)
    await interaction.response.send_message(f'{interaction.user} 擲出了 {roll}')

async def coin(interaction: discord.Interaction):
    flip = random.choice(['正面','反面'])
    await interaction.response.send_message(f'{interaction.user} 擲出了 {flip}')

async def rock_paper_scissors(interaction: discord.Interaction, choice: str):
    bot_choice = random.choice(['石頭','剪刀','布'])
    await interaction.response.send_message(f'{interaction.user} 選擇 {choice}, Bot 選擇 {bot_choice}')

async def guess_number(interaction: discord.Interaction):
    number = random.randint(1,100)
    await interaction.response.send_message(f'請猜一個 1-100 的數字 (示範遊戲 {number})')

# 新增額外娛樂遊戲範例
async def word_scramble(interaction: discord.Interaction, word: str):
    scrambled = ''.join(random.sample(word, len(word)))
    await interaction.response.send_message(f'打亂單字: {scrambled}')

async def math_challenge(interaction: discord.Interaction):
    a = random.randint(1,50)
    b = random.randint(1,50)
    await interaction.response.send_message(f'計算題: {a} + {b} = ? (答案: {a+b})')

# --------------------------- /help 指令 ---------------------------
@bot.tree.command(name='help', description='顯示所有指令與功能')
async def help_command(interaction: discord.Interaction):
    cmds = [f'{cmd.name}: {cmd.description}' for cmd in bot.tree.walk_commands()]
    await interaction.response.send_message('所有指令與功能:\n' + '\n'.join(cmds), ephemeral=True)

# --------------------------- 啟動 Bot ---------------------------
bot.run('YOUR_BOT_TOKEN')
