FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home listener
COPY main.py .
USER listener
ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]
