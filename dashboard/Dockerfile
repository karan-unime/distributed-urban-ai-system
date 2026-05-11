FROM python:3.11

WORKDIR /app

COPY app.py .
COPY templates/ templates/

RUN pip install flask flask-socketio paho-mqtt eventlet

CMD ["python", "app.py"]
