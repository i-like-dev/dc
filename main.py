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

# --------------------------- 管理/公告/私訊/互動指令 ---------------------------
@bot.tree.command(name='ping', description='測試指令')
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('Pong!')

@bot.tree.command(name='help', description='顯示可用指令列表')
async def help_cmd(interaction: discord.Interaction):
    cmds = [c.name for c in bot.tree.get_commands()]
    await interaction.response.send_message('📜 可用指令:\n' + '\n'.join([f'/{c}' for c in cmds]), ephemeral=True)

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

# --------------------------- 手動添加的25個獨立功能 ---------------------------
@bot.tree.command(name='ascii_art', description='產生 ASCII 藝術')
async def ascii_art(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(f'**{text.upper()}** in ASCII!')

@bot.tree.command(name='random_color', description='生成隨機顏色')
async def random_color(interaction: discord.Interaction):
    color = '#'+''.join(random.choices('0123456789ABCDEF', k=6))
    await interaction.response.send_message(f'🎨 隨機顏色: {color}')

@bot.tree.command(name='rps', description='石頭剪刀布')
async def rps(interaction: discord.Interaction, choice: str):
    bot_choice = random.choice(['石頭','剪刀','布'])
    await interaction.response.send_message(f'你出: {choice}, 我出: {bot_choice}')

@bot.tree.command(name='flip_coin_trick', description='魔術硬幣')
async def flip_coin_trick(interaction: discord.Interaction):
    result = random.choice(['正面','反面','立起'])
    await interaction.response.send_message(f'🪙 魔術硬幣結果: {result}')

@bot.tree.command(name='guess_number', description='猜數字遊戲')
async def guess_number(interaction: discord.Interaction, guess: int):
    target = random.randint(1,100)
    await interaction.response.send_message(f'目標數字: {target}, 你猜: {guess}')

@bot.tree.command(name='roll_2d6', description='擲兩顆六面骰')
async def roll_2d6(interaction: discord.Interaction):
    d1 = random.randint(1,6)
    d2 = random.randint(1,6)
    await interaction.response.send_message(f'🎲 結果: {d1} + {d2} = {d1+d2}')

@bot.tree.command(name='joke', description='隨機笑話')
async def joke(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(['笑話1','笑話2','笑話3']))

@bot.tree.command(name='inspire', description='隨機勵志語錄')
async def inspire(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(['加油!','相信自己!','你可以的!']))

@bot.tree.command(name='compliment', description='給用戶一個讚美')
async def compliment(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f'{member.mention} 你真棒!')

@bot.tree.command(name='roast', description='開玩笑吐槽用戶')
async def roast(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f'{member.mention} 你今天好像有點累😂')

@bot.tree.command(name='coin_game', description='硬幣猜正反')
async def coin_game(interaction: discord.Interaction, guess: str):
    result = random.choice(['正面','反面'])
    await interaction.response.send_message(f'結果: {result}. 你猜的是 {guess}.')

@bot.tree.command(name='dice_game', description='猜骰子點數')
async def dice_game(interaction: discord.Interaction, guess: int):
    roll = random.randint(1,6)
    await interaction.response.send_message(f'骰子結果: {roll}, 你猜: {guess}')

@bot.tree.command(name='magic8', description='魔法8球')
async def magic8(interaction: discord.Interaction, question: str):
    await interaction.response.send_message(random.choice(['是','不是','再問一次']))

@bot.tree.command(name='weather', description='隨機天氣')
async def weather(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(['晴天','雨天','陰天','下雪']))

@bot.tree.command(name='fortune', description='隨機運勢')
async def fortune(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(['大吉','中吉','小吉','凶']))

@bot.tree.command(name='roll_d20', description='擲二十面骰')
async def roll_d20(interaction: discord.Interaction):
    await interaction.response.send_message(f'🎲 結果: {random.randint(1,20)}')

@bot.tree.command(name='coin_guess', description='猜硬幣正反')
async def coin_guess(interaction: discord.Interaction, guess: str):
    result = random.choice(['正面','反面'])
    await interaction.response.send_message(f'結果: {result}. 你猜的是 {guess}.')

@bot.tree.command(name='motivate', description='隨機勵志短語')
async def motivate(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(['今天也要加油!','別放棄!','努力會有回報!']))

@bot.tree.command(name='fact', description='隨機小知識')
async def fact(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(['知識1','知識2','知識3']))

@bot.tree.command(name='flip_card', description='翻牌遊戲')
async def flip_card(interaction: discord.Interaction):
    await interaction.response.send_message(f'翻出的牌是 {random.randint(1,52)}')

@bot.tree.command(name='yes_no', description='隨機是或否')
async def yes_no(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(['是','否']))

@bot.tree.command(name='guess_letter', description='猜字母遊戲')
async def guess_letter(interaction: discord.Interaction, letter: str):
    correct = random.choice('abcdefghijklmnopqrstuvwxyz')
    await interaction.response.send_message(f'正確字母: {correct}, 你猜: {letter}')

@bot.tree.command(name='flip_card_game', description='翻牌猜數字')
async def flip_card_game(interaction: discord.Interaction):
    number = random.randint(1,10)
    await interaction.response.send_message(f'翻出的數字: {number}')

@bot.tree.command(name='lucky_number', description='隨機幸運數字')
async def lucky_number(interaction: discord.Interaction):
    await interaction.response.send_message(f'你的幸運數字是: {random.randint(1,100)}')

@bot.tree.command(name='random_animal', description='隨機動物')
async def random_animal(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(['🐶','🐱','🐹','🐸','🦊']))

# --------------------------- 啟動 Bot ---------------------------
bot.run(TOKEN)
