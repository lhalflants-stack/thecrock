import os
import json
import random
import sqlite3
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import discord
from dotenv import load_dotenv


# =========================
# CONFIGURATION
# =========================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

with open("config.json", "r", encoding="utf-8") as file:
    config = json.load(file)


# =========================
# BASE DE DONNÉES
# =========================

database = sqlite3.connect("database.db")
cursor = database.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        guild_id INTEGER NOT NULL,
        xp INTEGER NOT NULL DEFAULT 0
    )
""")

database.commit()


# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class LevelBot(discord.Client):

    def __init__(self):
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)


bot = LevelBot()


# =========================
# COOLDOWN XP
# =========================

last_xp_gain = {}


# =========================
# CALCUL DU NIVEAU
# =========================

def get_level(xp):

    current_level = 0

    for level, data in config["levels"].items():

        required_xp = data["xp_required"]

        if xp >= required_xp:
            current_level = int(level)

    return current_level


# =========================
# ATTRIBUTION DU RÔLE
# =========================

async def update_role(member, level):

    # Cherche le rôle correspondant au niveau atteint
    selected_role_id = None

    for level_number, data in config["levels"].items():

        if int(level_number) <= level:

            role_id = int(data["role_id"])

            # 0 signifie : aucun rôle pour ce niveau
            if role_id != 0:
                selected_role_id = role_id

    # Aucun rôle prévu pour ce niveau
    if selected_role_id is None:
        return

    # Cherche le rôle sur le serveur
    role = member.guild.get_role(selected_role_id)

    print(
        f"DEBUG ROLE → ID recherché : "
        f"{selected_role_id}"
    )

    print(
        f"DEBUG ROLE → rôle trouvé : "
        f"{role}"
    )

    if role is None:

        print(
            "ERREUR : le rôle est introuvable."
        )

        return

    # Liste uniquement des vrais rôles de niveau
    level_role_ids = []

    for data in config["levels"].values():

        role_id = int(data["role_id"])

        if role_id != 0:
            level_role_ids.append(role_id)

    # Retire les anciens rôles de niveau
    for old_role in member.roles:

        if (
            old_role.id in level_role_ids
            and old_role.id != role.id
        ):

            await member.remove_roles(old_role)

            print(
                f"{member} perd le rôle "
                f"{old_role.name}"
            )

    # Donne le nouveau rôle
    if role not in member.roles:

        await member.add_roles(role)

        print(
            f"{member} obtient le rôle "
            f"{role.name} "
            f"(niveau {level})"
        )


# =========================
# COMMANDE /NIVEAU
# =========================

@bot.tree.command(
    name="niveau",
    description="Affiche ton niveau et ton XP"
)
async def niveau_command(
    interaction: discord.Interaction
):

    # Vérifie que la commande est utilisée sur un serveur
    if interaction.guild is None:

        await interaction.response.send_message(
            "Cette commande doit être utilisée sur un serveur.",
            ephemeral=True
        )

        return

    user_id = interaction.user.id
    guild_id = interaction.guild.id

    # =========================
    # RÉCUPÉRATION DE L'XP
    # =========================

    cursor.execute(
        """
        SELECT xp
        FROM users
        WHERE user_id = ? AND guild_id = ?
        """,
        (user_id, guild_id)
    )

    result = cursor.fetchone()

    if result is None:

        xp = 0

    else:

        xp = result[0]

    # =========================
    # NIVEAU ACTUEL
    # =========================

    level = get_level(xp)

    # =========================
    # TITRE ACTUEL
    # =========================

    current_role_name = "Aucun titre"

    for level_number, data in sorted(
        config["levels"].items(),
        key=lambda item: int(item[0])
    ):

        if int(level_number) <= level:

            role = interaction.guild.get_role(
                int(data["role_id"])
            )

            if role is not None:

                current_role_name = role.name

    # =========================
    # PROCHAIN NIVEAU
    # =========================

    next_level = None
    next_xp = None
    next_role_name = None

    for level_number, data in sorted(
        config["levels"].items(),
        key=lambda item: int(item[0])
    ):

        if int(level_number) > level:

            next_level = int(level_number)
            next_xp = data["xp_required"]

            role = interaction.guild.get_role(
                int(data["role_id"])
            )

            if role is not None:

                next_role_name = role.name

            break

    # =========================
    # CRÉATION DU MESSAGE
    # =========================

    if next_level is not None:

        remaining_xp = next_xp - xp

        description = (
            f"🪨 **Titre actuel :** {current_role_name}\n"
            f"📊 **Niveau :** {level}\n"
            f"⭐ **XP :** {xp} / {next_xp}\n\n"
            f"🎯 **Prochain titre :** "
            f"{next_role_name}\n"
            f"➡️ Encore **{remaining_xp} XP**"
        )

    else:

        description = (
            f"🪨 **Titre actuel :** {current_role_name}\n"
            f"📊 **Niveau :** {level}\n"
            f"⭐ **XP :** {xp}\n\n"
            f"🏆 Tu as atteint le niveau maximum "
            f"configuré !"
        )

    embed = discord.Embed(
        title=(
            f"📈 Niveau de "
            f"{interaction.user.display_name}"
        ),
        description=description
    )

    await interaction.response.send_message(
        embed=embed
    )


# =========================
# BOT CONNECTÉ
# =========================

@bot.event
async def on_ready():

    print(f"Bot connecté : {bot.user}")
    print(f"Serveurs : {len(bot.guilds)}")

    try:

        for guild in bot.guilds:

            # Copie les commandes globales vers ce serveur
            bot.tree.copy_global_to(guild=guild)

            # Synchronise les commandes sur le serveur
            synced = await bot.tree.sync(guild=guild)

            print(
                f"Commandes synchronisées sur "
                f"{guild.name} : {len(synced)}"
            )

            print(
                f"Commandes : "
                f"{[command.name for command in synced]}"
            )

    except Exception as error:

        print(
            f"Erreur de synchronisation : {error}"
        )

    print("Système XP chargé !")


# =========================
# MESSAGE
# =========================

@bot.event
async def on_message(message):

    # Ignore les bots
    if message.author.bot:
        return

    # Ignore les messages privés
    if message.guild is None:
        return

    user_id = message.author.id
    guild_id = message.guild.id

    # =========================
    # COOLDOWN
    # =========================

    now = time.time()

    cooldown = config["xp"]["cooldown"]

    key = (guild_id, user_id)

    if key in last_xp_gain:

        elapsed = now - last_xp_gain[key]

        if elapsed < cooldown:

            return

    last_xp_gain[key] = now

    # =========================
    # XP GAGNÉE
    # =========================

    xp_min = config["xp"]["min"]
    xp_max = config["xp"]["max"]

    xp_gained = random.randint(
        xp_min,
        xp_max
    )

    # =========================
    # XP ACTUELLE
    # =========================

    cursor.execute(
        """
        SELECT xp
        FROM users
        WHERE user_id = ? AND guild_id = ?
        """,
        (user_id, guild_id)
    )

    result = cursor.fetchone()

    if result is None:

        old_xp = 0
        new_xp = xp_gained

        cursor.execute(
            """
            INSERT INTO users
            (user_id, guild_id, xp)
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                guild_id,
                new_xp
            )
        )

    else:

        old_xp = result[0]
        new_xp = old_xp + xp_gained

        cursor.execute(
            """
            UPDATE users
            SET xp = ?
            WHERE user_id = ?
            AND guild_id = ?
            """,
            (
                new_xp,
                user_id,
                guild_id
            )
        )

    database.commit()

    # =========================
    # CALCUL DES NIVEAUX
    # =========================

    old_level = get_level(old_xp)
    new_level = get_level(new_xp)

    print(
        f"{message.author} : "
        f"+{xp_gained} XP | "
        f"{new_xp} XP | "
        f"niveau {new_level}"
    )

    # =========================
    # NOUVEAU NIVEAU
    # =========================

    if new_level > old_level:

        await update_role(
            message.author,
            new_level
        )

        # Salon des annonces de niveaux
        level_up_channel_id = int(
            config["level_up_channel_id"]
        )

        level_up_channel = bot.get_channel(
            level_up_channel_id
        )

        if level_up_channel is not None:

            await level_up_channel.send(
                f"🎉 Félicitations "
                f"{message.author.mention} ! "
                f"Tu viens d'atteindre le "
                f"**niveau {new_level}** !"
            )

    # Vérifie également le rôle si le membre
    # avait déjà atteint ce niveau avant
    elif new_level >= 5:

        await update_role(
            message.author,
            new_level
        )


# =========================
# VÉRIFICATION DU TOKEN
# =========================

if not TOKEN:

    raise RuntimeError(
        "Le token Discord est introuvable "
        "dans le fichier .env"
    )


# =========================
# SERVEUR HTTP POUR RENDER
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)
        self.end_headers()

        self.wfile.write(
            b"thecrock is online"
        )

    def log_message(self, format, *args):
        return


def start_web_server():

    port = int(
        os.getenv("PORT", "10000")
    )

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    server.serve_forever()


threading.Thread(
    target=start_web_server,
    daemon=True
).start()


# =========================
# DÉMARRAGE
# =========================

bot.run(TOKEN)
