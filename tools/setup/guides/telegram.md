# Setting up Telegram with DexAI

## What You'll Need
- A Telegram account
- 2-3 minutes

## Steps

### 1. Open BotFather

Open Telegram and search for `@BotFather`, or click this link:
https://t.me/BotFather

BotFather is Telegram's official bot for creating and managing bots.

### 2. Create Your Bot

Send `/newbot` to BotFather.

You'll be asked two things:

1. **Bot name**: Choose something friendly like "My Dex Assistant"
   - This is the display name users will see

2. **Username**: Must end in `bot`, like `mydex_bot` or `myname_dexai_bot`
   - This is the unique identifier (no spaces, lowercase)

### 3. Copy Your Token

After creating the bot, BotFather will give you a token that looks like:
```
123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

**Copy this entire token** — including the numbers before the colon.

### 4. Paste in DexAI Setup

Return to the DexAI setup wizard and paste the token.

Click "Test Connection" to verify it works.

### 5. Start Chatting!

Once connected:
1. Open your new bot in Telegram (search for the username you chose)
2. Click "Start" or send any message
3. Dex will respond!

---

## Troubleshooting

### "Token invalid"

- Make sure you copied the **entire** token, including the numbers before the colon
- The token should look like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
- Don't include any extra spaces

### "No response from bot"

- Make sure DexAI is running
- Check that you started a chat with the correct bot username
- Try sending "hello" again

### "Conflict: terminated by other getUpdates request"

This means another instance of DexAI (or another program) is using the same bot token.
- Stop any other DexAI instances
- Or create a new bot with a fresh token

### Need a different bot later?

You can always create more bots with BotFather. Each bot gets its own token.

---

## Optional: Customize Your Bot

After setup, you can customize your bot with BotFather:

- `/setdescription` — Set what users see when they open the bot
- `/setabouttext` — Set the "About" section text
- `/setuserpic` — Upload a profile picture for your bot

---

## Privacy Note

Your Telegram bot token is stored securely in DexAI's encrypted vault.
Never share your bot token publicly — anyone with the token can control your bot.
