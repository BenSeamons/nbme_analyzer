FROM python:3.11-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Explicitly install the chromium browser and its OS dependencies during build
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

# Run gunicorn, binding it to the Railway-supplied PORT
CMD sh -c "gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1"
