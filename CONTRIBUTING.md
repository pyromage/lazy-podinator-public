# Contributing to Lazy Podinator

Thank you for considering contributing to Lazy Podinator! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork locally
3. Create a new branch for your feature or bugfix
4. Make your changes
5. Test your changes locally (see README.md for testing instructions)
6. Submit a pull request

## Development Workflow

### Local Testing

Before submitting a PR, please test your changes:

```bash
# Test script generation
python test_local.py

# Test audio generation with Docker
./test_audio_docker.sh
```

### Code Style

* Follow PEP 8 for Python code
* Use meaningful variable names
* Add comments for complex logic
* Keep functions focused and modular

### Configuration Changes

If you add new configuration options:

* Update `shows_config.json` with examples (including any new feeds or labels)
* Document the new options in README.md
* Ensure backward compatibility if possible

## Pull Request Guidelines

### PR Title Format

* `feat:` for new features
* `fix:` for bug fixes
* `docs:` for documentation changes
* `refactor:` for code refactoring
* `test:` for test additions/changes

Example: `feat: add support for new TTS voice models`

### PR Description

Include:

* What changes you made and why
* How to test the changes
* Any breaking changes
* Screenshots/logs if applicable

## Reporting Issues

When reporting bugs, please include:

* Description of the issue
* Steps to reproduce
* Expected vs actual behavior
* Environment details (OS, Python version, etc.)
* Relevant logs or error messages

## Feature Requests

We welcome feature requests! Please:

* Check existing issues first to avoid duplicates
* Clearly describe the feature and use case
* Explain why it would be valuable
* Consider if it fits the project's scope (serverless, free-tier focus)

## Areas for Contribution

We especially welcome contributions in:

* Additional TTS voice support
* New RSS feed sources
* Improved article content extraction
* Better error handling and logging
* Performance optimizations
* Documentation improvements

## Questions?

Open an issue with the `question` label or start a discussion.

Thank you for contributing!
