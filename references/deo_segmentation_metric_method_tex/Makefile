PDF=main.pdf
TEX=main.tex

all: $(PDF)

$(PDF): $(TEX)
	pdflatex -interaction=nonstopmode $(TEX)
	pdflatex -interaction=nonstopmode $(TEX)

clean:
	rm -f *.aux *.fdb_latexmk *.fls *.log *.out *.toc *.synctex.gz
