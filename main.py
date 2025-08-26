import discord
from discord import app_commands
import asyncio
import random
import os
from datetime import datetime, timedelta
import json

# --------------------------- 設定 ---------------------------
TOKEN = os.environ.get('DISCORD_TOKEN')
GUILD_ID = 1227929105018912839
ADMIN_ROLE_ID = 1227938559130861578
ANNOUNCE_CHANNEL_ID = 1228485979090718720
LEVEL_FILE = 'levels.json'
WARN_FILE = 'warnings.json'

# --------------------------- Bot ---------------------------
class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.levels = {}
        self.warnings = {}
        try:
            with open(LEVEL_FILE,'r',encoding='utf-8') as f:
                self.levels = json.load(f)
        except:
            self.levels = {}
        try:
            with open(WARN_FILE,'r',encoding='utf-8') as f:
                self.warnings = json.load(f)
        except:
            self.warnings = {}

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        await self.tree.sync(guild=guild)
        print("✅ Slash commands synced to the guild!")

    def save_json(self, filename, data):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

bot = MyBot()

# --------------------------- Bot 狀態 ---------------------------
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.online, activity=discord.Game('HFG 機器人 ・ 照亮你的生活'))
    print(f'Logged in as {bot.user}')

# --------------------------- 權限檢查 ---------------------------
def is_admin():
    def predicate(interaction: discord.Interaction) -> bool:
        return any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles)
    return app_commands.check(predicate)

# --------------------------- 等級系統 ---------------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    uid = str(message.author.id)
    bot.levels.setdefault(uid, {"xp":0, "level":1})
    bot.levels[uid]["xp"] += 10
    xp = bot.levels[uid]["xp"]
    level = bot.levels[uid]["level"]
    if xp >= level*100:
        bot.levels[uid]["level"] += 1
        await message.channel.send(f'🎉 {message.author.mention} 升到等級 {level+1}!')
    bot.save_json(LEVEL_FILE, bot.levels)
    await bot.process_commands(message)

