import os
import sqlite3
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = int(os.getenv("GUILD_ID", "0") or 0)
APPLICATION_CHANNEL_ID = int(os.getenv("APPLICATION_CHANNEL_ID", "0") or 0)
INSTRUCTOR_ROLE_ID = int(os.getenv("INSTRUCTOR_ROLE_ID", "0") or 0)
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0") or 0)

DB_PATH = os.getenv("DB_PATH", "applications.db")
AIRCRAFT = [
("Airbus A220", "AIRBUS"),
("Airbus A320", "AIRBUS"),
("Airbus A330", "AIRBUS"),
("Airbus A340", "AIRBUS"),
("Airbus A350", "AIRBUS"),

("Boeing B737", "BOEING"),
("Boeing B777", "BOEING"),
("Boeing B787", "BOEING"),
("Boeing B747", "BOEING"),

("Concorde", "CONCORDE"),

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("air-france-registration")


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            discord_name TEXT NOT NULL,
            roblox_name TEXT NOT NULL,
            aircraft TEXT NOT NULL,
            country TEXT NOT NULL,
            experience TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            reviewer_id INTEGER,
            review_note TEXT,
            created_at TEXT NOT NULL,
            message_id INTEGER
        )
        """)
        con.execute("""
        CREATE INDEX IF NOT EXISTS idx_app_user_status
        ON applications(user_id, status)
        """)


def has_pending(user_id: int) -> bool:
    with db() as con:
        row = con.execute(
            "SELECT id FROM applications WHERE user_id=? AND status='PENDING'",
            (user_id,)
        ).fetchone()
    return row is not None


def create_application(user, roblox, aircraft, country, experience):
    with db() as con:
        cur = con.execute("""
        INSERT INTO applications
        (user_id, discord_name, roblox_name, aircraft, country, experience, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user.id, str(user), roblox, aircraft, country, experience,
            datetime.now(timezone.utc).isoformat()
        ))
        return cur.lastrowid


def get_application(app_id):
    with db() as con:
        return con.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()


def update_application(app_id, status, reviewer_id, note=None):
    with db() as con:
        con.execute("""
        UPDATE applications SET status=?, reviewer_id=?, review_note=?
        WHERE id=? AND status='PENDING'
        """, (status, reviewer_id, note, app_id))


def update_message_id(app_id, message_id):
    with db() as con:
        con.execute("UPDATE applications SET message_id=? WHERE id=?", (message_id, app_id))


