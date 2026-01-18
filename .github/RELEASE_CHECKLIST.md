# Release Checklist

Use this checklist when preparing a new release.

## Pre-Release

- [ ] All tests pass on all supported Python versions (3.9-3.12)
- [ ] Type checking passes with mypy strict mode
- [ ] Code formatting is correct (black)
- [ ] Linting passes (ruff)
- [ ] Integration tests pass with LocalStack
- [ ] All property-based tests pass (42 properties)
- [ ] Documentation is up to date
- [ ] Examples are working and tested

## Version Update

- [ ] Update version in `pyproject.toml`
- [ ] Update `CHANGELOG.md`:
  - [ ] Move items from `[Unreleased]` to new version section
  - [ ] Add release date
  - [ ] Add comparison link at bottom
- [ ] Update version in `src/sqs_integration/__init__.py` if applicable
- [ ] Commit changes: `git commit -m "Bump version to X.Y.Z"`

## Git Operations

- [ ] Push changes to main branch
- [ ] Create and push git tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
- [ ] Push tag: `git push origin vX.Y.Z`

## GitHub Release

- [ ] Go to GitHub Releases page
- [ ] Click "Create a new release"
- [ ] Select the tag you created
- [ ] Title: `vX.Y.Z`
- [ ] Description: Copy relevant section from CHANGELOG.md
- [ ] Check "Set as the latest release" (or "Set as a pre-release" for alpha/beta)
- [ ] Click "Publish release"

## Automated Publishing

- [ ] Monitor GitHub Actions workflow
- [ ] Verify build completes successfully
- [ ] Verify package is published to PyPI
- [ ] Check package page on PyPI: https://pypi.org/project/python-sqs-integration/

## Post-Release Verification

- [ ] Install from PyPI: `pip install python-sqs-integration==X.Y.Z`
- [ ] Test basic imports:
  ```python
  from sqs_integration import SqsTemplate, sqs_listener
  ```
- [ ] Run a simple example
- [ ] Check documentation renders correctly on PyPI

## Announcement

- [ ] Update README badges if needed
- [ ] Post announcement (if applicable):
  - [ ] GitHub Discussions
  - [ ] Twitter/Social media
  - [ ] Python community forums

## Prepare for Next Release

- [ ] Add `[Unreleased]` section back to CHANGELOG.md
- [ ] Consider bumping version to next dev version (optional)

## Rollback (if needed)

If something goes wrong:

1. **Yank the release on PyPI** (doesn't delete, but marks as broken)
   - Go to PyPI project page
   - Click "Manage" → "Releases"
   - Click "Options" → "Yank release"

2. **Delete the GitHub release**
   - Go to GitHub Releases
   - Click "Delete" on the problematic release

3. **Delete the git tag**
   ```bash
   git tag -d vX.Y.Z
   git push origin :refs/tags/vX.Y.Z
   ```

4. **Fix the issues and try again**

## Version Numbering Guide

### Semantic Versioning (MAJOR.MINOR.PATCH)

- **MAJOR (1.0.0)**: Breaking changes
  - Incompatible API changes
  - Removed features
  - Changed behavior that breaks existing code

- **MINOR (0.1.0)**: New features
  - New functionality added
  - Backwards compatible
  - Deprecations (but not removals)

- **PATCH (0.0.1)**: Bug fixes
  - Bug fixes
  - Performance improvements
  - Documentation updates
  - Backwards compatible

### Pre-release versions

- **Alpha (0.1.0a1)**: Early testing, unstable
- **Beta (0.1.0b1)**: Feature complete, testing
- **Release Candidate (0.1.0rc1)**: Final testing before release

## Common Issues

### "Package already exists"
- You've already published this version
- Bump the version number and try again
- You cannot re-upload the same version to PyPI

### Trusted publishing fails
- Check workflow name matches (`publish.yml`)
- Check environment name matches (`pypi`)
- Verify you created a GitHub Release (not just a tag)
- Check PyPI trusted publisher configuration

### Tests fail in CI but pass locally
- Check Python version differences
- Check dependency versions
- Check environment variables
- Review CI logs carefully

### Import errors after installation
- Verify package structure is correct
- Check `__init__.py` files exist
- Verify `pyproject.toml` package configuration
- Test with both wheel and sdist

## Resources

- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [PyPI Publishing Guide](https://packaging.python.org/tutorials/packaging-projects/)
- [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github)
