FROM python:3.12-slim
WORKDIR /app
# The bot uses only the standard library; tzdata just makes log times Eastern.
RUN pip install --no-cache-dir tzdata
COPY alpaca.py bot.py config.py ./
# Keys come from the host's environment settings, never from the image:
#   ALPACA_API_KEY, ALPACA_SECRET_KEY   (optional: END_DATE, ODTE_ENABLED, ...)
CMD ["python", "-u", "bot.py", "run"]
