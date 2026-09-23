FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py metrics.py business_views.py view_writer.py ./
CMD exec gunicorn --bind :${PORT:-8080} --workers 1 --threads 1 --timeout 240 main:app
