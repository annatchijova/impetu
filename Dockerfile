# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Anna Tchijova
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
# Cloud Run sets $PORT; bind there.
CMD exec uvicorn server.main:app --host 0.0.0.0 --port ${PORT}
