import discord
from discord import app_commands
import asyncio
import random
import os
import json

# --------------------------- 設定 ---------------------------
TOKEN = os.environ.get('DISCORD_TOKEN')
GUILD_ID = 1227929105018912839
ADMIN_ROLE_ID = 1227938559130861578
LEVEL_FILE = 'levels.json'

# --------------------------- 輔助函數 ---------------------------
def load_levels():
    if not os.path.exists(LEVEL_FILE):
        return {}
    with open(LEVEL_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_levels(levels):
    with open(LEVEL_FILE, 'w', encoding='utf-8') as f:
        json.dump(levels, f, ensure_ascii=False, indent=4)

# --------------------------- Bot 設定 ---------------------------
class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.user_permissions = {}
        self.warnings = {}
        self.levels = load_levels()

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        await self.tree.sync(guild=guild)
        print("✅ Slash commands 已同步到伺服器!")

bot = MyBot()

# --------------------------- Bot 狀態 ---------------------------
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game('HFG 機器人 ・ 照亮你的生活'))
    print(f'Logged in as {bot.user}')

# --------------------------- 等級系統 ---------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    bot.levels.setdefault(user_id, {"xp": 0, "level": 1})

    bot.levels[user_id]["xp"] += 10
    xp = bot.levels[user_id]["xp"]
    level = bot.levels[user_id]["level"]

    if xp >= level * 100:
        bot.levels[user_id]["level"] += 1
        await message.channel.send(f'🎉 恭喜 {message.author.mention} 升到等級 {level+1}!')

    save_levels(bot.levels)
    await bot.process_commands(message)

@bot.tree.command(name='level', description='查看等級', guild=discord.Object(id=GUILD_ID))
async def level(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    user_id = str(member.id)
    data = bot.levels.get(user_id, {"xp": 0, "level": 1})
    await interaction.response.send_message(f'⭐ {member.mention} 等級: {data["level"]}, XP: {data["xp"]}')

# --------------------------- 權限檢查 ---------------------------
def is_admin():
    def predicate(interaction: discord.Interaction) -> bool:
        return any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles)
    return app_commands.check(predicate)

# --------------------------- 測試與基本指令 ---------------------------
@bot.tree.command(name='ping', description='測試指令', guild=discord.Object(id=GUILD_ID))
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('Pong! ✅')

@bot.tree.command(name='help', description='顯示可用指令列表', guild=discord.Object(id=GUILD_ID))
async def help_cmd(interaction: discord.Interaction):
    cmds = [c.name for c in bot.tree.get_commands(guild=discord.Object(id=GUILD_ID))]
    await interaction.response.send_message('📜 可用指令:\n' + '\n'.join([f'/{c}' for c in cmds]), ephemeral=True)

