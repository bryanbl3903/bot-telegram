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


def obtener_siguiente_cliente_numero(clientes):

    numeros = []

    for c in clientes.values():

        numero = c.get("cliente_numero")

        if isinstance(numero, int):

            numeros.append(numero)

    if not numeros:

        return 1

    return max(numeros) + 1


def registrar_usuario(user):

    clientes = cargar_clientes()

    user_id = str(user.id)

    ahora = datetime.now()

    nuevo_vencimiento = ahora + timedelta(days=30)

    # Si el usuario ya existe en la lista

    if user_id in clientes:

        cliente = clientes[user_id]

        # Si sigue activo, NO se le reinician los 30 días

        if cliente.get("estado") == "activo":

            cliente["nombre"] = user.full_name

            cliente["username"] = user.username if user.username else ""

            guardar_clientes(clientes)

            print(f"Usuario ya activo, no se reinicia: {user.full_name} | ID: {user.id}")

            return

        # Si estaba vencido, se borra su registro anterior y se crea uno nuevo

        if cliente.get("estado") == "vencido":

            del clientes[user_id]

    # Crear registro nuevo

    clientes[user_id] = {

        "user_id": user.id,

        "cliente_numero": obtener_siguiente_cliente_numero(clientes),

        "nombre": user.full_name,

        "username": user.username if user.username else "",

        "fecha_ingreso": ahora.strftime("%Y-%m-%d %H:%M:%S"),

        "fecha_vencimiento": nuevo_vencimiento.strftime("%Y-%m-%d %H:%M:%S"),

        "estado": "activo"

    }

    guardar_clientes(clientes)

    print(

        f"Guardado nuevo: {user.full_name} | "

        f"ID: {user.id} | "

        f"Vence: {nuevo_vencimiento}"

    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola 👋\n"
        "Soy tu bot.\n"
        "Registro usuarios y expulso automáticamente a los vencidos."
    )