@bot.tree.command(name='level', description='查看等級', guild=discord.Object(id=GUILD_ID))
async def level(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    uid = str(member.id)
    data = bot.levels.get(uid, {"xp":0,"level":1})
    await interaction.response.send_message(f'⭐ {member.mention} 等級: {data["level"]}, XP: {data["xp"]}')

# --------------------------- 警告系統 ---------------------------
async def warn_user(member: discord.Member, reason: str, moderator: discord.Member):
    uid = str(member.id)
    bot.warnings[uid] = bot.warnings.get(uid, 0) + 1
    bot.save_json(WARN_FILE, bot.warnings)
    await member.send(f'⚠️ 你被警告 ({bot.warnings[uid]} 次)，原因: {reason}')
    if bot.warnings[uid] >= 5:
        try:
            await member.edit(timed_out_until=datetime.utcnow()+timedelta(minutes=10))
            await member.send('⏱ 你已被禁言 10 分鐘')
            bot.warnings[uid] = 0
            bot.save_json(WARN_FILE, bot.warnings)
        except discord.Forbidden:
            pass

@bot.tree.command(name='warn', description='警告用戶', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    await warn_user(member, reason, interaction.user)
    await interaction.response.send_message(f'✅ 已警告 {member.display_name} ({bot.warnings[str(member.id)]} 次)', ephemeral=True)

# --------------------------- 權限管理 ---------------------------
@bot.tree.command(name='grant_admin', description='給予管理權限', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def grant_admin(interaction: discord.Interaction, member: discord.Member):
    role = discord.utils.get(interaction.guild.roles, id=ADMIN_ROLE_ID)
    await member.add_roles(role)
    await interaction.response.send_message(f'✅ {member.display_name} 已獲得管理權限', ephemeral=True)

@bot.tree.command(name='revoke_admin', description='撤銷管理權限', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def revoke_admin(interaction: discord.Interaction, member: discord.Member):
    role = discord.utils.get(interaction.guild.roles, id=ADMIN_ROLE_ID)
    await member.remove_roles(role)
    await interaction.response.send_message(f'✅ {member.display_name} 已撤銷管理權限', ephemeral=True)

# --------------------------- 公告功能 ---------------------------
@bot.tree.command(name='announce', description='管理員發布公告', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def announce(interaction: discord.Interaction, title: str, content: str):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    embed = discord.Embed(title=title, description=content, color=discord.Color.blue(), timestamp=datetime.utcnow())
    embed.set_footer(text=f'發布人: {interaction.user.display_name}')
    await channel.send(embed=embed)
    await interaction.response.send_message('✅ 公告已發佈。', ephemeral=True)

# --------------------------- 私訊功能 ---------------------------
@bot.tree.command(name='dm_user', description='私訊特定用戶', guild=discord.Object(id=GUILD_ID))
@is_admin()
async def dm_user(interaction: discord.Interaction, member: discord.Member, message: str):
    try:
        await member.send(f'📩 管理員訊息 ({interaction.user.display_name}): {message}')
        await interaction.response.send_message(f'訊息已發送給 {member.display_name}.', ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message('無法私訊此用戶。', ephemeral=True)

# --------------------------- 客服單 ---------------------------
@bot.tree.command(name='create_ticket', description='開客服單', guild=discord.Object(id=GUILD_ID))
async def create_ticket(interaction: discord.Interaction, reason: str):
    category = discord.utils.get(interaction.guild.categories, name='客服單')
    if not category:
        category = await interaction.guild.create_category('客服單')
    overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                  interaction.user: discord.PermissionOverwrite(view_channel=True)}
    ticket = await interaction.guild.create_text_channel(f'ticket-{interaction.user.name}', category=category, overwrites=overwrites)

    view = discord.ui.View()
    async def close_callback(interaction_close):
        await ticket.delete()
    button = discord.ui.Button(label='關閉客服單', style=discord.ButtonStyle.red)
    button.callback = close_callback
    view.add_item(button)
    await ticket.send(f'{interaction.user.mention} 已開啟客服單，原因: {reason}', view=view)
    await interaction.response.send_message(f'✅ 已建立客服單: {ticket.mention}', ephemeral=True)

# --------------------------- 娛樂/互動功能 ---------------------------
fun_prompts = {
    'truth': ['你最怕什麼?', '最近一次說謊是什麼?', '有沒有偷偷喜歡過伺服器裡的人?'],
    'dare': ['在公開頻道唱一首歌', '發一張搞笑自拍', '在聊天區說三次"我是豬"']
}

@bot.tree.command(name='coinflip', description='擲硬幣', guild=discord.Object(id=GUILD_ID))
async def coinflip(interaction: discord.Interaction):
    await interaction.response.send_message(f'🪙 硬幣結果: {random.choice(["正面","反面"])}')

@bot.tree.command(name='roll_dice', description='擲骰子', guild=discord.Object(id=GUILD_ID))
async def roll_dice(interaction: discord.Interaction, sides: int):
    await interaction.response.send_message(f'🎲 骰子結果: {random.randint(1,sides)}')

@bot.tree.command(name='truth_or_dare', description='真心話大冒險', guild=discord.Object(id=GUILD_ID))
async def truth_or_dare(interaction: discord.Interaction):
    choice = random.choice(['真心話','大冒險'])
    prompt = random.choice(fun_prompts['truth'] if choice=='真心話' else fun_prompts['dare'])
    await interaction.response.send_message(f'🎲 {choice}: {prompt}')

@bot.tree.command(name='hug', description='給予擁抱', guild=discord.Object(id=GUILD_ID))
async def hug(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f'🤗 {interaction.user.mention} 擁抱了 {member.mention}!')

# --------------------------- 新增互動功能 ---------------------------
eight_ball_responses = ["是的", "不是", "可能吧", "不太可能", "當然！", "我不確定", "再問一次"]

@bot.tree.command(name='8ball', description='問 8ball 一個問題', guild=discord.Object(id=GUILD_ID))
async def eight_ball(interaction: discord.Interaction, question: str):
    answer = random.choice(eight_ball_responses)
    await interaction.response.send_message(f'🎱 問題: {question}\n答案: {answer}')

@bot.tree.command(name='poll', description='建立投票', guild=discord.Object(id=GUILD_ID))
async def poll(interaction: discord.Interaction, title: str, *options: str):
    if len(options) < 2:
        await interaction.response.send_message('❌ 至少提供兩個選項', ephemeral=True)
        return
    embed = discord.Embed(title=f'📊 {title}', description='\n'.join(f'{i+1}. {opt}' for i,opt in enumerate(options)), color=discord.Color.green())
    msg = await interaction.channel.send(embed=embed)
    emojis = ['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟']
    for i in range(len(options)):
        await msg.add_reaction(emojis[i])
    await interaction.response.send_message('✅ 投票已建立', ephemeral=True)

jokes = [
    "我告訴我的電腦一個笑話，它笑了…至少它的屏幕亮了起來。",
    "為什麼程式員不喜歡大自然？因為有太多 bug。",
    "為什麼 Java 程式員總是戴眼鏡？因為他們不 C#。"
]

@bot.tree.command(name='joke', description='隨機笑話', guild=discord.Object(id=GUILD_ID))
async def joke(interaction: discord.Interaction):
    await interaction.response.send_message(f'😂 {random.choice(jokes)}')

compliments = [
    "你今天看起來很棒！",
    "你的程式碼總是很乾淨！",
    "你讓伺服器更有趣了！",
    "你真是一個棒的朋友！"
]

@bot.tree.command(name='compliment', description='隨機讚美', guild=discord.Object(id=GUILD_ID))
async def compliment(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    await interaction.response.send_message(f'💖 {member.mention} {random.choice(compliments)}')

@bot.tree.command(name='remind', description='設定提醒', guild=discord.Object(id=GUILD_ID))
async def remind(interaction: discord.Interaction, minutes: int, *, message: str):
    await interaction.response.send_message(f'⏱ {interaction.user.mention} 我會在 {minutes} 分鐘後提醒你: {message}')
    await asyncio.sleep(minutes*60)
    try:
        await interaction.user.send(f'⏰ 提醒: {message}')
    except discord.Forbidden:
        await interaction.channel.send(f'{interaction.user.mention} 提醒: {message}')

# --------------------------- 啟動 ---------------------------
bot.run(TOKEN)
