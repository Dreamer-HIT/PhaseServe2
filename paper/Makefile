MAIN ?= PhaseServe.tex
PDF := $(MAIN:.tex=.pdf)
TECTONIC ?= tectonic

.PHONY: all build pdf view open clean doctor

all: build

build pdf:
	@command -v $(TECTONIC) >/dev/null 2>&1 || { \
		echo "tectonic is not installed. Install it with: brew install tectonic"; \
		exit 1; \
	}
	$(TECTONIC) $(MAIN)

view open: build
	open "$(PDF)"

doctor:
	@command -v $(TECTONIC) >/dev/null 2>&1 && $(TECTONIC) --version || { \
		echo "tectonic is not installed. Install it with: brew install tectonic"; \
		exit 1; \
	}

clean:
	rm -f *.aux *.bbl *.blg *.log *.out *.toc *.lof *.lot *.synctex.gz *.fls *.fdb_latexmk
