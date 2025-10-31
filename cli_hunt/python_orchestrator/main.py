import requests
import json
import subprocess
import os
import argparse
from datetime import datetime, timezone

DB_FILE = "challenges.json"
RUST_SOLVER_PATH = (
    "../rust_solver/target/release/ashmaize-solver"  # Assuming it's built
)


def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)


def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(
            f"Warning: Could not decode JSON from {DB_FILE}. Starting with an empty DB."
        )
        return {}


def init_db(json_files):
    """Initializes the database from a list of JSON files."""
    print("Initializing database...")
    db = {}
    for file_path in json_files:
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                if (
                    "registration_receipt" in data
                    and "walletAddress" in data["registration_receipt"]
                ):
                    address = data["registration_receipt"]["walletAddress"]
                    db[address] = {
                        "registration_receipt": data["registration_receipt"],
                        "challenge_queue": data.get("challenge_queue", []),
                    }
                    print(f"Added address {address} from {file_path}")
                else:
                    print(
                        f"Warning: Could not find registration_receipt and walletAddress in {file_path}. Skipping."
                    )
        except FileNotFoundError:
            print(f"Error: File not found: {file_path}")
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {file_path}")
    save_db(db)
    print("Database initialized.")


def fetch_challenges():
    print("Fetching challenges...")
    db = load_db()
    addresses = list(db.keys())

    if not addresses:
        print("No addresses found in the database. Run 'init' first.")
        return

    for address in addresses:
        try:
            response = requests.get("https://sm.midnight.gd/api/challenge")
            response.raise_for_status()
            challenge_data = response.json()["challenge"]

            new_challenge = {
                "challengeId": challenge_data["challenge_id"],
                "challengeNumber": challenge_data["challenge_number"],
                "campaignDay": challenge_data["day"],
                "difficulty": challenge_data["difficulty"],
                "status": "available",
                "noPreMine": challenge_data["no_pre_mine"],
                "noPreMineHour": challenge_data["no_pre_mine_hour"],
                "latestSubmission": challenge_data["latest_submission"],
                "availableAt": challenge_data["issued_at"],
            }

            # This case should ideally not happen if init is run first
            if address not in db:
                db[address] = {"registration_receipt": {}, "challenge_queue": []}

            challenge_queue = db[address]["challenge_queue"]

            # Check if challenge already exists for this address
            if not any(
                c["challengeId"] == new_challenge["challengeId"]
                for c in challenge_queue
            ):
                challenge_queue.append(new_challenge)
                challenge_queue.sort(key=lambda c: c["challengeId"])
                print(
                    f"New challenge fetched for {address}: {new_challenge['challengeId']}"
                )
            else:
                print(
                    f"Challenge {new_challenge['challengeId']} already exists for {address}"
                )
        except requests.exceptions.RequestException as e:
            print(f"Error fetching challenge for {address}: {e}")
    save_db(db)


def solve_challenges():
    print("Solving challenges...")
    db = load_db()
    now = datetime.now(timezone.utc)
    for address, data in db.items():
        challenges = data.get("challenge_queue", [])
        for challenge in challenges:
            if challenge["status"] == "available":
                latest_submission = datetime.fromisoformat(
                    challenge["latestSubmission"].replace("Z", "+00:00")
                )
                if now > latest_submission:
                    challenge["status"] = "expired"
                    print(
                        f"Challenge {challenge['challengeId']} for {address} has expired."
                    )
                    continue

                print(
                    f"Attempting to solve challenge {challenge['challengeId']} for {address}"
                )
                try:
                    command = [
                        RUST_SOLVER_PATH,
                        "--address",
                        address,
                        "--challenge-id",
                        challenge["challengeId"],
                        "--difficulty",
                        challenge["difficulty"],
                        "--no-pre-mine",
                        challenge["noPreMine"],
                        "--latest-submission",
                        challenge["latestSubmission"],
                        "--no-pre-mine-hour",
                        challenge["noPreMineHour"],
                    ]
                    result = subprocess.run(
                        command, capture_output=True, text=True, check=True
                    )
                    nonce = result.stdout.strip()
                    print(f"Found nonce: {nonce}")

                    # Submit solution
                    submit_url = f"https://sm.midnight.gd/api/solution/{address}/{challenge['challengeId']}/{nonce}"
                    submit_response = requests.post(submit_url, data={})
                    submit_response.raise_for_status()
                    print(
                        f"Solution submitted successfully for {challenge['challengeId']}"
                    )
                    challenge["status"] = "solved"
                    challenge["solvedAt"] = (
                        datetime.now(timezone.utc)
                        .isoformat(timespec="milliseconds")
                        .replace("+00:00", "Z")
                    )
                    challenge["salt"] = nonce
                    try:
                        submission_data = submit_response.json()
                        if "hash" in submission_data:
                            challenge["hash"] = submission_data["hash"]
                    except json.JSONDecodeError:
                        pass

                except subprocess.CalledProcessError as e:
                    print(f"Rust solver error: {e.stderr}")
                except requests.exceptions.RequestException as e:
                    print(f"Error submitting solution: {e}")
                except Exception as e:
                    print(f"An unexpected error occurred: {e}")
    save_db(db)


def main():
    parser = argparse.ArgumentParser(description="Midnight Scavenger Hunt Orchestrator")
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Sub-command help"
    )

    # Init command
    parser_init = subparsers.add_parser(
        "init", help="Initialize the database from JSON files."
    )
    parser_init.add_argument("files", nargs="+", help="List of JSON files to import.")

    # Fetch command
    subparsers.add_parser("fetch", help="Fetch new challenges for all addresses.")

    # Solve command
    subparsers.add_parser("solve", help="Attempt to solve available challenges.")

    args = parser.parse_args()

    if args.command == "init":
        init_db(args.files)
    elif args.command == "fetch":
        fetch_challenges()
    elif args.command == "solve":
        solve_challenges()


if __name__ == "__main__":
    main()
