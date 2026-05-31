# PhaseServe LaTeX Draft

This directory contains the LaTeX source for the PhaseServe paper.

## Build

```sh
make
```

This compiles `PhaseServe.tex` with `tectonic` and writes `PhaseServe.pdf`.

## Open the PDF

```sh
make view
```

This rebuilds the paper if needed and opens `PhaseServe.pdf` with the default macOS PDF viewer.

## Toolchain

This workspace uses `tectonic`, a lightweight LaTeX engine that downloads missing LaTeX packages on demand.

If it is missing on another machine:

```sh
brew install tectonic
```

## Clean Temporary Files

```sh
make clean
```
