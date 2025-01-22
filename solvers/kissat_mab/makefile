all:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat_mab/build"
kissat:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat_mab/build" kissat
tissat:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat_mab/build" tissat
clean:
	rm -f "/home/adam/Documents/RP/painless/solvers/kissat_mab"/makefile
	-$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat_mab/build" clean
	rm -rf "/home/adam/Documents/RP/painless/solvers/kissat_mab/build"
coverage:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat_mab/build" coverage
indent:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat_mab/build" indent
test:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat_mab/build" test
.PHONY: all clean coverage indent kissat test tissat
