FROM python:3.11

WORKDIR /app

COPY sensor.py .
COPY beijing_Industrial_District.csv .
COPY beijing_Residential_District.csv .
COPY beijing_Green_District.csv .

RUN pip install paho-mqtt pandas

CMD ["python", "sensor.py"]