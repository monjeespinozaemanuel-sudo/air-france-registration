AIR FRANCE REGISTRATION BOT
===========================

Este paquete contiene el código inicial del bot de inscripciones.

ARCHIVOS
- bot.py: código del bot.
- requirements.txt: dependencias.
- .env.example: plantilla de configuración (no contiene secretos).

CONFIGURACIÓN QUE FALTA
1. Crear un archivo .env a partir de .env.example.
2. Añadir el token privado del bot y los IDs de servidor, canal de solicitudes y rol de instructores.
3. Instalar dependencias: pip install -r requirements.txt
4. Ejecutar: python bot.py
5. En Discord, usar /setup_inscripciones en el canal público de inscripciones.

IMPORTANTE
- Nunca compartas DISCORD_TOKEN por chat ni lo subas a GitHub.
- El bot necesita View Channel, Send Messages, Embed Links y Read Message History
  en los canales que utiliza.
- Para interacciones persistentes, no elimines ni recrees la aplicación del bot.
- La base SQLite debe estar en almacenamiento persistente del hosting para conservar
  solicitudes tras reinicios.
- Configura GUILD_ID para sincronizar el comando en tu servidor de forma rápida.
- El rol de instructores debe ser un rol real del servidor.
- Si los mensajes directos están cerrados, el aspirante no recibirá la notificación.
