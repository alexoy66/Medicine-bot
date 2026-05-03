import json
import os
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

TOKEN = os.environ.get("TOKEN")
DATA_FILE = "medicine.json"
NOME, ORA, FREQUENZA, CONFERMA = range(4)

def carica_dati():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def salva_dati(dati):
    with open(DATA_FILE, "w") as f:
        json.dump(dati, f, indent=2, ensure_ascii=False)

def get_medicine_utente(user_id):
    return carica_dati().get(str(user_id), [])

def salva_medicine_utente(user_id, medicine):
    dati = carica_dati()
    dati[str(user_id)] = medicine
    salva_dati(dati)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nome = update.effective_user.first_name
    await update.message.reply_text(
        f"💊 Ciao {nome}! Sono il tuo bot per i promemoria medicine.\n\n"
        "➕ /aggiungi — Aggiungi una medicina\n"
        "📋 /lista — Vedi le tue medicine\n"
        "❌ /elimina — Elimina una medicina\n\n"
        "Ti manderò una notifica ad ogni orario che imposti! 🔔"
    )

async def aggiungi_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "➕ *Aggiunta nuova medicina*\n\nCome si chiama la medicina?\n\nScrivi /annulla per uscire.",
        parse_mode="Markdown"
    )
    return NOME

async def aggiungi_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome"] = update.message.text.strip()
    await update.message.reply_text(
        f"✅ Medicina: *{context.user_data['nome']}*\n\n"
        "🕐 A che ora devi prenderla?\n"
        "Formato *HH:MM* es. `08:00`\n"
        "Più orari separati da virgola: `08:00, 21:00`",
        parse_mode="Markdown"
    )
    return ORA

