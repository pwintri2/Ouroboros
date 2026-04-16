# Deployment Guide: Wintrip Messaging Bot to Linux

This guide outlines how to migrate the `messaging-bot` directory from your current environment to your Ubuntu laptop.

## Prerequisites
- SSH access is configured between your Mac and the Ubuntu laptop.
- Python 3 and `pip` are installed on the Ubuntu laptop.

## Steps

### 1. Prepare the destination
On your Ubuntu laptop, ensure the target directory exists:
```bash
ssh user@ubuntu-ip "mkdir -p /home/user/WintripAI"
```

### 2. Copy the directory
Use `rsync` to securely copy the entire `messaging-bot` directory from your Mac:
```bash
rsync -avz /Users/philip/WintripAI/messaging-bot/ user@ubuntu-ip:/home/user/WintripAI/messaging-bot/
```

### 3. Setup on Linux
On the Ubuntu laptop, navigate to the directory and install dependencies:
```bash
cd /home/user/WintripAI/messaging-bot/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Start the bot
Ensure the script is executable and start the bot:
```bash
chmod +x start_bot.sh
./start_bot.sh
```