async def asignar_numeros(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data = cargar_clientes()

    numeros_usados = set()

    asignados = 0

    for c in data.values():

        numero = c.get("cliente_numero")

        if isinstance(numero, int):

            numeros_usados.add(numero)

        elif isinstance(numero, str) and numero.isdigit():

            c["cliente_numero"] = int(numero)

            numeros_usados.add(int(numero))

    siguiente = 1

    for user_id, c in data.items():

        numero = c.get("cliente_numero")

        if not isinstance(numero, int):

            while siguiente in numeros_usados:

                siguiente += 1

            c["cliente_numero"] = siguiente

            numeros_usados.add(siguiente)

            asignados += 1

    guardar_clientes(data)

    await update.message.reply_text(

        f"✅ Números asignados correctamente\n"

        f"Clientes actualizados: {asignados}\n"

        f"Total clientes: {len(data)}"

    )


async def renovo_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:

        await update.message.reply_text("Usa así: /renovo_cliente NUMERO")

        return

    if not context.args[0].isdigit():

        await update.message.reply_text("El número de cliente debe ser un número.")

        return

    cliente_numero = int(context.args[0])

    data = cargar_clientes()

    objetivo_id = None

    for user_id, c in data.items():

        if c.get("cliente_numero") == cliente_numero:

            objetivo_id = user_id

            break

    if not objetivo_id:

        await update.message.reply_text("No encontré ese número de cliente.")

        return

    ahora = datetime.now()

    fecha_actual_vencimiento = datetime.strptime(

        data[objetivo_id]["fecha_vencimiento"], "%Y-%m-%d %H:%M:%S"

    )

    base = fecha_actual_vencimiento if fecha_actual_vencimiento > ahora else ahora

    nuevo_vencimiento = base + timedelta(days=30)

    data[objetivo_id]["fecha_vencimiento"] = nuevo_vencimiento.strftime("%Y-%m-%d %H:%M:%S")

    data[objetivo_id]["estado"] = "activo"

    guardar_clientes(data)

    await update.message.reply_text(

        f"✅ Renovado cliente #{cliente_numero}\n"

        f"Nombre: {data[objetivo_id]['nombre']}\n"

        f"ID: {objetivo_id}\n"

        f"Nuevo vencimiento: {data[objetivo_id]['fecha_vencimiento']}"

    )


async def limpiar_duplicados(update: Update, context: ContextTypes.DEFAULT_TYPE):

    data = cargar_clientes()

    limpio = {}

    eliminados = 0

    reporte = []

    def convertir_fecha(fecha_texto):

        try:

            return datetime.strptime(fecha_texto, "%Y-%m-%d %H:%M:%S")

        except:

            return datetime.min

    for clave, cliente in data.items():

        user_id = str(cliente.get("user_id", clave))

        nombre = cliente.get("nombre", "Sin nombre")

        cliente["user_id"] = int(user_id) if user_id.isdigit() else user_id

        if user_id not in limpio:

            limpio[user_id] = cliente

        else:

            existente = limpio[user_id]

            fecha_existente = convertir_fecha(existente.get("fecha_vencimiento", ""))

            fecha_nueva = convertir_fecha(cliente.get("fecha_vencimiento", ""))

            if fecha_nueva > fecha_existente:

                reporte.append(f"🔁 Reemplazado: {nombre} | ID: {user_id}")

                limpio[user_id] = cliente

            else:

                reporte.append(f"🗑️ Eliminado: {nombre} | ID: {user_id}")

            eliminados += 1

    guardar_clientes(limpio)

    mensaje = (

        f"✅ Limpieza terminada\n"

        f"Duplicados eliminados: {eliminados}\n"

        f"Clientes finales: {len(limpio)}\n\n"

    )

    # Evita que el mensaje sea demasiado largo

    detalle = "\n".join(reporte[:20])

    if len(reporte) > 20:

        detalle += f"\n... y {len(reporte) - 20} más"

    await update.message.reply_text(mensaje + detalle)


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


async def dias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("Usa así: /dias ID_o_@usuario cantidad_de_dias")
        return

    entrada = context.args[0].strip()
    dias_texto = context.args[1].strip()

    if not dias_texto.isdigit():
        await update.message.reply_text("La cantidad de días debe ser un número.")
        return

    cantidad_dias = int(dias_texto)
    data = cargar_clientes()

    objetivo_id = None

    if entrada.isdigit():
        if entrada in data:
            objetivo_id = entrada
    else:
        username_buscado = entrada.lower().replace("@", "")
        for user_id, c in data.items():
            username = c.get("username", "").lower()
            if username == username_buscado:
                objetivo_id = user_id
                break

    if not objetivo_id:
        await update.message.reply_text("No encontré ese usuario.")
        return

    ahora = datetime.now()
    nuevo_vencimiento = ahora + timedelta(days=cantidad_dias)

    data[objetivo_id]["fecha_vencimiento"] = nuevo_vencimiento.strftime("%Y-%m-%d %H:%M:%S")
    data[objetivo_id]["estado"] = "activo"

    guardar_clientes(data)

    await update.message.reply_text(
        f"✅ Tiempo actualizado para {data[objetivo_id]['nombre']}\n"
        f"ID: {objetivo_id}\n"
        f"Días asignados: {cantidad_dias}\n"
        f"Nuevo vencimiento: {data[objetivo_id]['fecha_vencimiento']}"
    )


async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usa así: /buscar nombre_o_usuario")
        return

    termino = " ".join(context.args).strip().lower()
    data = cargar_clientes()

    resultados = []

    for user_id, c in data.items():
        nombre = c.get("nombre", "").lower()
        username = c.get("username", "").lower()
        user_id_texto = str(c.get("user_id", user_id))
        cliente_numero_texto = str(c.get("cliente_numero", ""))

    if (
        termino in nombre
        or termino in username
        or termino in user_id_texto
        or termino == cliente_numero_texto
    ):
        resultados.append(c)

if not resultados:
    await update.message.reply_text("No encontré usuarios con ese dato.")
    return

    texto = f"Resultados para: {termino}\n\n"

    for c in resultados[:20]:
        username = f"@{c['username']}" if c["username"] else "sin username"
        texto += (
            f"{c['nombre']}\n"
            f"Usuario: {username}\n"
            f"ID: {c['user_id']}\n"
            f"Vence: {c['fecha_vencimiento']}\n"
            f"Estado: {c['estado']}\n\n"
        )

    if len(resultados) > 20:
        texto += f"Mostrando 20 de {len(resultados)} resultados."

    await update.message.reply_text(texto[:4000])


async def renovo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usa así: /renovo ID o /renovo @usuario")
        return

    entrada = " ".join(context.args).strip()
    data = cargar_clientes()

    objetivo_id = None

    if entrada.isdigit():
        if entrada in data:
            objetivo_id = entrada
    else:
        username_buscado = entrada.lower().replace("@", "")
        for user_id, c in data.items():
            username = c.get("username", "").lower()
            if username == username_buscado:
                objetivo_id = user_id
                break

    if not objetivo_id:
        await update.message.reply_text("No encontré ese usuario.")
        return

    ahora = datetime.now()
    fecha_actual_vencimiento = datetime.strptime(
        data[objetivo_id]["fecha_vencimiento"], "%Y-%m-%d %H:%M:%S"
    )

    base = fecha_actual_vencimiento if fecha_actual_vencimiento > ahora else ahora
    nuevo_vencimiento = base + timedelta(days=30)

    data[objetivo_id]["fecha_vencimiento"] = nuevo_vencimiento.strftime("%Y-%m-%d %H:%M:%S")
    data[objetivo_id]["estado"] = "activo"

    guardar_clientes(data)

    await update.message.reply_text(
        f"✅ Renovado: {data[objetivo_id]['nombre']}\n"
        f"ID: {objetivo_id}\n"
        f"Nuevo vencimiento: {data[objetivo_id]['fecha_vencimiento']}"
    )


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with open(ARCHIVO_CLIENTES, "rb") as archivo:
            await context.bot.send_document(
                chat_id=update.effective_user.id,
                document=archivo,
                filename="clientes.json",
                caption="📁 Backup actual de clientes"
            )
    except Exception as e:
        await update.message.reply_text(f"Error al enviar backup: {e}")


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
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("asignar_numeros", asignar_numeros))
    app.add_handler(CommandHandler("renovo_cliente", renovo_cliente))
    app.add_handler(CommandHandler("limpiar_duplicados", limpiar_duplicados))
    app.add_handler(CommandHandler("dias", dias))
    app.add_handler(CommandHandler("buscar", buscar))
    app.add_handler(CommandHandler("renovo", renovo))
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
