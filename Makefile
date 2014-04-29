#
# Simple Makefile for the LapsePiTouch project.
#

.PHONY: docs

html: docs

docs:
	@make -C docs html

pdf:
	@make -C docs latexpdf

clean:
	@make -C docs clean

readthedocs:
	curl -X POST http://readthedocs.org/build/lapse-pi-touch

