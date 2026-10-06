.PHONY: setup dev dev-backend dev-frontend test build demo-check

setup:
	cd backend && uv sync --python 3.11 --extra dev
	cd frontend && npm install

dev:
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q

build:
	cd frontend && npm run build

demo-check:
	cd backend && uv run python ../scripts/demo_check.py
