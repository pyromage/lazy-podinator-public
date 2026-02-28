# Contributing to Lazy Podinator

Thanks for your interest in improving Lazy Podinator! This guide will help you contribute effectively.

## 🎯 Ways to Contribute

### 🐛 Bug Reports

- Use GitHub Issues with detailed reproduction steps
- Include logs from `gcloud run services logs read lazy-podinator`
- Specify your environment (local, Cloud Run, etc.)

### 💡 Feature Requests  

- Describe the use case and expected behavior
- Consider how it fits with the "simple, personal podcast" goal
- Check existing issues first to avoid duplicates

### 🔧 Code Contributions

- Focus on code quality, reliability, and documentation  
- Test thoroughly with the provided test scripts
- Keep personal configuration out of commits

## 🚀 Development Setup

### Fork & Clone

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/yourusername/lazy-podinator.git
cd lazy-podinator

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Local Testing

```bash
# Set up configuration
cp shows_config.example.json shows_config.json
cp .env.example .env
# Edit with your API keys

# Test script generation
python test/test_local.py

# Test audio (requires Docker)
./test/test_audio_docker.sh
```

### Code Quality

- Follow existing code style and patterns
- Add docstrings for new functions
- Include error handling and logging
- Test edge cases and error scenarios

## 📝 Contribution Areas

### High Priority

- **Audio Quality**: Improvements to Piper TTS settings
- **Content Curation**: Better AI prompts for topic selection  
- **Error Handling**: More robust RSS feed parsing
- **Documentation**: Clearer setup instructions

### Medium Priority  

- **Voice Models**: Support for additional languages
- **Scheduling**: More flexible timing options
- **Monitoring**: Better logging and metrics
- **Testing**: Additional test coverage

### Nice to Have

- **Email Integration**: Newsletter parsing
- **Analytics**: Download tracking
- **Mobile App**: Companion app for management
- **Multi-language**: International support

## 🔀 Submission Process

### Pull Request Guidelines

1. **Create feature branch**: `git checkout -b feature/awesome-improvement`
2. **Make focused changes**: One feature per PR
3. **Test thoroughly**: Both local and Docker testing
4. **Document changes**: Update README/docs if needed
5. **Clean commits**: Clear commit messages

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature  
- [ ] Documentation update
- [ ] Performance improvement

## Testing
- [ ] Local testing completed
- [ ] Docker testing completed
- [ ] Edge cases considered

## Impact
- Affects: (users, deployment, configuration)
- Breaking changes: (none/describe)
```

## Technical Guidelines

### Code Structure

- **main.py**: Core application logic
- **test/**: All testing scripts  
- **scripts/**: Deployment and utility scripts
- **docs/**: Documentation and guides

### Configuration Management

- Use example files for public templates
- Support local override files (*.local.json)
- Document all configuration options
- Provide sensible defaults

### Error Handling

```python
# Good: Specific exception handling
try:
    feed = feedparser.parse(url)
    if not feed.entries:
        print(f"No entries found in {url}")
        continue
except Exception as e:
    print(f"Failed to parse {url}: {e}")
    continue

# Bad: Silent failures
try:
    process_feed(url)
except:
    pass
```

### Logging Best Practices

```python
# Use descriptive log messages
print(f"✓ Generated audio for {config['title']} ({word_count} words)")
print(f"⚠ Skipping {url}: No content found")
print(f"❌ Error processing {show_key}: {e}")
```

## Testing Requirements

### Required Tests

- All changes must pass existing test scripts
- New features require corresponding tests
- Test with example configuration (no personal data)

### Test Categories

1. **Unit Tests**: Individual function testing
2. **Integration Tests**: RSS fetching, AI generation
3. **End-to-End Tests**: Full podcast generation pipeline
4. **Docker Tests**: Container-based audio generation

## Documentation Standards

### Code Documentation

- Docstrings for all public functions
- Inline comments for complex logic
- Type hints where helpful
- Clear variable naming

### User Documentation  

- Update README for user-facing changes
- Add examples to configuration docs
- Include troubleshooting steps
- Keep deployment guide current

## Debugging Guide

### Common Development Issues

**RSS Feed Problems:**

```bash
# Test individual feed
python -c "import feedparser; print(len(feedparser.parse('URL').entries))"
```

**Audio Generation Issues:**

```bash
# Test Piper directly
echo "test" | ./piper/piper --model ./piper/models/en_US-ryan-high.onnx --output_file test.wav
```

**Cloud Deployment Problems:**

```bash
# Check Cloud Run logs
gcloud run services logs read lazy-podinator --limit=50
```

### Getting Help

- GitHub Discussions for questions
- Issues for bug reports

Thanks for making Lazy Podinator better!
