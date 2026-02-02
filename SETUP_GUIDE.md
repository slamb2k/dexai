# Claude Code Setup Guide (Beginner Friendly)

A step-by-step guide to set up Claude Code in VS Code from scratch.

---

## Prerequisites

Before you start, you need:

1. **A computer** (Mac, Windows, or Linux)
2. **Claude subscription** - this gives you unlimited Claude Code usage
   - Sign up at: https://claude.ai
   You cna use this with codex, gemini, grok - just change the .md file from claude.md to whatever your AI uses. 
3. **VS Code** (free) - download from: https://code.visualstudio.com

---

## Step 1: Install VS Code

1. Go to https://code.visualstudio.com
2. Click the big download button
3. Install it like any other app
4. Open VS Code

---

## Step 2: Install Claude Code Extension

1. In VS Code, look at the left sidebar
2. Click the **Extensions icon** (looks like 4 squares/puzzle piece)
3. In the search bar, type: `Claude Code`
4. Find the official one by **Anthropic**
5. Click **Install**
6. Wait for it to finish

---

## Step 3: Sign In to Claude

1. After installing, you'll see a Claude icon in the left sidebar
2. Click it
3. Click **Sign In**
4. It will open your browser - log in with your Claude account
5. Authorize the connection
6. You're connected!

---

## Step 4: Create Your Project Folder

1. On your computer, create a new folder somewhere (e.g., Desktop or Documents)
2. Name it something like `my-agent` or `claude-workspace`
3. In VS Code, go to **File → Open Folder**
4. Select the folder you just created
5. Click **Open**

You now have an empty workspace. This is a safe space it will ONLY build in here as long as you dont give it permissions or a command to build elsewhere. 

---

## Step 5: Add the Framework Files

Download these files from the video description and drag them into your folder:

### Required Files:
- `CLAUDE.md` - This is the "brain" that tells Claude how to operate
- `build_app.md` - Put this inside a `goals/` folder
- 'memory' - a folder containing the python sripts if you want memory. Create a folder called "tools" and put the memory folder in there inside your vscode alongside the baove 2 files.

### Your folder should look like:
```
my-agent/
├── CLAUDE.md
└── goals/
    └── build_app.md
|--tools/
    |__memory/
```

**To create the goals folder:**
1. Right-click in the VS Code file explorer (left panel)
2. Click **New Folder**
3. Name it `goals`
4. Drag `build_app.md` into it

---

## Step 6: Initialize Your Environment

1. Click the **Claude icon** in the chat sidebar (or press `Cmd+Shift+P` and type "Claude")
2. Start a new chat
3. Type this message:

```
Hey, this is a new environment. Please initialize it by reading CLAUDE.md and setting up the folder structure.
```

4. Press Enter
5. Claude will read your CLAUDE.md and create all the folders it needs
6. When it asks for permission to run commands, click **Yes** or **Allow**

---

## Step 7: You're Ready!

That's it! You can now:

- Ask Claude to build apps: `Build me a simple todo app`
- Ask Claude to create tools: `Create a Python script that does X`
- Ask Claude to research: `Research the best way to do Y`
- Build a leadgen app - whatever you want. 

---

## Quick Tips for Beginners

### How to Talk to Claude
Just type naturally in the chat. Examples:
- "Build me a landing page for my business"
- "Create a script that sends me a daily email"
- "Help me understand this code"

### When Claude Asks for Permission
Claude will ask before running commands or creating files. You can:
- Click **Yes** to allow once
- Click **Always Allow** if you trust it for that type of action

### If Something Goes Wrong
Just tell Claude:
- "That didn't work, here's the error: [paste error]"
- "Can you fix that?"
- "Let's try a different approach"

### Save Your Work
Your files are automatically saved in the folder you created. You can back this up like any other folder.

---

## Common Questions

### Do I need to know how to code?
No! Claude writes the code for you. But basic understanding helps.

### How much does it cost?
- Claude Max: $20/month (unlimited Claude Code)
- VS Code: Free

### Can I use this on Windows?
Yes! Works on Mac, Windows, and Linux.

### What if Claude makes a mistake?
Just tell it. Say "That's not right, can you fix X?" - Claude learns from feedback.

### Where do my files go?
Everything stays in the folder you created. Nothing is uploaded anywhere unless you specifically ask Claude to do that or give it permissions to do so.

---

## Need Help?

- Check my youtube for builds and guides
- Join the community: [[link](https://www.skool.com/cybercloudpremium)]
- Add me on LinkedIn: [[link](https://www.linkedin.com/in/mansel-scheffel/)]

---

*Remember: Claude is like a brilliant assistant. The better you explain what you want, the better results you get. Don't be afraid to experiment but dont give it the keys to your wallet without a human in the loop!*
