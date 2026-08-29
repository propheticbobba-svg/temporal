# Agent notes

## GitHub auth

All `git` / `gh` auth for this repo uses the isolated bot config at
`~/.config/gh-warden-bot` (`GH_CONFIG_DIR`). See
`.cursor/rules/github-pr-auth.mdc`.

Do not use personal GitHub login, SSH keys, or macOS Keychain. Do not commit
or print that config directory.
