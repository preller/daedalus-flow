{
  # The daedalus dev shell provisions Python, uv, just, git and the native libraries the science wheels load.
  # Python deps live in pyproject.toml and uv.lock; this flake never lists one.

  description = "daedalus dev shell (uv-backed toolchain; Python deps stay in uv.lock)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      nixpkgs,
      flake-utils,
      ...
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };

        # zlib and the gcc runtime lib, which the prebuilt science wheels dlopen.
        runtimeLibs = [
          pkgs.zlib
          pkgs.stdenv.cc.cc.lib
        ];
      in
      {
        devShells.default = pkgs.mkShell {
          # Toolchain only; python312 matches requires-python.
          packages = [
            pkgs.python312
            pkgs.uv
            pkgs.just
            pkgs.git
          ];

          # The science stack finds libz and libstdc++ through this path.
          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath runtimeLibs;

          # Use the nix Python rather than a uv download.
          UV_PYTHON = "${pkgs.python312}/bin/python3.12";

          shellHook = ''
            # Sync every group when the venv is missing, older than uv.lock or has a broken
            # interpreter. Only from the project dir, so a parent flake that reuses this shell no-ops.
            if [ -f pyproject.toml ] \
                 && { [ ! -d .venv ] || [ uv.lock -nt .venv ] \
                        || ! .venv/bin/python -c "" 2>/dev/null; }; then
              echo "daedalus: syncing venv (uv sync --all-groups)..."
              uv sync --all-groups
            fi

            echo "daedalus dev shell ready (python312 + uv + just; libs shimmed via LD_LIBRARY_PATH)."
          '';
        };
      }
    );
}
