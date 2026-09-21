@echo off
REM Bien dich bai bao (can MiKTeX / TeX Live)
cd /d "%~dp0"
xelatex -interaction=nonstopmode main.tex
bibtex main
xelatex -interaction=nonstopmode main.tex
xelatex -interaction=nonstopmode main.tex
echo.
echo Done: main.pdf
pause
