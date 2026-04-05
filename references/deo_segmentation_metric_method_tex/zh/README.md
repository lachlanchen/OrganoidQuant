# DEO 分割与量化方法中文 TeX 说明

该目录包含当前英文方法说明的中文版本。

主文件：

- `main.tex`

构建命令：

```bash
cd references/deo_segmentation_metric_method_tex/zh
xelatex -interaction=nonstopmode main.tex
xelatex -interaction=nonstopmode main.tex
```

或：

```bash
cd references/deo_segmentation_metric_method_tex/zh
make
```

当前版本使用 `Noto Serif CJK SC` 作为主字体，并针对 XeLaTeX 配置中文换行。
