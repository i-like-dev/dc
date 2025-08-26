import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio

# --------------------------- Bot 設定 ---------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents, help_command=None)

# --------------------------- Bot 狀態設定 ---------------------------
@bot.event
async def on_ready():
    await bot.tree.sync()  # 同步 Slash Commands
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game('暑假作業'))
    print(f'Logged in as {bot.user}')

# --------------------------- 用戶警告系統 ---------------------------
warnings = {}
warning_limit = 5
mute_duration = 600  # 10 分鐘

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

# --------------------------- 管理功能 ---------------------------
@bot.tree.command(name="kick", description="踢出成員")
@app_commands.describe(member="要踢出的成員")
async def kick(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.guild_permissions.kick_members:
        await member.kick(reason=f'Kicked by {interaction.user}')
        await interaction.response.send_message(f'{member} 已被踢出')

@bot.tree.command(name="ban", description="封鎖成員")
@app_commands.describe(member="要封鎖的成員")
async def ban(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.guild_permissions.ban_members:
        await member.ban(reason=f'Banned by {interaction.user}')
        await interaction.response.send_message(f'{member} 已被封鎖')

@bot.tree.command(name="purge", description="刪除訊息")
@app_commands.describe(limit="要刪除的訊息數量")
async def purge(interaction: discord.Interaction, limit: int):
    if interaction.user.guild_permissions.manage_messages:
        deleted = await interaction.channel.purge(limit=limit)
        await interaction.response.send_message(f'已刪除 {len(deleted)} 則訊息', ephemeral=True)

# --------------------------- 公告系統 ---------------------------
announcements = {}

@bot.tree.command(name="announce", description="發布公告")
@app_commands.describe(title="公告標題", content="公告內容")
async def announce(interaction: discord.Interaction, title: str, content: str):
    if interaction.user.guild_permissions.administrator:
        announcements[title] = content
        await interaction.response.send_message(f'公告 {title} 已發布')

@bot.tree.command(name="edit_announcement", description="編輯公告")
@app_commands.describe(title="公告標題", content="新的公告內容")
async def edit_announcement(interaction: discord.Interaction, title: str, content: str):
    if title in announcements:
        announcements[title] = content
        await interaction.response.send_message(f'公告 {title} 已更新')

@bot.tree.command(name="delete_announcement", description="刪除公告")
@app_commands.describe(title="公告標題")
async def delete_announcement(interaction: discord.Interaction, title: str):
    if title in announcements:
        del announcements[title]
        await interaction.response.send_message(f'公告 {title} 已刪除')

@bot.tree.command(name="list_announcements", description="列出公告")
async def list_announcements(interaction: discord.Interaction):
    if announcements:
        msg = '\n'.join([f'{t}: {c}' for t,c in announcements.items()])
        await interaction.response.send_message(msg)
    else:
        await interaction.response.send_message('目前沒有公告')

# --------------------------- 私訊系統 ---------------------------
@bot.tree.command(name="dm_user", description="私訊成員")
@app_commands.describe(member="要私訊的成員", content="訊息內容")
async def dm_user(interaction: discord.Interaction, member: discord.Member, content: str):
    await member.send(content)
    await interaction.response.send_message(f'訊息已發送給 {member}', ephemeral=True)

# --------------------------- 娛樂功能 ---------------------------
@bot.tree.command(name="dice", description="擲骰子")
async def dice(interaction: discord.Interaction):
    roll = random.randint(1,6)
    await interaction.response.send_message(f'{interaction.user} 擲出了 {roll}')

@bot.tree.command(name="coin", description="擲硬幣")
async def coin(interaction: discord.Interaction):
    flip = random.choice(['正面','反面'])
    await interaction.response.send_message(f'{interaction.user} 擲出了 {flip}')

@bot.tree.command(name="rps", description="剪刀石頭布")
@app_commands.describe(choice="你的選擇")
async def rps(interaction: discord.Interaction, choice: str):
    bot_choice = random.choice(['石頭','剪刀','布'])
    await interaction.response.send_message(f'{interaction.user} 選擇 {choice}, Bot 選擇 {bot_choice}')

@bot.tree.command(name="guess_number", description="猜數字遊戲")
async def guess_number(interaction: discord.Interaction):
    number = random.randint(1,100)
    await interaction.response.send_message(f'請猜一個 1-100 的數字 (示範答案: {number})')

# --------------------------- /help 指令 ---------------------------
@bot.tree.command(name='help', description='顯示所有指令與功能')
async def help_command(interaction: discord.Interaction):
    cmds = [f'{cmd.name}: {cmd.description}' for cmd in bot.tree.walk_commands()]
    await interaction.response.send_message('所有指令與功能:\n' + '\n'.join(cmds), ephemeral=True)

# --------------------------- 啟動 Bot ---------------------------
bot.run('YOUR_BOT_TOKEN')
