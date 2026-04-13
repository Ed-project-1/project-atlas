FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the simulator script
COPY bank_simulator.py .

# Run the simulator when container starts
CMD ["python", "bank_simulator.py"]
