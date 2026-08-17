# 🧠 Qulay Bot — AI eslatma yordamchisi

> 👨‍💻 **Azizbek Atoyev** tomonidan yaratilgan · Admin: [@firstpremiumuser](https://t.me/firstpremiumuser)

Telegram bot: xayolingizdagi ishlarni **matn** yoki **ovozli xabar** bilan aytasiz —
sun'iy intellekt (Google Gemini) ularni tushunadi, muhimlik darajasi va vaqtini
aniqlaydi, saralaydi va kerakli paytda eslatib turadi.

Har bir foydalanuvchi telefon raqami bilan ro'yxatdan o'tadi va faqat **o'z**
ma'lumotlari bilan ishlaydi.

---

## ✨ Imkoniyatlar

| Imkoniyat | Tavsif |
|---|---|
| 🎤 **Ovozli xabar** | Aytasiz — bot tinglab, matnga o'giradi va vazifalarga ajratadi |
| ✍️ **Matnli xabar** | «ertaga soat 3 da shifokorga borish, muhim» → tayyor vazifa |
| 🧩 **Bir nechta vazifa** | Bitta xabardan bir nechta ishni ajratib oladi |
| ❗️ **Avtomatik daraja** | 🔴 Shoshilinch · 🟠 Yuqori · 🟡 O'rta · 🟢 Past |
| ⏰ **Vaqtni tushunish** | «2 soatdan keyin», «juma kechqurun», «25.12 18:00», «har dushanba» |
| 🔁 **Takrorlanish** | Har kuni / ish kunlari / har hafta / har oy / har yili |
| 🔔 **Aqlli eslatmalar** | Muddatdan oldin ogohlantirish + muddati o'tganda turtki |
| 😴 **Keyinroq** | Eslatmani 10 daqiqa / 1 soat / ertaga ertalabga surish |
| 🔀 **Saralash** | Aqlli · Vaqt · Daraja · Yangi + Bugun/Ertaga/Hafta/O'tgan filtrlari |
| ➕ **Qo'lda kiritish** | AI'siz, bosqichma-bosqich vazifa yaratish |
| ✅ **Qo'lda tasdiqlash** | Xohlasangiz, AI natijasini saqlashdan oldin ko'rib chiqasiz |
| 💡 **Muammo va yechim** | Yangi g'oyalarni yozib borish; yechimini keyin qo'shish, 🤖 AI dan taklif so'rash yoki g'oyani vazifaga aylantirish |
| ✉️ **Adminga yozish** | Bir bosishda @firstpremiumuser bilan bog'lanish |
| 🌅 **Kunlik xulosa** | Har kuni belgilangan soatda bugungi rejalar ro'yxati |
| 📊 **Statistika** | Bajarilgan/bajarilmagan, kechikkanlar, bajarilish foizi |
| 🌍 **Vaqt mintaqasi** | Har bir foydalanuvchi uchun alohida |
| 🔐 **Ro'yxatdan o'tish** | Telefon raqam orqali; boshqa odamning kontakti qabul qilinmaydi |

---

## 🚀 Ishga tushirish

### 1. Talablar
- Python 3.11+
- Telegram bot tokeni — [@BotFather](https://t.me/BotFather)
- Gemini API kaliti — [Google AI Studio](https://aistudio.google.com/apikey)

### 2. O'rnatish

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # va ichiga tokenlaringizni yozing
```

### 3. Ishga tushirish

```bash
python -m app.main
```

Telegramda botni oching → `/start` → telefon raqamni yuboring → tayyor.

---

## 🐳 Docker orqali

```bash
docker compose up -d --build
```

Loglarni ko'rish:

```bash
docker compose logs -f
```

Ma'lumotlar bazasi `./data/bot.db` faylida saqlanadi (konteyner o'chsa ham yo'qolmaydi).

---

## 🖥 Serverga o'rnatish (systemd)

Loyiha AWS serverida (`16.16.120.67`) shu tarzda ishlab turibdi:

```bash
# 1. Kodni yuklash
rsync -az --exclude '.venv' --exclude 'data' --exclude '__pycache__' \
  -e "ssh -i ~/avishifo.pem" \
  ./app ./requirements.txt ./.env ubuntu@16.16.120.67:~/qulaybot/

# 2. Muhitni tayyorlash
ssh -i ~/avishifo.pem ubuntu@16.16.120.67 \
  "cd ~/qulaybot && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"

# 3. Xizmatni o'rnatish (deploy/qulaybot.service faylidan)
sudo cp deploy/qulaybot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qulaybot
```

Boshqarish:

```bash
sudo systemctl status qulaybot      # holati
sudo systemctl restart qulaybot     # qayta ishga tushirish
journalctl -u qulaybot -f           # jonli loglar
```

Xizmat fayli [deploy/qulaybot.service](deploy/qulaybot.service) da. U:
- ishdan chiqsa 10 sekundda o'zi qayta ishga tushadi (`Restart=always`);
- server o'chib yonsa avtomatik ko'tariladi (`enable`);
- xotira (400 MB) va CPU (50%) cheklovi bilan ishlaydi — serverdagi boshqa
  loyihalarga xalaqit bermaydi;
- faqat `data/` papkasiga yoza oladi (`ProtectSystem=full`).

---

## ⚙️ Sozlamalar (.env)

| O'zgaruvchi | Tavsif | Standart |
|---|---|---|
| `BOT_TOKEN` | Telegram bot tokeni | **majburiy** |
| `GEMINI_API_KEY` | Gemini API kaliti | **majburiy** |
| `GEMINI_TEXT_MODELS` | Matn uchun modellar zanjiri | `gemini-3.1-flash-lite,gemini-3.7-flash,gemini-flash-latest` |
| `GEMINI_VOICE_MODELS` | Ovoz uchun modellar zanjiri | `gemini-3.7-flash,gemini-flash-latest,gemini-3-flash-preview` |
| `DB_PATH` | SQLite fayli | `data/bot.db` |
| `DEFAULT_TZ` | Yangi foydalanuvchi vaqt mintaqasi | `Asia/Tashkent` |
| `TICK_SECONDS` | Eslatmalarni tekshirish oralig'i | `20` |
| `LOG_LEVEL` | Log darajasi | `INFO` |

> **Model zanjiri:** birinchi model band bo'lsa (`503`) yoki xato bersa, bot
> avtomatik ravishda keyingi modelga o'tadi. Matn uchun tez model, ovoz uchun
> o'zbek nutqini yaxshiroq tushunadigan model tanlangan.

---

## 🏗 Arxitektura

```
app/
├── main.py         # ishga tushirish, dispatcher, graceful shutdown
├── config.py       # .env dan sozlamalar
├── db.py           # SQLite qatlami (har bir so'rov user_id bo'yicha filtrlanadi)
├── gemini.py       # Gemini API klienti (structured output, model zanjiri, retry)
├── analyzer.py     # AI javobini tekshirish/tozalash + zaxira tahlil
├── heuristics.py   # AI'siz vaqt va daraja tahlili (zaxira va qo'lda kiritish)
├── service.py      # vazifa amallari: saqlash, eslatma rejasi, takrorlanish
├── scheduler.py    # fon jarayoni: eslatma yuborish, kunlik xulosa
├── middleware.py   # foydalanuvchini yuklash + ro'yxatdan o'tish nazorati
├── keyboards.py    # inline/reply tugmalar
├── texts.py        # barcha matnlar va kartochka ko'rinishi
├── states.py       # FSM holatlari
├── timeutil.py     # UTC ↔ mahalliy vaqt, o'zbekcha sana formati
└── handlers/
    ├── start.py    # /start, ro'yxatdan o'tish, menyu, statistika
    ├── capture.py  # matn/ovoz → AI → vazifa
    ├── tasks.py    # ro'yxat, kartochka, tahrirlash, bajarish
    ├── newtask.py  # qo'lda yaratish sehrgari
    ├── ideas.py    # 💡 muammo va yechim bo'limi
    ├── settings.py # sozlamalar
    └── render.py   # umumiy chizish yordamchilari
```

### Muhim yechimlar

- **Eslatmalar bazada saqlanadi**, xotirada emas. Bot qayta ishga tushsa ham
  hech qanday eslatma yo'qolmaydi — fon jarayoni har 20 sekundda navbatni
  tekshiradi.
- **Barcha vaqtlar UTC da** saqlanadi, foydalanuvchiga esa uning mintaqasida
  ko'rsatiladi. Takrorlanuvchi vazifalar mahalliy vaqtda hisoblanadi — shunda
  yozgi vaqtga o'tishda ham soat siljimaydi.
- **Ma'lumotlar ajratilgan**: `get_task(task_id, user_id)` kabi barcha so'rovlar
  egasini tekshiradi, shuning uchun boshqaning vazifasiga tegib bo'lmaydi.
- **AI ishlamasa ham bot ishlaydi**: Gemini javob bermasa, `heuristics` moduli
  vaqt va darajani o'zi topishga urinadi.

---

## 🧪 Testlar

```bash
pip install -r requirements-dev.txt
pytest -q
```

48 ta test: vaqt tahlili, baza va ma'lumotlar ajratilishi, eslatma rejasi,
takrorlanish, kunlik xulosa, g'oyalar bo'limi va handlerlarning to'liq oqimi
(Telegram serveri soxta sessiya bilan almashtiriladi).

---

## 🔒 Xavfsizlik

- `.env` fayli `.gitignore` da — kalitlar repozitoriyga tushmaydi.
- Botga yuborilgan ovoz/matn faqat tahlil uchun Gemini API ga yuboriladi.
- Foydalanuvchi `⚙️ Sozlamalar → 🗑 Barcha vazifalarni o'chirish` orqali
  ma'lumotlarini istalgan payt o'chira oladi.

---

## 📋 Buyruqlar

| Buyruq | Vazifasi |
|---|---|
| `/start` | Boshlash / ro'yxatdan o'tish |
| `/tasks` | Barcha vazifalar |
| `/today` | Bugungi ishlar |
| `/new` | Qo'lda yangi vazifa |
| `/ideas` | 💡 Muammo va yechim |
| `/stats` | Statistika |
| `/settings` | Sozlamalar |
| `/admin` | Adminga yozish |
| `/help` | Qo'llanma |
| `/cancel` | Joriy amalni bekor qilish |
