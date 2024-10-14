# Makefile
.PHONY: clean clean_all clean_pycache clean_venv clean_interface clean_alo clean_key

clean: clean_pycache clean_venv clean_interface 

clean_all: clean clean_alo clean_key

clean_pycache:
	find . -type d -name "__pycache__" -exec rm -rf {} +
clean_venv:
	rm -rf ./interface/py310_venv
clean_interface:
	rm -rf ./interface
clean_alo:
	rm -rf ./engine/alo_engine/
clean_key:
	cp ./template/.env ./engine/.env
