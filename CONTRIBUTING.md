# CONTRIBUTING.md
# Contributing to the Reusable AI Software Team

We welcome contributions! Please read the following guidelines before submitting a pull request.

## How to Contribute

1. **Fork** the repository.
2. Create a new branch for your feature or bug fix.
3. Run the test suite locally:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -e ".[dev]"
   pytest
   ```
4. Make your changes and add tests.
5. Run linting and type‑checking:
   ```bash
   ruff check .
   mypy src/ tests/
   ```
6. Commit your changes with a clear message.
7. Push to your fork and open a pull request.

## Code Style

- Use 4‑space indentation.
- Follow the style enforced by Ruff (PEP‑8, Black, isort).
- Keep line lengths under 88 characters.

## Testing

All tests must pass locally. The CI workflow will run tests, linting, and type‑checking on every PR.

## Documentation

If you add or modify functionality, update the relevant docs in the `docs/` directory.

## Issue Templates

- Use the **Bug Report** template for bugs.
- Use the **Feature Request** template for new features.

## Code of Conduct

Please adhere to the [Code of Conduct](CODE_OF_CONDUCT.md).