class ApplicationModal(discord.ui.Modal, title="AIR FRANCE | Pilot Registration"):
    roblox = discord.ui.TextInput(
        label="Usuario de Roblox",
        placeholder="Escribe tu usuario exacto de Roblox",
        min_length=3, max_length=32
    )
    country = discord.ui.TextInput(
        label="País",
        placeholder="Ej. México, Argentina, Colombia",
        min_length=2, max_length=40
    )
    experience = discord.ui.TextInput(
        label="Experiencia en PTFS",
        placeholder="Principiante, intermedio o avanzado",
        min_length=3, max_length=30
    )

    def __init__(self, aircraft: str):
        super().__init__()
        self.aircraft = aircraft

    async def on_submit(self, interaction: discord.Interaction):
        if has_pending(interaction.user.id):
            await interaction.response.send_message(
                "Ya tienes una solicitud pendiente de revisión. Espera la respuesta de los instructores.",
                ephemeral=True
            )
            return

        app_id = create_application(
            interaction.user,
            str(self.roblox.value).strip(),
            self.aircraft,
            str(self.country.value).strip(),
            str(self.experience.value).strip()
        )

        channel = interaction.client.get_channel(APPLICATION_CHANNEL_ID)
        if channel is None:
            try:
                channel = await interaction.client.fetch_channel(APPLICATION_CHANNEL_ID)
            except Exception:
                channel = None

        if channel is None:
            await interaction.response.send_message(
                "No se pudo localizar el canal de solicitudes. Contacta con la administración.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="NEW PILOT APPLICATION",
            description="Se ha recibido una nueva solicitud de inscripción.",
            color=discord.Color.from_rgb(35, 91, 145),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Solicitud", value=f"`AF-{app_id:04d}`", inline=True)
        embed.add_field(name="Estado", value="🟡 PENDING", inline=True)
        embed.add_field(name="Aspirante", value=f"{interaction.user.mention}\n`{interaction.user}`", inline=False)
        embed.add_field(name="Roblox", value=f"`{self.roblox.value}`", inline=True)
        embed.add_field(name="Aeronave solicitada", value=f"**{self.aircraft}**", inline=True)
        embed.add_field(name="País", value=str(self.country.value), inline=True)
        embed.add_field(name="Experiencia PTFS", value=str(self.experience.value), inline=True)
        embed.set_footer(text="AIR FRANCE | FLIGHT OPERATIONS")
        view = ReviewView(app_id)

        try:
            msg = await channel.send(embed=embed, view=view)
            update_message_id(app_id, msg.id)
        except discord.Forbidden:
            await interaction.response.send_message(
                "El bot no tiene permiso para publicar en el canal de instructores. Contacta con la administración.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"¡Tu solicitud `AF-{app_id:04d}` fue enviada correctamente! Los instructores la revisarán.",
            ephemeral=True
        )


class AircraftSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=name, description=f"Familia {family}", value=name)
            for name, family in AIRCRAFT
        ]
        super().__init__(
            placeholder="Selecciona la aeronave que deseas pilotar",
            min_values=1, max_values=1, options=options,
            custom_id="af_registration:aircraft"
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_aircraft = self.values[0]
        await interaction.response.edit_message(
            content=f"Aeronave seleccionada: **{self.values[0]}**\nAhora pulsa **Continuar** para completar tus datos.",
            view=self.view
        )


class AircraftView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.selected_aircraft = None
        self.add_item(AircraftSelect())

    @discord.ui.button(label="Continuar", style=discord.ButtonStyle.primary, emoji="✈️")
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_aircraft:
            await interaction.response.send_message(
                "Primero selecciona una aeronave.", ephemeral=True
            )
            return
        await interaction.response.send_modal(ApplicationModal(self.selected_aircraft))


class RegistrationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="REGISTRARME COMO PILOTO",
        style=discord.ButtonStyle.primary,
        emoji="✈️",
        custom_id="af_registration:start"
    )
    async def register(self, interaction: discord.Interaction, button: discord.ui.Button):
        if has_pending(interaction.user.id):
            await interaction.response.send_message(
                "Ya tienes una solicitud pendiente. No necesitas enviar otra.",
                ephemeral=True
            )
            return
        await interaction.response.send_message(
            "## AIR FRANCE | PILOT REGISTRATION\nSelecciona la aeronave que deseas pilotar.",
            view=AircraftView(),
            ephemeral=True
        )


