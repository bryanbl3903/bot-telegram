import json
import os
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    ChatMemberHandler,
    filters,
)

TOKEN = os.getenv ("TOKEN")
GROUP_CHAT_ID = -1001632540226
ARCHIVO_CLIENTES = os.path.join(
    os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/app/data"),
    "clientes.json"
)


def cargar_clientes():
    if not os.path.exists(ARCHIVO_CLIENTES):
        return {}

    try:
        with open(ARCHIVO_CLIENTES, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def guardar_clientes(clientes):
    with open(ARCHIVO_CLIENTES, "w", encoding="utf-8") as f:
        json.dump(clientes, f, indent=4, ensure_ascii=False)


def registrar_usuario(user):
    clientes = cargar_clientes()
    ahora = datetime.now()
    vencimiento = ahora + timedelta(days=30)

    clientes[str(user.id)] = {
        "user_id": user.id,
        "nombre": user.full_name,
        "username": user.username if user.username else "",
        "fecha_ingreso": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        "fecha_vencimiento": vencimiento.strftime("%Y-%m-%d %H:%M:%S"),
        "estado": "activo"
    }

    guardar_clientes(clientes)
    print(f"Guardado: {user.full_name} | ID: {user.id} | Vence: {vencimiento}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola 👋\n"
        "Soy tu bot.\n"
        "Registro usuarios y expulso automáticamente a los vencidos."
    )


async def clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = cargar_clientes()

    if not data:
        await update.message.reply_text("No hay clientes registrados.")
        return

    texto = "CLIENTES:\n\n"

    for c in data.values():
        username = f"@{c['username']}" if c["username"] else "sin username"
        texto += (
            f"{c['nombre']}\n"
            f"Usuario: {username}\n"
            f"ID: {c['user_id']}\n"
            f"Ingreso: {c['fecha_ingreso']}\n"
            f"Vence: {c['fecha_vencimiento']}\n"
            f"Estado: {c['estado']}\n\n"
        )

    await update.message.reply_text(texto[:4000])


async def vencidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = cargar_clientes()
    ahora = datetime.now()

    lista = []

    for c in data.values():
        fecha_v = datetime.strptime(c["fecha_vencimiento"], "%Y-%m-%d %H:%M:%S")
        if fecha_v <= ahora:
            lista.append(c)

    if not lista:
        await update.message.reply_text("No hay clientes vencidos.")
        return

    texto = "VENCIDOS:\n\n"
    for c in lista:
        texto += (
            f"{c['nombre']}\n"
            f"ID: {c['user_id']}\n"
            f"Vence: {c['fecha_vencimiento']}\n"
            f"Estado: {c['estado']}\n\n"
        )

    await update.message.reply_text(texto[:4000])


async def detectar_por_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return

    for user in update.message.new_chat_members:
        registrar_usuario(user)


async def detectar_por_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cambio = update.chat_member
    if not cambio:
        return

    estado_anterior = cambio.old_chat_member.status
    estado_nuevo = cambio.new_chat_member.status

    estaba_fuera = estado_anterior in ["left", "kicked"]
    entro = estado_nuevo in ["member", "administrator", "restricted"]

    if estaba_fuera and entro:
        registrar_usuario(cambio.new_chat_member.user)


async def revisar_vencidos_automaticamente(context: ContextTypes.DEFAULT_TYPE):
    data = cargar_clientes()
    ahora = datetime.now()
    cambios = False

    for user_id, c in data.items():
        if c["estado"] != "activo":
            continue

        fecha_v = datetime.strptime(c["fecha_vencimiento"], "%Y-%m-%d %H:%M:%S")

        if fecha_v <= ahora:
            try:
                await context.bot.ban_chat_member(
                    chat_id=GROUP_CHAT_ID,
                    user_id=int(user_id)
                )

                await context.bot.unban_chat_member(
                    chat_id=GROUP_CHAT_ID,
                    user_id=int(user_id)
                )

                c["estado"] = "vencido"
                cambios = True
                print(f"Expulsado por vencimiento: {c['nombre']} | ID: {user_id}")

            except Exception as e:
                print(f"Error al expulsar {c['nombre']} ({user_id}): {e}")

    if cambios:
        guardar_clientes(data)


async def revisar_vencidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await revisar_vencidos_automaticamente(context)
    await update.message.reply_text("Revisión de vencidos terminada.")


async def idgrupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"ID del grupo: {update.effective_chat.id}")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clientes", clientes))
    app.add_handler(CommandHandler("vencidos", vencidos))
    app.add_handler(CommandHandler("revisar_vencidos", revisar_vencidos))
    app.add_handler(CommandHandler("idgrupo", idgrupo))

    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, detectar_por_mensaje)
    )
    app.add_handler(
        ChatMemberHandler(detectar_por_estado, ChatMemberHandler.CHAT_MEMBER)
    )

    if app.job_queue:
        app.job_queue.run_repeating(
            revisar_vencidos_automaticamente,
            interval=60,
            first=10
        )

    print("Bot encendido...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
