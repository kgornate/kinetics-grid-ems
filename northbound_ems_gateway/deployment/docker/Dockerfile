FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "nb_ems_gateway.main", "--config", "configs/development.json", "--mock"]
