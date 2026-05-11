FROM python:3.11

WORKDIR /app

COPY . .

RUN pip install paho-mqtt pandas

CMD ["python", "sensor.py"]