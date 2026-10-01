init:
	pip install --upgrade pip
	pip install .[dev]
test:
	pytest tests
publish:
	python -m build
	twine upload dist/*
	rm -fr build dist .egg mano.egg-info
