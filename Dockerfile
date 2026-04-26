FROM python:3.11-slim

# install supervisord to manage both processes
RUN apt-get update && apt-get install -y supervisor && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install python dependencies
RUN pip install --no-cache-dir \
    flask \
    flask-sqlalchemy \
    werkzeug \
    "discord.py" \
    aiohttp \
    zstandard

# copy your project files in
COPY . .

# persistent storage for uploads and sqlite databases
RUN mkdir -p db uploads

# supervisord config — runs both scripts, restarts either if it crashes
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 5050

ENV FLASK_SECRET_KEY=""
ENV DISCORD_BOT_TOKEN=""

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
