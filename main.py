import os, threading, requests
from flask import Flask, render_template, request, redirect
from supabase import create_client
from discord.ext import commands
from discord import app_commands, Embed, ButtonStyle
from discord.ui import Button, View
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
ROLE_ID = int(os.getenv("ROLE_ID"))
GUILD_ID = int(os.getenv("GUILD_ID"))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
RECAPTCHA_SECRET = os.getenv("RECAPTCHA_SECRET")
SUPPORT_INVITE = os.getenv("SUPPORT_INVITE")

BLACKLIST_IPS = ["63.", "185.", "188."]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

intents = commands.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
app = Flask(__name__)

# ---------------- Flask Routes ---------------- #

@app.route("/")
def index():
    return redirect("https://discord.com")

@app.route("/recaptcha")
def recaptcha_page():
    uid = request.args.get("uid")
    return render_template("recaptcha.html", uid=uid, site_key="YOUR_SITE_KEY_HERE")

@app.route("/verify", methods=["POST"])
def verify():
    token = request.form.get("g-recaptcha-response")
    ip = request.remote_addr
    uid = request.args.get("uid")

    if any(ip.startswith(prefix) for prefix in BLACKLIST_IPS):
        return render_template("blocked.html", reason="VPN/Proxy使用検出", ip=ip, invite=SUPPORT_INVITE)

    recaptcha_res = requests.post("https://www.google.com/recaptcha/api/siteverify", data={
        "secret": RECAPTCHA_SECRET,
        "response": token
    }).json()

    if not recaptcha_res.get("success"):
        return render_template("failed.html", invite=SUPPORT_INVITE)

    # reCAPTCHA 成功 → Discordボタン有効化
    bot.loop.create_task(enable_user_button(uid, ip))
    return render_template("success.html", invite=SUPPORT_INVITE)

async def enable_user_button(user_id, ip):
    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(int(user_id))
    role = guild.get_role(ROLE_ID)
    if member and role:
        try:
            supabase.table("users").insert({
                "id": user_id,
                "ip": ip,
                "username": member.name,
                "display_name": member.display_name,
                "email": getattr(member, "email", None),
                "icon": str(member.display_avatar.url)
            }).execute()
            # ロール付与
            await member.add_roles(role)
        except:
            pass

# ---------------- Discord Bot Commands ---------------- #

@bot.tree.command(name="button", description="認証ボタンを送信")
@app_commands.describe(title="タイトル", description="説明", image_url="画像URL")
async def button(interaction, title:str, description:str, image_url:str=None):
    embed = Embed(title=title, description=description, color=discord.Color.dark_grey())
    if image_url: embed.set_image(url=image_url)
    view = View()
    oauth_button = Button(label="認証する", style=ButtonStyle.grey, url=f"{REDIRECT_URI}?uid={interaction.user.id}", disabled=True)
    view.add_item(oauth_button)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="user", description="ユーザー情報を表示")
@app_commands.describe(user="表示したいユーザー")
async def user(interaction, user:discord.User):
    res = supabase.table("users").select("*").eq("id", str(user.id)).execute()
    if not res.data:
        await interaction.response.send_message("ユーザー情報が見つかりません。")
        return
    data = res.data[0]
    embed = Embed(title="ユーザー情報", color=discord.Color.teal())
    embed.add_field(name="Username", value=data["username"], inline=False)
    embed.add_field(name="Display Name", value=data["display_name"], inline=False)
    embed.add_field(name="Email", value=data["email"], inline=False)
    embed.add_field(name="IP", value=data["ip"], inline=False)
    embed.set_thumbnail(url=data["icon"])
    await interaction.response.send_message(embed=embed)

# ---------------- Keep Alive / 24時間稼働 ---------------- #

def keep_alive():
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT",8080)))).start()

# ---------------- Bot起動 ---------------- #

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

keep_alive()
bot.run(TOKEN)
