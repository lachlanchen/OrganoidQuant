PDF=main.pdf
TEX=main.tex

all: $(PDF)

$(PDF): $(TEX)
	xelatex -interaction=nonstopmode $(TEX)
	xelatex -interaction=nonstopmode $(TEX)

clean:
	rm -f *.aux *.fdb_latexmk *.fls *.log *.out *.toc *.synctex.gz
