FROM python:3.11

WORKDIR /app

COPY sensor.py .
COPY GlobalWeatherRepository.csv .

RUN pip install paho-mqtt pandas

CMD ["python", "sensor.py"]