FROM python:3.12-slim

WORKDIR /app

# Install git for agent worktrees and commits
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Configure git to trust Docker bind-mounted workspace directory
RUN git config --system --add safe.directory '*'

RUN pip install --no-cache-dir fastapi uvicorn aiosqlite httpx

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data

EXPOSE 8000

CMD ["sh", "-c", "python seed.py && uvicorn main:app --host 0.0.0.0 --port 8000"]
