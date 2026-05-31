This is a Somnia hackathon project for NFT-gated voting through a Somnia JSON
API agent and a public GET wrapper.

Project priorities:
- Keep the repo minimal, explicit, and easy to run from a fresh terminal.
- Never commit or print private keys, seed phrases, real wallet secrets, or
  local deployed config.
- Use Somnia testnet by default unless the user explicitly asks otherwise.
- Develop contract + CLI first. Do not build the frontend until the contract,
  wrapper, and live JSON agent path are stable.
- Keep the live JSON API agent ID, method selector, price, wrapper URL, and
  deployed addresses configurable because these are the brittle integration
  points.
- Include fast preflight and dry/offline checks before commands that spend STT.
- Preserve callback and response evidence in events/logs for failed agent runs.
- Keep context ZIPs under 10 MB and exclude `.env.local`, `config.local.json`,
  `.git`, dependencies, caches, and build artifacts.

Python/run-command conventions:
- Work from the repo root on macOS. Do not assume global Python packages are
  installed; use the repo-local virtual environment.
- First check `pwd`, `ls`, and `python3 --version`.
- If `.venv` does not exist, create it with `python3 -m venv .venv`.
- Activate it with `source .venv/bin/activate`, then install dependencies with
  `python -m pip install --upgrade pip` and
  `python -m pip install -r requirements.txt`.
- Run Python scripts through `python` from the repo root, for example
  `python scripts/somnia_vote_cli.py --help`,
  `python scripts/somnia_vote_cli.py --config config.example.json compile`,
  `python scripts/somnia_vote_cli.py live-defaults`, and
  `python scripts/check_public_wrapper.py --help`.
- Run tests with `python -m pytest`, not bare `pytest`. For targeted checks use
  `python -m pytest test/test_wrapper.py`,
  `python -m pytest test/test_nft_gated_vote.py`,
  `python -m pytest test/test_cli_validation.py`, or
  `python -m pytest test/test_wrapper_live.py`.
- If a listed test file does not exist, run
  `find test -maxdepth 1 -type f -name 'test_*.py' -print` and then
  `python -m pytest test`.
- Do not run scripts as `./scripts/somnia_vote_cli.py ...` unless the file is
  explicitly executable and has a working shebang. Prefer
  `python scripts/somnia_vote_cli.py ...`.
- Do not print secrets or `cat .env.local`. To check for a private key variable
  without printing it, use
  `test -f .env.local && grep -q '^SOMNIA_PRIVATE_KEY=0x' .env.local && echo "SOMNIA_PRIVATE_KEY present"`.
- If `config.local.json` already exists, do not overwrite it with
  `cp config.example.json config.local.json` unless the user explicitly says it
  is okay. Use `config.example.json` for read-only compile/help checks and
  `config.local.json` only for local/live operations.

Useful references:
- Keep personal local reference paths out of tracked public docs.
- Prior Somnia agent experiments and callback ABI evidence may exist in local
  private workspaces, but should be summarized before being copied here.
