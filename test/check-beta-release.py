#!/usr/bin/env python3
"""Reject stable tags and mismatched versions in the beta publishing workflow."""
import pathlib
import re
import sys


def valid(tag, version):
    return bool(re.fullmatch(r"v1\.4\.0-beta\.[1-9][0-9]*", tag)) and tag[1:] == version


def main():
    if sys.argv[1:] == ["--self-test"]:
        assert valid("v1.4.0-beta.1", "1.4.0-beta.1")
        assert valid("v1.4.0-beta.12", "1.4.0-beta.12")
        for tag in ("v1.4.0", "v1.4.0-beta", "v1.4.0-beta.0", "v1.4.0-beta.1+stable", "v1.4.0-beta.2", "v1.5.0-beta.1"):
            assert not valid(tag, "1.4.0-beta.1"), tag
        print("Beta release channel tests passed")
        return
    version = re.search(r'\.version = "([^"]+)"', pathlib.Path("build.zig.zon").read_text())[1]
    if len(sys.argv) != 2 or not valid(sys.argv[1], version):
        sys.exit(f"Only v{version} may be published by this beta workflow; stable promotion is disabled.")
    print(f"Validated beta tag {sys.argv[1]}; publish as prerelease, never latest.")


if __name__ == "__main__":
    main()