# --------------------------- 管理功能 ---------------------------
@bot.tree.command(name='clear', description='清除訊息', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def clear(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f'🧹 已清除 {amount} 則訊息', ephemeral=True)

@bot.tree.command(name='lock_channel', description='鎖定頻道', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def lock_channel(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message('🔒 頻道已鎖定')

@bot.tree.command(name='unlock_channel', description='解鎖頻道', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def unlock_channel(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = True
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message('🔓 頻道已解鎖')

@bot.tree.command(name='kick', description='踢出成員', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "無理由"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f'👢 {member} 已被踢出，理由: {reason}')

@bot.tree.command(name='ban', description='封鎖成員', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "無理由"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f'⛔ {member} 已被封鎖，理由: {reason}')

@bot.tree.command(name='unban', description='解除封鎖成員', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def unban(interaction: discord.Interaction, user_id: int):
    user = await bot.fetch_user(user_id)
    await interaction.guild.unban(user)
    await interaction.response.send_message(f'✅ {user} 已解除封鎖')

@bot.tree.command(name='mute', description='禁言用戶', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def mute(interaction: discord.Interaction, member: discord.Member, time: int):
    await member.edit(timeout=discord.utils.utcnow() + discord.timedelta(seconds=time))
    await interaction.response.send_message(f'🔇 {member.mention} 已被禁言 {time} 秒')

@bot.tree.command(name='unmute', description='解除禁言', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await member.edit(timeout=None)
    await interaction.response.send_message(f'🔊 {member.mention} 已解除禁言')

@bot.tree.command(name='warn', description='警告用戶', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    bot.warnings.setdefault(member.id, []).append(reason)
    await interaction.response.send_message(f'⚠️ {member.mention} 已被警告，理由: {reason}')

@bot.tree.command(name='warnings', description='查看警告紀錄', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def warnings(interaction: discord.Interaction, member: discord.Member):
    warns = bot.warnings.get(member.id, [])
    if not warns:
        await interaction.response.send_message(f'✅ {member.mention} 沒有任何警告')
    else:
        await interaction.response.send_message(f'⚠️ {member.mention} 的警告紀錄:\n' + '\n'.join(warns))

# --------------------------- 公告功能 ---------------------------
@bot.tree.command(name='announce', description='管理員發布公告', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def announce(interaction: discord.Interaction, message: str):
    for channel in interaction.guild.text_channels:
        try:
            await channel.send(f'📢 公告: {message}')
        except:
            continue
    await interaction.response.send_message('公告已發佈。', ephemeral=True)

# --------------------------- 私訊功能 ---------------------------
@bot.tree.command(name='dm_user', description='私訊特定用戶', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def dm_user(interaction: discord.Interaction, member: discord.Member, message: str):
    try:
        await member.send(f'📩 管理員 {interaction.user} 傳送: {message}')
        await interaction.response.send_message(f'訊息已發送給 {member}.', ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message('無法私訊此用戶。', ephemeral=True)

# --------------------------- 娛樂功能 ---------------------------
@bot.tree.command(name='coinflip', description='擲硬幣', guild=discord.Object(id=GUILD_ID))
async def coinflip(interaction: discord.Interaction):
    await interaction.response.send_message(f'🪙 硬幣結果: {random.choice(["正面","反面"])}')

@bot.tree.command(name='roll_dice', description='擲骰子', guild=discord.Object(id=GUILD_ID))
async def roll_dice(interaction: discord.Interaction, sides: int):
    await interaction.response.send_message(f'🎲 骰子結果: {random.randint(1,sides)}')

@bot.tree.command(name='truth_or_dare', description='真心話大冒險', guild=discord.Object(id=GUILD_ID))
async def truth_or_dare(interaction: discord.Interaction):
    choice = random.choice(['真心話','大冒險'])
    truth_prompts = ['你最怕什麼?', '最近一次說謊是什麼?', '有沒有偷偷喜歡過伺服器裡的人?']
    dare_prompts = ['在公開頻道唱一首歌', '發一張搞笑自拍', '在聊天區說三次"我是豬"']
    prompt = random.choice(truth_prompts if choice=='真心話' else dare_prompts)
    await interaction.response.send_message(f'🎲 {choice}: {prompt}')

@bot.tree.command(name='create_ticket', description='開客服單', guild=discord.Object(id=GUILD_ID))
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
@bot.tree.command(name='hug', description='給予擁抱', guild=discord.Object(id=GUILD_ID))
async def hug(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f'🤗 {interaction.user.mention} 擁抱了 {member.mention}!')

@bot.tree.command(name='poll', description='建立投票', guild=discord.Object(id=GUILD_ID))
async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str):
    embed = discord.Embed(title=f'📊 {question}', description=f'1️⃣ {option1}\n2️⃣ {option2}', color=0x00ff00)
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction('1️⃣')
    await message.add_reaction('2️⃣')
    await interaction.response.send_message('投票已建立!', ephemeral=True)

@bot.tree.command(name='remind', description='提醒功能 (秒)', guild=discord.Object(id=GUILD_ID))
async def remind(interaction: discord.Interaction, time: int, reminder: str):
    await interaction.response.send_message(f'⏰ 好的，我會在 {time} 秒後提醒你: {reminder}', ephemeral=True)
    await asyncio.sleep(time)
    await interaction.followup.send(f'⏰ 提醒: {reminder}')

@bot.tree.command(name='say', description='讓機器人說話', guild=discord.Object(id=GUILD_ID))
async def say(interaction: discord.Interaction, message: str):
    await interaction.channel.send(f'{message}')
    await interaction.response.send_message('✅ 已代發訊息', ephemeral=True)

@bot.tree.command(name='server_info', description='查看伺服器資訊', guild=discord.Object(id=GUILD_ID))
async def server_info(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f'{guild.name} 資訊', color=0x3498db)
    embed.add_field(name='👑 擁有者', value=guild.owner, inline=False)
    embed.add_field(name='👥 成員數', value=guild.member_count, inline=False)
    embed.add_field(name='📅 建立時間', value=guild.created_at.strftime('%Y-%m-%d'), inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='userinfo', description='查看用戶資訊', guild=discord.Object(id=GUILD_ID))
async def userinfo(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(title=f'{member} 的資訊', color=0x95a5a6)
    embed.add_field(name='🆔 ID', value=member.id, inline=False)
    embed.add_field(name='📅 加入伺服器', value=member.joined_at.strftime('%Y-%m-%d'), inline=False)
    embed.add_field(name='📝 建立帳號', value=member.created_at.strftime('%Y-%m-%d'), inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='8ball', description='隨機回答問題', guild=discord.Object(id=GUILD_ID))
async def eight_ball(interaction: discord.Interaction, question: str):
    responses = ["是的", "不是", "可能", "再問一次", "絕對是", "我不確定"]
    await interaction.response.send_message(f'🎱 問題: {question}\n答案: {random.choice(responses)}')

@bot.tree.command(name='joke', description='隨機笑話', guild=discord.Object(id=GUILD_ID))
async def joke(interaction: discord.Interaction):
    jokes = ["我昨天去看牙醫，他說我需要放鬆，所以他給我了一張帳單。", "電腦最怕什麼？當機！", "為什麼數學課很吵？因為大家都在講題。"]
    await interaction.response.send_message(f'😂 {random.choice(jokes)}')

@bot.tree.command(name='quote', description='隨機勵志語錄', guild=discord.Object(id=GUILD_ID))
async def quote(interaction: discord.Interaction):
    quotes = ["成功不是終點，失敗也不是末日，最重要的是勇氣。", "保持微笑，世界會因你而更美好。", "每天進步一點點，就是成功的一大步。"]
    await interaction.response.send_message(f'💡 {random.choice(quotes)}')

# --------------------------- 啟動 Bot ---------------------------
bot.run(TOKEN)
