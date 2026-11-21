.PHONY: up down logs test smoke clean

# Creates .env from the template on first run so the stack always starts.
.env:
	@cp .env.example .env
	@echo "WARNING: created .env from .env.example with PLACEHOLDER keys."
	@echo "         The stack will start, but chat needs real keys: edit .env, then 'make up' again."

up: .env  ## Build and start backend (:8000) and frontend (:3000)
	docker compose up --build -d --wait
	@echo ""
	@echo "Backend : http://localhost:8000/health"
	@echo "Frontend: http://localhost:3000"

down:  ## Stop the stack (the data volume is kept)
	docker compose down

logs:  ## Follow logs
	docker compose logs -f --tail=100

test:  ## Run backend tests inside Docker (no local Python needed)
	docker build --target test -t lyftr-backend-test ./backend
	docker run --rm lyftr-backend-test

smoke:  ## Black-box contract check against the running stack (needs real keys in .env)
	python3 scripts/smoke_test.py http://localhost:8000 --origin http://localhost:3000

clean:  ## DESTRUCTIVE: stop, delete the data volume and built images
	docker compose down -v --rmi local
