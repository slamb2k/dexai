# Setting up Slack with DexAI

## What You'll Need
- A Slack workspace where you have admin permissions
- 10-15 minutes (Slack setup is the most involved)

## Steps

### 1. Create a Slack App

1. Go to https://api.slack.com/apps
2. Click **"Create New App"**
3. Choose **"From scratch"**
4. Name it "DexAI" (or your preference)
5. Select your workspace
6. Click **"Create App"**

### 2. Configure Socket Mode

Socket Mode allows DexAI to receive events without a public URL.

1. In the left sidebar, click **"Socket Mode"**
2. Toggle **"Enable Socket Mode"** ON
3. You'll be prompted to create an App-Level Token:
   - Name it "dexai-socket"
   - Add the scope: `connections:write`
   - Click **"Generate"**
4. **Copy this token** — it starts with `xapp-`

### 3. Configure Bot Token Scopes

1. In the left sidebar, click **"OAuth & Permissions"**
2. Scroll to **"Scopes"** → **"Bot Token Scopes"**
3. Add these scopes:
   - `app_mentions:read` — Respond when mentioned
   - `chat:write` — Send messages
   - `im:history` — Read DM history
   - `im:read` — Access DMs
   - `im:write` — Send DMs
   - `users:read` — Get user info

### 4. Enable Events

1. In the left sidebar, click **"Event Subscriptions"**
2. Toggle **"Enable Events"** ON
3. Under **"Subscribe to bot events"**, add:
   - `app_mention` — When someone @mentions the bot
   - `message.im` — Direct messages to the bot

### 5. Enable Home Tab (Optional)

1. In the left sidebar, click **"App Home"**
2. Toggle **"Home Tab"** ON
3. Toggle **"Messages Tab"** ON
4. Check **"Allow users to send Slash commands and messages from the messages tab"**

### 6. Install to Workspace

1. In the left sidebar, click **"Install App"**
2. Click **"Install to Workspace"**
3. Review the permissions and click **"Allow"**
4. **Copy the Bot User OAuth Token** — it starts with `xoxb-`

### 7. Paste Tokens in DexAI Setup

Return to the DexAI setup wizard and paste both tokens:
- **Bot Token**: The `xoxb-...` token from OAuth & Permissions
- **App Token**: The `xapp-...` token from Socket Mode

Click "Test Connection" to verify they work.

### 8. Start Chatting!

Your bot should now appear in your Slack workspace.
- DM the bot directly
- Or @mention it in any channel it's invited to

---

## Troubleshooting

### "invalid_auth"

- Make sure you copied the correct tokens:
  - Bot Token starts with `xoxb-`
  - App Token starts with `xapp-`
- Try reinstalling the app to your workspace

### "missing_scope"

- Go to OAuth & Permissions and add the required scope
- Reinstall the app after adding scopes (Slack requires this)

### Bot doesn't respond to DMs

- Make sure you added the `im:*` scopes
- Make sure you subscribed to `message.im` events
- Try reinstalling the app

### Bot doesn't respond to mentions

- Make sure you subscribed to `app_mention` events
- Make sure the bot is invited to the channel
- Invite with `/invite @DexAI`

### "not_allowed_token_type"

- You might be using the wrong token type
- App Token (`xapp-`) is for Socket Mode connection
- Bot Token (`xoxb-`) is for API calls

---

## Quick Reference: Required Configuration

| Setting | Location | Required |
|---------|----------|----------|
| Socket Mode | Socket Mode page | ✅ Enabled |
| App Token | Socket Mode page | ✅ `xapp-...` |
| Bot Token | OAuth & Permissions | ✅ `xoxb-...` |
| Bot Scopes | OAuth & Permissions | ✅ See step 3 |
| Events | Event Subscriptions | ✅ See step 4 |

---

## Privacy Note

Your Slack tokens are stored securely in DexAI's encrypted vault.
Never share your tokens publicly.

If you think your tokens were exposed:
1. Go to your app settings
2. Regenerate the tokens
3. Update them in DexAI settings
