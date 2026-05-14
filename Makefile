.PHONY: demo up install pipeline api ui check clean data-check help

PY := .venv/bin/python
UVICORN := .venv/bin/uvicorn
DATA_DIR ?= ../data

help:
	@echo "Targets:"
	@echo "  make demo       Full cold start: up + install + pipeline. Then run 'make api' and 'make ui' in separate terminals."
	@echo "  make up         Bring Postgres up (first boot applies schema/*.sql)."
	@echo "  make install    Create venv and pip install -e ."
	@echo "  make pipeline   Run bronze -> silver -> assessments -> gold."
	@echo "  make api        Start FastAPI on http://127.0.0.1:8000."
	@echo "  make ui         Start React dev server on http://localhost:5173 (npm install on first run)."
	@echo "  make check      Verify pipeline row counts."
	@echo "  make clean      docker compose down -v (wipes the database)."

demo: data-check up install pipeline
	@echo ""
	@echo "Pipeline populated. Next steps (separate terminals):"
	@echo "  make api    → FastAPI at http://127.0.0.1:8000"
	@echo "  make ui     → Dashboard at http://localhost:5173"

data-check:
	@for f in HI-Small_Trans.csv HI-Small_KYC_Customers.csv HI-Small_Account_Customer_Link.csv; do \
	  if [ ! -f "$(DATA_DIR)/$$f" ]; then \
	    echo "Missing: $(DATA_DIR)/$$f"; \
	    echo "Get the AMLSim HI-Small CSVs:"; \
	    echo "  https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml"; \
	    exit 1; \
	  fi; \
	done
	@echo "Data files present in $(DATA_DIR)."

up:
	docker compose up -d
	@echo "Waiting for Postgres to be healthy..."
	@until [ "$$(docker inspect -f '{{.State.Health.Status}}' kgfc-postgres 2>/dev/null)" = "healthy" ]; do sleep 1; done
	@echo "Postgres ready."

install:
	@if [ ! -d .venv ]; then python3 -m venv .venv; fi
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -e .

pipeline:
	@cp -n .env.example .env 2>/dev/null || true
	$(PY) -m bronze.load
	$(PY) -m silver.transform
	$(PY) -m assessments.circular_flow
	$(PY) -m assessments.mule_hub
	$(PY) -m assessments.laundering_exposure
	$(PY) -m gold.publish

api:
	$(UVICORN) api.main:app --reload --host 127.0.0.1 --port 8000

ui:
	@if [ ! -d ui/node_modules ]; then cd ui && npm install; fi
	cd ui && npm run dev

check:
	@docker compose exec -T postgres psql -U kgfc -d kgfincrime -c "\
	SELECT 'bronze.transactions_raw' AS t, count(*) FROM bronze.transactions_raw \
	UNION ALL SELECT 'silver.transfers_to', count(*) FROM silver.transfers_to \
	UNION ALL SELECT 'silver.party', count(*) FROM silver.party \
	UNION ALL SELECT 'silver.account', count(*) FROM silver.account \
	UNION ALL SELECT 'silver.finding', count(*) FROM silver.finding \
	UNION ALL SELECT 'gold.finding', count(*) FROM gold.finding \
	UNION ALL SELECT 'gold.finding_entity', count(*) FROM gold.finding_entity \
	UNION ALL SELECT 'gold.finding_edge', count(*) FROM gold.finding_edge;"

clean:
	docker compose down -v
