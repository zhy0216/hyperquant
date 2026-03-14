.PHONY: install test lint fmt typecheck clean docker-up docker-down

install:
	pip install -e ".[dev]"

test:
	pytest --cov --cov-report=term-missing -q

lint:
	ruff check .

fmt:
	ruff format .
	ruff check --fix .

typecheck:
	mypy core/ data/ strategy/ execution/ portfolio/ notify/ utils/ main.py

clean:
	rm -rf .coverage htmlcov/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
