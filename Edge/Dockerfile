FROM python:3.11

WORKDIR /app

# Copy agent and dataset
COPY edge_agent.py .
COPY processed_weather.csv .

# Install dependencies
RUN pip install paho-mqtt pandas scikit-learn

CMD ["python", "edge_agent.py"]
