# Contributing to Ghostty²

Thanks for helping improve Ghostty². Bug reports, feature ideas, and pull requests belong in the [Ghostty² repository](https://github.com/pihalf/ghostty2).

Before opening a change:

1. Search the fork's issues and pull requests for related work.
2. Keep changes focused on this fork's goals: the quick-terminal workflow, privacy, packaging, and compatibility with upstream Ghostty.
3. Read [HACKING.md](HACKING.md) and the repository's `AGENTS.md` files for build and testing guidance.
4. Run the narrowest relevant tests, then `zig fmt --check .` and `zig build test` when your environment supports them.
5. Disclose any AI assistance and make sure you understand the submitted code.
6. Explain the behavior change, platforms tested, and any known limitations in the pull request.

Ghostty² remains based on upstream [Ghostty](https://github.com/ghostty-org/ghostty). General terminal-core changes that are not specific to this fork may be better proposed upstream first; please follow Ghostty's contribution policy when doing so.

By contributing, you agree that your work is licensed under this repository's [MIT license](LICENSE).
