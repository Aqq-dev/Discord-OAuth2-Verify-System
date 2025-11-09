import os
import discord
from discord import app_commands, Embed, ButtonStyle
from discord.ui import Button, View
from discord.ext import commands
from flask import Flask, request, render_template, redirect
from supabase import create_client, Client
from dotenv import load_dotenv
import requests
import threading

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

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

app = Flask(__name__)

@app.route("/")
def index():
    return redirect("https://discord.com")

@app.route("/oauth")
def oauth():
    ip = request.remote_addr
    if any(ip.startswith(prefix) for prefix in BLACKLIST_IPS):
        return render_template("blocked.html", reason="VPN/Proxyの使用が検出されました。", ip=ip, invite=SUPPORT_INVITE)

    code = request.args.get("code")
    if not code:
        return redirect(f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20email%20guilds.join")

    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    token_res = requests.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
    token_json = token_res.json()
    access_token = token_json.get("access_token")

    user_info = requests.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {access_token}"}).json()

    return render_template("success.html", username=user_info["username"], avatar=f"https://cdn.discordapp.com/avatars/{user_info['id']}/{user_info['avatar']}.png", email=user_info["email"])

@app.route("/verify", methods=["POST"])
def verify():
    token = request.form.get("g-recaptcha-response")
    ip = request.remote_addr
    recaptcha_url = "https://www.google.com/recaptcha/api/siteverify"
    payload = {"secret": RECAPTCHA_SECRET, "response": token}
    res = requests.post(recaptcha_url, data=payload)
    result = res.json()
    if not result.get("success"):
        return render_template("failed.html", invite=SUPPORT_INVITE)

    user_id = request.args.get("uid")
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
                "email": member.email if hasattr(member, "email") else None,
                "icon": str(member.display_avatar.url)
            }).execute()
            bot.loop.create_task(member.add_roles(role))
        except:
            pass
    return render_template("success.html", username=member.name, avatar=member.display_avatar.url, email="認証成功")

@bot.tree.command(name="button", description="認証ボタンを送信します。")
@app_commands.describe(title="タイトル", description="説明", image_url="画像URL（任意）")
async def button(interaction: discord.Interaction, title: str, description: str, image_url: str = None):
    embed = Embed(title=title, description=description, color=discord.Color.dark_grey())
    if image_url:
        embed.set_image(url=image_url)
    view = View()
    button = Button(label="認証する", style=ButtonStyle.grey, url=f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20email%20guilds.join")
    view.add_item(button)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="user", description="ユーザー情報を表示します。")
@app_commands.describe(user="表示したいユーザー")
async def user(interaction: discord.Interaction, user: discord.User):
    res = supabase.table("users").select("*").eq("id", str(user.id)).execute()
    if not res.data:
        await interaction.response.send_message("ユーザー情報が見つかりません。")
        return
    data = res.data[0]
    embed = Embed(title="User DATA", color=discord.Color.teal())
    embed.add_field(name="Username", value=data["username"], inline=False)
    embed.add_field(name="Display Name", value=data["display_name"], inline=False)
    embed.add_field(name="Email", value=data["email"], inline=False)
    embed.add_field(name="IP", value=data["ip"], inline=False)
    embed.set_thumbnail(url=data["icon"])
    await interaction.response.send_message(embed=embed)

def keep_alive():
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))).start()

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

keep_alive()
bot.run(TOKEN)
