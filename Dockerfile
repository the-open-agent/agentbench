# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install optional dependency (PyYAML) for full dataset support
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy benchmark framework and datasets
COPY . .

# Default entrypoint: run all suites against OpenAgent
# Override --base-url at runtime to point to your OpenAgent instance
ENTRYPOINT ["python", "-m", "agentbench", "run"]
CMD ["--suite", "all", "--rounds", "3", "--max-attempts", "2", "--timeout", "240"]