class ReviewView(discord.ui.View):
    def __init__(self, app_id: int):
        super().__init__(timeout=None)
        self.app_id = app_id
        for label, style, action, emoji in [
            ("Aprobar", discord.ButtonStyle.success, "approve", "✅"),
            ("Rechazar", discord.ButtonStyle.danger, "reject", "⛔"),
            ("Solicitar prueba", discord.ButtonStyle.primary, "test", "🛫"),
        ]:
            button = discord.ui.Button(
                label=label, style=style, emoji=emoji,
                custom_id=f"af_review:{action}:{app_id}"
            )
            button.callback = self.make_callback(action)
            self.add_item(button)

    def make_callback(self, action):
        async def callback(interaction: discord.Interaction):
            role = interaction.guild.get_role(INSTRUCTOR_ROLE_ID) if interaction.guild else None
            is_admin = interaction.user.guild_permissions.administrator if interaction.guild else False
            is_instructor = role in getattr(interaction.user, "roles", []) if role else False
            if not (is_admin or is_instructor):
                await interaction.response.send_message(
                    "Solo los instructores autorizados pueden revisar solicitudes.",
                    ephemeral=True
                )
                return

            app = get_application(self.app_id)
            if not app or app["status"] != "PENDING":
                await interaction.response.send_message(
                    "Esta solicitud ya fue revisada o no existe.", ephemeral=True
                )
                return

            if action == "test":
                update_application(self.app_id, "TEST", interaction.user.id, "Prueba de vuelo solicitada")
                status_text = "🛫 FLIGHT TEST REQUESTED"
                user_text = "Los instructores han solicitado que realices una prueba de vuelo. Contacta con ellos para coordinarla."
            elif action == "approve":
                update_application(self.app_id, "APPROVED", interaction.user.id, "Aprobada")
                status_text = "🟢 APPROVED"
                user_text = "¡Tu solicitud para AIR FRANCE | PTFS ha sido aprobada!"
            else:
                update_application(self.app_id, "REJECTED", interaction.user.id, "Rechazada")
                status_text = "🔴 REJECTED"
                user_text = "Tu solicitud para AIR FRANCE | PTFS no ha sido aprobada. Puedes contactar con el equipo de instructores si necesitas más información."

            embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
            embed.color = (
                discord.Color.green() if action == "approve"
                else discord.Color.red() if action == "reject"
                else discord.Color.blue()
            )
            embed.add_field(name="Resultado", value=status_text, inline=False)
            embed.add_field(name="Revisado por", value=interaction.user.mention, inline=True)
            await interaction.response.edit_message(embed=embed, view=None)

            try:
                user = await interaction.client.fetch_user(app["user_id"])
                await user.send(user_text)
            except (discord.Forbidden, discord.HTTPException):
                pass

            if LOG_CHANNEL_ID:
                log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
                if log_channel:
                    await log_channel.send(
                        f"Solicitud `AF-{self.app_id:04d}`: **{status_text}** por {interaction.user.mention}."
                    )
        return callback


class AirFranceBot(commands.Bot):
    async def setup_hook(self):
        init_db()
        self.add_view(RegistrationView())
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


intents = discord.Intents.default()
bot = AirFranceBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    log.info("Conectado como %s", bot.user)


@bot.tree.command(name="setup_inscripciones", description="Publica el panel de inscripción de pilotos AIR FRANCE.")
@app_commands.checks.has_permissions(administrator=True)
async def setup_inscripciones(interaction: discord.Interaction):
    embed = discord.Embed(
        title="AIR FRANCE | PILOT REGISTRATION",
        description=(
            "¿Deseas formar parte de nuestra tripulación?\n\n"
            "Selecciona **REGISTRARME COMO PILOTO** para enviar tu solicitud.\n"
            "Los instructores revisarán tu información y te comunicarán el resultado."
        ),
        color=discord.Color.from_rgb(35, 91, 145)
    )
    embed.set_footer(text="AIR FRANCE | PTFS • Flight Operations")
    await interaction.channel.send(embed=embed, view=RegistrationView())
    await interaction.response.send_message(
        "Panel de inscripción publicado correctamente.", ephemeral=True
    )


@setup_inscripciones.error
async def setup_inscripciones_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "Necesitas permisos de administrador para publicar el panel."
    else:
        msg = "No se pudo publicar el panel. Revisa los permisos y la configuración del bot."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("Falta DISCORD_TOKEN en las variables de entorno.")
    if not APPLICATION_CHANNEL_ID:
        raise RuntimeError("Falta APPLICATION_CHANNEL_ID en las variables de entorno.")
    if not INSTRUCTOR_ROLE_ID:
        raise RuntimeError("Falta INSTRUCTOR_ROLE_ID en las variables de entorno.")
    bot.run(TOKEN)
