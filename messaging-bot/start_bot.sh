#!/bin/bash
cd /Users/philip/WintripAI/messaging-bot
pkill -f server.py
nohup python3 server.py > bot.log 2>&1 &
echo "Messaging bot started in the background on port 5005. Logs are in bot.log"
