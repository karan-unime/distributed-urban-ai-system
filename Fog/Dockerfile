FROM python:3.11

WORKDIR /app

COPY fog_coordinator.py .

RUN pip install paho-mqtt

CMD ["python", "fog_coordinator.py"]
