# Documentation

This directory contains the Sphinx documentation for papagai.

## Building Locally

Install the documentation dependencies:

```console
$ pip install -e .[docs]
```

Build the documentation:

```console
$ cd doc
$ make html
```

The built documentation will be in `_build/html/`. Open `_build/html/index.html` in your browser.

## Building with uv

If using uv for development:

```console
$ uv pip install -e .[docs]
$ cd doc
$ make html
```

## Available Make Targets

- `make html` - Build HTML documentation
- `make clean` - Remove built documentation
- `make help` - Show all available targets

## Read the Docs

This documentation is configured to build automatically on Read the Docs using the `.readthedocs.yaml` configuration file in the repository root.
