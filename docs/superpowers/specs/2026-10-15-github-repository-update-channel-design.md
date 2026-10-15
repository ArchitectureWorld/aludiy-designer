# GitHub Repository and Blender Update Channel Design

## Goal

Move the current AluDIY Designer source into `ArchitectureWorld/aludiy-designer` and establish one public repository for source, tests, documentation, release packages, the visual progress dashboard, and a Blender-compatible remote extension repository.

## Decisions

- The GitHub default branch is `main`.
- Source and release automation live in the same public repository.
- The Blender extension ID remains `aludiy_designer` so future versions update in place.
- The extension package version is read from `extension/aludiy_designer/blender_manifest.toml`; build scripts must not hard-code it.
- Pushes and pull requests run Python tests and deterministic packaging checks.
- Tags matching `v*` publish a GitHub Release and deploy a static Blender extension repository to GitHub Pages.
- The Pages artifact contains the extension ZIP, Blender-generated `index.json`/`index.html`, and a stable `/progress/` dashboard URL.
- Blender's official `server-generate` command is the source of truth for the extension repository index.
- Project files and extension versions remain separate; this task does not change the AluDIY project schema.

## One-time user action

After the workflows are committed, GitHub Pages must be enabled with **Source: GitHub Actions** in the repository settings. No deployment secret is required because the workflow uses the repository `GITHUB_TOKEN` with `pages: write` and `id-token: write`.

## Release flow

1. Update the manifest version and changelog.
2. Push code and ensure CI passes.
3. Create a tag such as `v0.1.6-alpha`.
4. The release workflow validates the tag against the manifest version.
5. It builds the deterministic extension ZIP.
6. It prepares the Pages site and runs Blender `extension server-generate --html`.
7. It deploys Pages and creates/uploads the GitHub Release assets.
8. Blender users refresh the remote repository and click Update.

## Compatibility and safety

- Existing local ZIP installations may require one final uninstall/reinstall when moving to the remote repository.
- Future remote versions keep the same extension ID.
- Build and publication failures stop the release; no partial package is published.
- The remote repository URL is expected to be `https://architectureworld.github.io/aludiy-designer/index.json` after Pages is enabled.
