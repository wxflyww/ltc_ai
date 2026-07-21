"""Submit documents to Docflow parser service and generate JSON + Markdown output.

Workflow:
1. Submit source file to /docflow/doc/submit and get taskId.
2. Poll /docflow/doc/result/{taskId} until status becomes done.
3. Save the returned JSON next to the source file.
4. Call extract_md.py logic to generate the Markdown file next to the source file.

Examples:
    python docflow_to_md.py "D:/contracts/contract.pdf"
    python docflow_to_md.py "D:/contracts" --recursive
    python docflow_to_md.py "D:/contracts" --suffixes "*"
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import time
from pathlib import Path

import httpx

from extract_md import extract_md

DEFAULT_BASE_URL = "https://dpmapi-test.neusoft.com:8082/docflow"
DEFAULT_SUFFIXES = {".pdf", ".doc", ".docx", ".ofd", ".txt", ".rtf"}
DONE_STATUS = {"done", "success", "completed"}
FAILED_STATUS = {"failed", "error", "timeout", "canceled", "cancelled"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch parse files via Docflow API and generate JSON/Markdown outputs.",
    )
    parser.add_argument(
        "input_path",
        help="Source file path or folder path.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Docflow API key. If omitted, DOCFLOW_API_KEY or X_NEUSOFT_API_KEY is used.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("DOCFLOW_BASE_URL", DEFAULT_BASE_URL),
        help="Docflow base URL. Default comes from DOCFLOW_BASE_URL or built-in value.",
    )
    parser.add_argument(
        "--suffixes",
        default=",".join(sorted(DEFAULT_SUFFIXES)),
        help=(
            "Comma-separated file suffix list for folder mode, like '.pdf,.docx'. "
            "Use '*' to include all files."
        ),
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Scan subfolders recursively when input_path is a folder.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds. Default: 2.0",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Polling timeout in seconds per file. Default: 300",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first failed file.",
    )
    return parser.parse_args()


def read_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def resolve_api_key(cli_api_key: str | None, env_path: Path) -> str:
    if cli_api_key:
        return cli_api_key

    for env_name in ("DOCFLOW_API_KEY", "X_NEUSOFT_API_KEY"):
        env_val = os.getenv(env_name)
        if env_val:
            return env_val

    env_values = read_env_file(env_path)
    for env_name in ("DOCFLOW_API_KEY", "X_NEUSOFT_API_KEY"):
        env_val = env_values.get(env_name)
        if env_val:
            return env_val

    raise ValueError(
        "Missing Docflow API key. Set --api-key, DOCFLOW_API_KEY, or X_NEUSOFT_API_KEY."
    )


def parse_suffixes(raw_suffixes: str) -> set[str] | None:
    cleaned = raw_suffixes.strip()
    if cleaned == "*":
        return None
    suffixes = set()
    for item in cleaned.split(","):
        piece = item.strip().lower()
        if not piece:
            continue
        if not piece.startswith("."):
            piece = f".{piece}"
        suffixes.add(piece)
    return suffixes or set(DEFAULT_SUFFIXES)


def collect_files(target: Path, recursive: bool, suffixes: set[str] | None) -> list[Path]:
    if not target.exists():
        raise FileNotFoundError(f"Input path does not exist: {target}")

    if target.is_file():
        if suffixes and target.suffix.lower() not in suffixes:
            raise ValueError(
                f"File suffix '{target.suffix}' is not in configured suffixes: {sorted(suffixes)}"
            )
        return [target]

    if not target.is_dir():
        raise ValueError(f"Unsupported input path type: {target}")

    iterator = target.rglob("*") if recursive else target.glob("*")
    files = [path for path in iterator if path.is_file()]
    if suffixes:
        files = [path for path in files if path.suffix.lower() in suffixes]
    return sorted(files)


def submit_document(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    source_file: Path,
) -> str:
    submit_url = f"{base_url.rstrip('/')}/doc/submit"
    mime_type, _ = mimetypes.guess_type(source_file.name)
    mime_type = mime_type or "application/octet-stream"

    headers = {"X-Neusoft-Api-Key": api_key}
    with source_file.open("rb") as handle:
        response = client.post(
            submit_url,
            headers=headers,
            files={"file": (source_file.name, handle, mime_type)},
        )

    response.raise_for_status()
    payload = response.json()
    task_id = payload.get("taskId")
    if not task_id:
        raise RuntimeError(f"Submit response missing taskId: {payload}")
    return str(task_id)


def poll_result(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    task_id: str,
    poll_interval: float,
    timeout: float,
) -> dict:
    result_url = f"{base_url.rstrip('/')}/doc/result/{task_id}"
    headers = {"X-Neusoft-Api-Key": api_key}

    deadline = time.monotonic() + timeout
    latest_status = ""

    while True:
        response = client.get(result_url, headers=headers)
        response.raise_for_status()
        payload = response.json()

        status = str(payload.get("status", "")).strip().lower()
        if status in DONE_STATUS:
            return payload
        if status in FAILED_STATUS:
            raise RuntimeError(f"Task failed. taskId={task_id}, response={payload}")

        if status and status != latest_status:
            print(f"  taskId={task_id} status={status}")
            latest_status = status

        if time.monotonic() >= deadline:
            raise TimeoutError(f"Task polling timed out after {timeout}s, taskId={task_id}")

        time.sleep(poll_interval)


def process_single_file(
    client: httpx.Client,
    base_url: str,
    api_key: str,
    source_file: Path,
    poll_interval: float,
    timeout: float,
) -> tuple[Path, Path | None]:
    print(f"[START] {source_file}")
    task_id = submit_document(client, base_url, api_key, source_file)
    print(f"  submit taskId={task_id}")

    result_payload = poll_result(
        client=client,
        base_url=base_url,
        api_key=api_key,
        task_id=task_id,
        poll_interval=poll_interval,
        timeout=timeout,
    )

    json_output = source_file.with_suffix(".json")
    json_output.write_text(
        json.dumps(result_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  saved json: {json_output}")

    extract_md(str(json_output), str(source_file.parent))
    md_output = json_output.with_suffix(".md")

    if md_output.exists():
        print(f"  saved md:   {md_output}")
        return json_output, md_output

    print("  markdown not generated because response has no markdown field.")
    return json_output, None


def main() -> int:
    args = parse_args()

    root_dir = Path(__file__).resolve().parent
    api_key = resolve_api_key(args.api_key, root_dir / ".env")

    target_path = Path(args.input_path).expanduser().resolve()
    suffixes = parse_suffixes(args.suffixes)
    source_files = collect_files(target_path, args.recursive, suffixes)

    if not source_files:
        print("No input files found for parsing.")
        return 0

    print(f"Total files to process: {len(source_files)}")

    success = 0
    failed: list[tuple[Path, str]] = []

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for source_file in source_files:
            try:
                process_single_file(
                    client=client,
                    base_url=args.base_url,
                    api_key=api_key,
                    source_file=source_file,
                    poll_interval=args.poll_interval,
                    timeout=args.timeout,
                )
                success += 1
            except Exception as exc:  # noqa: BLE001
                failed.append((source_file, str(exc)))
                print(f"[FAIL] {source_file}: {exc}")
                if args.fail_fast:
                    break

    print("\nSummary")
    print(f"  Success: {success}")
    print(f"  Failed:  {len(failed)}")

    if failed:
        for file_path, reason in failed:
            print(f"  - {file_path}: {reason}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
