# Release notes

The release job in `.github/workflows/build.yml` attaches the three platform
deliverables and `SHA256SUMS` to a **draft** GitHub release.

If a file named after the tag exists here, it becomes the release body:

```
release/v0.1.0.md
```

Otherwise the job asks GitHub to generate notes from the commits. Nothing in
this directory is copied into the artifacts.
