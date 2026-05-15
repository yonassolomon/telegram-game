# 🎮 Bingo2Bingo — Telegram Bingo Game Bot

A modern, multiplayer Telegram bingo bot built with Django + python-telegram-bot.  
Features coin system, rooms, leaderboard, referrals, daily bonuses, and an admin panel.

## 🚀 Quick Start

### 1. Clone & Enter

```bash
cd telegram-bingo
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:
```
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
SECRET_KEY=your_random_secret_key
DEBUG=True
```

### 5. Run Migrations

```bash
python manage.py makemigrations users wallets referrals games
python manage.py migrate
```

### 6. Create Admin User

```bash
python manage.py createsuperuser
```

### 7. Run the Bot

```bash
python manage.py runbot
```

### 8. (Optional) Run Django Admin

In a separate terminal:

```bash
python manage.py runserver
```

Then open http://127.0.0.1:8000/admin/

## 📂 Project Structure

```
telegram-bingo/
├── config/                  # Django project config
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── core/                    # Shared utilities
│   └── utils.py             # Bingo card generator, card formatter
├── users/                   # Player management
│   ├── models.py            # Player model
│   ├── admin.py             # Django admin for players
│   └── services.py          # get_or_create_player, coin operations
├── wallets/                 # Coin transactions
│   ├── models.py            # Transaction model
│   └── admin.py
├── referrals/               # Referral system
│   ├── models.py            # Referral model
│   └── admin.py
├── games/                   # Game logic
│   ├── models.py            # GameRoom, BingoCard, GameHistory
│   ├── admin.py
│   └── services.py
├── bot/                     # Telegram bot
│   ├── handlers/            # Command & callback handlers
│   │   ├── start.py         # /start command
│   │   ├── menu.py          # Main menu callback
│   │   ├── play.py          # Room creation, joining, leaving
│   │   ├── game.py          # Bingo game engine (start, run, win)
│   │   ├── wallet.py        # Wallet/inventory view
│   │   ├── leaderboard.py   # Top players view
│   │   ├── daily.py         # Daily bonus claim
│   │   ├── referral.py      # Referral/invite system
│   │   ├── help.py          # Help menu
│   │   └── callbacks.py     # Callback query router
│   ├── keyboards/
│   │   └── inline.py        # All inline keyboard builders
│   └── management/commands/
│       └── runbot.py        # manage.py runbot command
├── .env.example
├── requirements.txt
├── manage.py
└── README.md
```

## 🎯 How to Play

1. **Start** — `/start` to register and get 500 free coins
2. **Play** — Tap "🎮 Play Bingo" to see available rooms or create your own
3. **Join/Create** — Join a public room or create one with custom entry fee & player limit
4. **Wait** — Room fills up, then someone taps "Start Game"
5. **Bingo!** — Numbers are called. Mark 5 in a row, column, or diagonal to WIN
6. **Win** — Winner takes the prize pool. Everyone gets XP.

## 🛠️ Admin Panel Features

- Manage players (view, ban, unban, adjust coins)
- View all transactions
- View game history
- Monitor referrals
- Bulk actions (add coins to selected users)

## 🔧 Development (VS Code)

```bash
# Terminal 1: Run the bot
python manage.py runbot

# Terminal 2: Run Django admin
python manage.py runserver

# Create migrations after model changes
python manage.py makemigrations
python manage.py migrate
```

## 📦 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 4.2+ |
| Bot | python-telegram-bot 21+ |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Admin | Django Admin |
| Python | 3.10+ |

## 🔐 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | (required) |
| `SECRET_KEY` | Django secret key | (required) |
| `DEBUG` | Debug mode | True |
| `DATABASE_URL` | Database URL | sqlite:///db.sqlite3 |

## 📝 License

MIT
