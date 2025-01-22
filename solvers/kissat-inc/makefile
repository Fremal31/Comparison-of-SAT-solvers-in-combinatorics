all:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat-inc/build"
kissat:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat-inc/build" kissat
tissat:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat-inc/build" tissat
clean:
	rm -f "/home/adam/Documents/RP/painless/solvers/kissat-inc"/makefile
	-$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat-inc/build" clean
	rm -rf "/home/adam/Documents/RP/painless/solvers/kissat-inc/build"
coverage:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat-inc/build" coverage
indent:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat-inc/build" indent
test:
	$(MAKE) -C "/home/adam/Documents/RP/painless/solvers/kissat-inc/build" test
.PHONY: all clean coverage indent kissat test tissat
