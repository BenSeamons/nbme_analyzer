FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run the app. Railway passes the PORT env variable automatically.
CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1
