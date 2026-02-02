# Setting up Discord with DexAI

## What You'll Need
- A Discord account
- A Discord server where you have admin permissions
- 5-10 minutes

## Steps

### 1. Go to Discord Developer Portal

Open your browser and go to:
https://discord.com/developers/applications

Log in with your Discord account if prompted.

### 2. Create a New Application

1. Click the **"New Application"** button (top right)
2. Name it something like "DexAI" or "My Dex Assistant"
3. Accept the terms and click **"Create"**

### 3. Create a Bot User

1. In the left sidebar, click **"Bot"**
2. Click **"Add Bot"** and confirm
3. Under the bot's username, click **"Reset Token"** and confirm
4. Click **"Copy"** to copy the token

**Important:** This is your only chance to copy the token! If you lose it, you'll need to reset it again.

### 4. Configure Bot Settings

While on the Bot page, configure these settings:

**Privileged Gateway Intents** (scroll down):
- ✅ Enable **MESSAGE CONTENT INTENT** — Required for reading messages
- ✅ Enable **SERVER MEMBERS INTENT** — Optional but helpful

### 5. Invite the Bot to Your Server

1. In the left sidebar, click **"OAuth2"** → **"URL Generator"**
2. Under **SCOPES**, check:
   - ✅ `bot`
   - ✅ `applications.commands`

3. Under **BOT PERMISSIONS**, check:
   - ✅ Send Messages
   - ✅ Read Message History
   - ✅ Use Slash Commands
   - ✅ Embed Links (optional, for rich responses)

4. Copy the generated URL at the bottom
5. Open the URL in a new tab
6. Select your server and click **"Authorize"**

### 6. Paste Token in DexAI Setup

Return to the DexAI setup wizard and paste your bot token.

Click "Test Connection" to verify it works.

### 7. Start Chatting!

Your bot should now appear in your Discord server.
- Type `/dex` or mention the bot to interact
- Or DM the bot directly

---

## Troubleshooting

### "Token invalid"

- Make sure you copied the token from the **Bot** section, not the Application ID
- Tokens look like: `MTIzNDU2Nzg5MDEyMzQ1Njc4.GxxxxA.xxxxxxxxxxxx`
- Try resetting the token and copying it again

### "Missing Access" or "Missing Permissions"

- Make sure you invited the bot with the right permissions
- The bot needs at least "Send Messages" and "Read Message History"
- Try kicking and re-inviting the bot with updated permissions

### Bot is offline

- Make sure DexAI is running
- Check the console for any error messages
- Verify the token is correct

### "Intents are not enabled"

- Go back to the Bot page in Developer Portal
- Enable **MESSAGE CONTENT INTENT**
- This is required to read message content

---

## Optional: Slash Commands

DexAI can register slash commands for easier interaction:

- `/dex ask [question]` — Ask Dex anything
- `/dex task [description]` — Create a task
- `/dex remind [message] [time]` — Set a reminder

Slash commands are registered automatically when DexAI starts.

---

## Privacy Note

Your Discord bot token is stored securely in DexAI's encrypted vault.
Never share your bot token publicly — anyone with the token can control your bot.

If you think your token was exposed, reset it immediately in the Developer Portal.
