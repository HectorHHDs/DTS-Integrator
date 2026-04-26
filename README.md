# DTS-Integrator
integrates discord threaded channels into a web UI ticketing system using a discord bot. Allows for self-hosting, replies, attachments, and more. The use case for this project is if you are using discord for ticketing or reports and want a more streamlined or centralized way to manage them a lot more easily since the Discord UI is a bit cluttered and not entirely focused on the workflow you are trying to achieve as a ticketing or reporting system. It is also recommended to have a cloudflare (or really any) domain name registered for a more secure tunnel to the network hosting this project. Privacy and GNU license included

How to run using docker:
```
docker run -p hostport:5050 \
  -e DISCORD_BOT_TOKEN=your_discord_bot_token \
  -e FLASK_SECRET_KEY=random_string_of_letters \
  -v /(host_dir_here):/app/db \
  -v /(host_dir_here):/app/uploads \
  ticketing:latest
```
  
ticketing can be any tag you used to build this project

To use this bot, you must create a new discord bot and give it permissions for managing threads, messages, reading messages, sending messages, and managing channels and then invite it to your server.

To change what channels the bot listens on, change #suggestions to any channel with threads, and then change #modpack-crashes-and-bugs to any other channel with threads within discord_bot.py.

Uses flask and zstandard. I recommend using sqlite for managing databases as a backup, as hosting some options on the site can be unsecure - this is why I opted to remove some options from the website such as demoting, promoting, and username changes.

You may change any code in this project, however the general structure is this:

app.py for managing everything
discord_bot.py runs separately to connect to discord channels
/routes/* for menus activated by a sidebar button
index.html for layout
/css/style.css for... style
/css/main.js as another pipeline for clientside rendering and (most importantly) sliding animations
