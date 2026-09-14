FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

RUN chmod +x /app/entrypoint.sh

RUN adduser --disabled-password --gecos "" appuser || true
RUN mkdir -p /app/staticfiles /app/db_data \
	&& chown -R appuser:appuser /app/staticfiles /app/db_data
USER appuser

ENV PORT=8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "odotracker_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
