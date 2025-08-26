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
        guild = discord.Object(id=GUILD_ID)
        await self.tree.sync(guild=guild)
        print("✅ Slash commands synced to the guild!")

bot = MyBot()

# --------------------------- Bot 狀態 ---------------------------
@bot.event
async def on_ready():
    await bot.change_presence(status=discord.Status.idle, activity=discord.Game('HFG 機器人 · 照亮你的生活'))
    print(f'Logged in as {bot.user}')

# --------------------------- 權限檢查 ---------------------------
def is_admin():
    def predicate(interaction: discord.Interaction) -> bool:
        return any(role.id == ADMIN_ROLE_ID for role in interaction.user.roles)
    return app_commands.check(predicate)

# --------------------------- 基礎指令 ---------------------------
@bot.tree.command(name='ping', description='測試指令')
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('Pong!')

@bot.tree.command(name='help', description='顯示可用指令列表')
async def help_cmd(interaction: discord.Interaction):
    cmds = [c.name for c in bot.tree.get_commands()]
    await interaction.response.send_message('📜 可用指令:\n' + '\n'.join([f'/{c}' for c in cmds]), ephemeral=True)

# --------------------------- 管理/公告/私訊指令 ---------------------------
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

@bot.tree.command(name='warn_user', description='對用戶發出警告')
@is_admin()
async def warn_user(interaction: discord.Interaction, member: discord.Member, reason: str):
    bot.warnings.setdefault(member.id, 0)
    bot.warnings[member.id] += 1
    await interaction.response.send_message(f'{member} 已被警告 ({bot.warnings[member.id]} 次) 原因: {reason}')
    try:
        await member.send(f'⚠ 你已被警告 ({bot.warnings[member.id]} 次) 原因: {reason}')
    except:
        pass

@bot.tree.command(name='unwarn_user', description='解除用戶警告')
@is_admin()
async def unwarn_user(interaction: discord.Interaction, member: discord.Member):
    bot.warnings[member.id] = 0
    await interaction.response.send_message(f'{member} 的警告已解除。')

@bot.tree.command(name='kick_user', description='踢出用戶')
@is_admin()
async def kick_user(interaction: discord.Interaction, member: discord.Member, reason: str):
    await member.kick(reason=reason)
    await interaction.response.send_message(f'{member} 已被踢出，原因: {reason}')

@bot.tree.command(name='ban_user', description='封鎖用戶')
@is_admin()
async def ban_user(interaction: discord.Interaction, member: discord.Member, reason: str):
    await member.ban(reason=reason)
    await interaction.response.send_message(f'{member} 已被封鎖，原因: {reason}')

@bot.tree.command(name='unban_user', description='解除封鎖用戶')
@is_admin()
async def unban_user(interaction: discord.Interaction, member_name: str):
    banned_users = await interaction.guild.bans()
    for ban_entry in banned_users:
        if ban_entry.user.name == member_name:
            await interaction.guild.unban(ban_entry.user)
            await interaction.response.send_message(f'{member_name} 已解除封鎖')
            return
    await interaction.response.send_message(f'找不到 {member_name} 的封鎖紀錄')

# --------------------------- 娛樂/互動功能 ---------------------------
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

# --------------------------- 擴展娛樂/互動功能 ---------------------------
@bot.tree.command(name='random_joke', description='隨機笑話')
async def random_joke(interaction: discord.Interaction):
    jokes = ['笑話1','笑話2','笑話3','笑話4','笑話5']
    await interaction.response.send_message(random.choice(jokes))

@bot.tree.command(name='daily_fortune', description='今日運勢')
async def daily_fortune(interaction: discord.Interaction):
    fortunes = ['大吉','中吉','小吉','凶']
    await interaction.response.send_message(f'🎴 今日運勢: {random.choice(fortunes)}')

@bot.tree.command(name='inspire', description='隨機名言')
async def inspire(interaction: discord.Interaction):
    quotes = ['名言1','名言2','名言3','名言4','名言5']
    await interaction.response.send_message(f'💡 {random.choice(quotes)}')

@bot.tree.command(name='number_guess', description='猜數字遊戲')
async def number_guess(interaction: discord.Interaction, guess: int):
    answer = random.randint(1,20)
    result = '正確!' if guess == answer else f'錯誤，答案是 {answer}'
    await interaction.response.send_message(result)

@bot.tree.command(name='magic_8ball', description='8球占卜')
async def magic_8ball(interaction: discord.Interaction, question: str):
    responses = ['會','不會','不確定','問問再說','肯定會']
    await interaction.response.send_message(f'🎱 問題: {question}\n答案: {random.choice(responses)}')

@bot.tree.command(name='flip_card', description='翻牌遊戲')
async def flip_card(interaction: discord.Interaction):
    suits = ['♠','♥','♦','♣']
    ranks = ['A','2','3','4','5','6','7','8','9','10','J','Q','K']
    await interaction.response.send_message(f'🃏 你翻到: {random.choice(ranks)}{random.choice(suits)}')

@bot.tree.command(name='roll_multiple_dice', description='擲多顆骰子')
async def roll_multiple_dice(interaction: discord.Interaction, dice: int, sides: int):
    results = [str(random.randint(1,sides)) for _ in range(dice)]
    await interaction.response.send_message(f'🎲 擲骰結果: {", ".join(results)}')

@bot.tree.command(name='rock_paper_scissors', description='剪刀石頭布')
async def rock_paper_scissors(interaction: discord.Interaction, choice: str):
    choices = ['剪刀','石頭','布']
    bot_choice = random.choice(choices)
    result = '平手' if choice == bot_choice else ('你贏了' if (choice=='剪刀' and bot_choice=='布') or (choice=='石頭' and bot_choice=='剪刀') or (choice=='布' and bot_choice=='石頭') else '你輸了')
    await interaction.response.send_message(f'你選 {choice}, 我選 {bot_choice} → {result}')

@bot.tree.command(name='roll_d20', description='擲20面骰')
async def roll_d20(interaction: discord.Interaction):
    await interaction.response.send_message(f'🎲 你擲到: {random.randint(1,20)}')

@bot.tree.command(name='fortune_cookie', description='幸運籤')
async def fortune_cookie(interaction: discord.Interaction):
    fortunes = ['今天會遇到好事','小心錢財','愛情運佳','工作順利','要注意健康']
    await interaction.response.send_message(f'🥠 幸運籤: {random.choice(fortunes)}')

@bot.tree.command(name='random_fact', description='隨機知識')
async def random_fact(interaction: discord.Interaction):
    facts = ['章魚有三個心臟','貓可以聽到超過64kHz','香蕉是漿果','蜂蜜不會壞','水母可以長生不老']
    await interaction.response.send_message(f'📚 知識: {random.choice(facts)}')

@bot.tree.command(name='choose', description='幫你做決定')
async def choose(interaction: discord.Interaction, options: str):
    option_list = options.split(',')
    await interaction.response.send_message(f'🎯 我選: {random.choice(option_list)}')

@bot.tree.command(name='echo', description='重複你的訊息')
async def echo(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(f'💬 {message}')

# --------------------------- 啟動 Bot ---------------------------
bot.run(TOKEN)
