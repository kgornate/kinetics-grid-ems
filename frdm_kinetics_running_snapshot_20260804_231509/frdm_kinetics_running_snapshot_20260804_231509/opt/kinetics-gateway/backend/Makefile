.PHONY: install test run-mock compile probe package

install:
	python3 -m pip install -r requirements.txt

test:
	pytest -q

compile:
	python3 -m compileall -q app tools tests

run-mock:
	KINETICS_CONFIG=configs/kinetics_mock.json uvicorn app.main:app --host 0.0.0.0 --port 8000

probe:
	python3 tools/modbus_probe.py --host 10.30.4.13 --ports 503 504 505 506 507 --unit-ids 1 2 3 4 5 127 --address 0 --count 1