async def aggiungi_ora(update: Update, context: ContextTypes.DEFAULT_TYPE):
    orari = [o.strip() for o in update.message.text.strip().split(",")]
    orari_validi = []
    for orario in orari:
        try:
            datetime.strptime(orario, "%H:%M")
            orari_validi.append(orario)
        except ValueError:
            await update.message.reply_text(f"❌ Orario non valido: *{orario}*\nUsa HH:MM", parse_mode="Markdown")
            return ORA
    context.user_data["orari"] = orari_validi
    keyboard = [
        [InlineKeyboardButton("📅 Ogni giorno", callback_data="freq_giorno")],
        [InlineKeyboardButton("📅 Giorni feriali", callback_data="freq_feriali")],
        [InlineKeyboardButton("📅 Fine settimana", callback_data="freq_weekend")],
    ]
    await update.message.reply_text(
        f"✅ Orari: *{', '.join(orari_validi)}*\n\n📆 Con quale frequenza?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return FREQUENZA

async def aggiungi_frequenza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    freq_map = {"freq_giorno": "Ogni giorno", "freq_feriali": "Giorni feriali", "freq_weekend": "Fine settimana"}
    context.user_data["frequenza"] = query.data
    keyboard = [
        [InlineKeyboardButton("✅ Conferma", callback_data="conferma_si")],
        [InlineKeyboardButton("❌ Annulla", callback_data="conferma_no")],
    ]
    await query.edit_message_text(
        f"📋 *Riepilogo:*\n\n💊 *{context.user_data['nome']}*\n"
        f"🕐 {', '.join(context.user_data['orari'])}\n"
        f"📅 {freq_map[query.data]}\n\nConfermi?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CONFERMA

async def aggiungi_conferma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "conferma_si":
        user_id = update.effective_user.id
        medicine = get_medicine_utente(user_id)
        nuova = {
            "id": len(medicine) + 1,
            "nome": context.user_data["nome"],
            "orari": context.user_data["orari"],
            "frequenza": context.user_data["frequenza"],
            "attiva": True
        }
        medicine.append(nuova)
        salva_medicine_utente(user_id, medicine)
        registra_promemoria(context.application, user_id, nuova)
        await query.edit_message_text(
            f"✅ *{nuova['nome']}* aggiunta!\n🔔 Promemoria alle: *{', '.join(nuova['orari'])}*",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text("❌ Annullato.")
    context.user_data.clear()
    return ConversationHandler.END

async def annulla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Operazione annullata.")
    return ConversationHandler.END

async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    medicine = get_medicine_utente(update.effective_user.id)
    if not medicine:
        await update.message.reply_text("📋 Nessuna medicina. Usa /aggiungi!")
        return
    freq_map = {"freq_giorno": "Ogni giorno", "freq_feriali": "Giorni feriali", "freq_weekend": "Fine settimana"}
    testo = "📋 *Le tue medicine:*\n\n"
    for m in medicine:
        testo += f"🟢 *{m['nome']}*\n   🕐 {', '.join(m['orari'])}\n   📅 {freq_map.get(m['frequenza'], '')}\n\n"
    await update.message.reply_text(testo, parse_mode="Markdown")

async def elimina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    medicine = get_medicine_utente(update.effective_user.id)
    if not medicine:
        await update.message.reply_text("📋 Nessuna medicina da eliminare.")
        return
    keyboard = [[InlineKeyboardButton(f"❌ {m['nome']} ({', '.join(m['orari'])})", callback_data=f"elimina_{m['id']}")] for m in medicine]
    keyboard.append([InlineKeyboardButton("🔙 Annulla", callback_data="elimina_annulla")])
    await update.message.reply_text("Quale medicina vuoi eliminare?", reply_markup=InlineKeyboardMarkup(keyboard))

async def elimina_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "elimina_annulla":
        await query.edit_message_text("🔙 Annullato.")
        return
    med_id = int(query.data.split("_")[1])
    user_id = update.effective_user.id
    medicine = get_medicine_utente(user_id)
    salva_medicine_utente(user_id, [m for m in medicine if m["id"] != med_id])
    rimuovi_promemoria(context.application, user_id, med_id)
    await query.edit_message_text("✅ Medicina eliminata!")

def registra_promemoria(app, user_id, medicina):
    scheduler = app.bot_data.get("scheduler")
    if not scheduler:
        return
    freq_map = {"freq_giorno": "*", "freq_feriali": "mon-fri", "freq_weekend": "sat,sun"}
    giorni = freq_map.get(medicina["frequenza"], "*")
    for orario in medicina["orari"]:
        ora, minuto = map(int, orario.split(":"))
        scheduler.add_job(
            invia_promemoria, trigger="cron",
            hour=ora, minute=minuto, day_of_week=giorni,
            args=[app, user_id, medicina["nome"], orario],
            id=f"med_{user_id}_{medicina['id']}_{orario}",
            replace_existing=True
        )

def rimuovi_promemoria(app, user_id, med_id):
    scheduler = app.bot_data.get("scheduler")
    if not scheduler:
        return
    for job in scheduler.get_jobs():
        if job.id.startswith(f"med_{user_id}_{med_id}_"):
            job.remove()

async def invia_promemoria(app, user_id, nome, orario):
    try:
        await app.bot.send_message(
            chat_id=user_id,
            text=f"💊 *Promemoria!*\n\nÈ ora di prendere: *{nome}*\n🕐 {orario} 🌟",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Errore: {e}")

async def post_init(app):
    scheduler = app.bot_data["scheduler"]
    scheduler.start()
    for user_id, medicine in carica_dati().items():
        for m in medicine:
            if m.get("attiva", True):
                registra_promemoria(app, int(user_id), m)

def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Rome")
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.bot_data["scheduler"] = scheduler

    conv = ConversationHandler(
        entry_points=[CommandHandler("aggiungi", aggiungi_start)],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, aggiungi_nome)],
            ORA: [MessageHandler(filters.TEXT & ~filters.COMMAND, aggiungi_ora)],
            FREQUENZA: [CallbackQueryHandler(aggiungi_frequenza, pattern="^freq_")],
            CONFERMA: [CallbackQueryHandler(aggiungi_conferma, pattern="^conferma_")],
        },
        fallbacks=[CommandHandler("annulla", annulla)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lista", lista))
    app.add_handler(CommandHandler("elimina", elimina))
    app.add_handler(CallbackQueryHandler(elimina_callback, pattern="^elimina_"))
    app.add_handler(conv)
    print("🤖 Bot avviato!")
    app.run_polling()

if __name__ == "__main__":
    main()
